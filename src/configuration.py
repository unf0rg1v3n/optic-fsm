"""
Модуль конфигурации фреймворка OpticFSM.
Содержит структуры данных (DSL) и логику парсинга на базе Pydantic.
"""
import json
import random
import time
from enum import StrEnum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


class Action(StrEnum):
    CLICK = 'click'
    DOUBLE_CLICK = 'double_click'
    WAIT = 'wait'


class DelayStrategy(StrEnum):
    FIXED = 'fixed'
    UNIFORM = 'uniform'
    GAUSSIAN = 'gaussian'


class DelayConfig(BaseModel):
    strategy: DelayStrategy = Field(default=DelayStrategy.GAUSSIAN)
    mean: float = Field(default=0.8)
    std_dev: float = Field(default=0.2)
    min_val: float = Field(default=0.5)
    max_val: float = Field(default=1.5)

    def execute(self, base_msec: Optional[int] = None) -> None:
        base_sec = (base_msec / 1000.0) if base_msec else 0.0

        if self.strategy == DelayStrategy.FIXED:
            noise = self.mean if not base_msec else 0.0
        elif self.strategy == DelayStrategy.UNIFORM:
            noise = random.uniform(self.min_val, self.max_val)
        elif self.strategy == DelayStrategy.GAUSSIAN:
            noise = max(0.1, random.gauss(self.mean, self.std_dev))
        else:
            noise = 0.0

        total_delay = base_sec + noise
        time.sleep(total_delay)


class ScaleSettings(BaseModel):
    base_resolution: Optional[str] = Field(default=None)
    min_scale: float = Field(default=0.5)
    max_scale: float = Field(default=1.5)
    scale_step: float = Field(default=0.05)

    @property
    def parsed_resolution(self) -> Optional[Tuple[int, int]]:
        """Парсит строку разрешения в кортеж (width, height)."""
        if self.base_resolution:
            parts = self.base_resolution.lower().split('x')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        return None


class SessionLimits(BaseModel):
    max_iterations: Optional[int] = Field(default=None, gt=0)
    iteration_trigger_state: Optional[str] = Field(default=None)
    max_runtime_sec: Optional[int] = Field(default=None, gt=0)
    stop_anchors: List[str] = Field(default_factory=list)


class EngineSettings(BaseModel):
    project_name: str
    target_window_title: str
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    global_timeout_sec: int
    delay: DelayConfig
    session_limits: Optional[SessionLimits] = Field(default=None)
    scale_settings: ScaleSettings = Field(default_factory=ScaleSettings)


class TransitionConfig(BaseModel):
    target_template: Optional[str] = Field(default=None)
    action: Action
    next_state: str
    retries: int = Field(default=1)
    delay_msec: Optional[int] = Field(default=None)

    @model_validator(mode="after")
    def check_action_dependencies(self) -> "TransitionConfig":
        if self.action == Action.WAIT and self.delay_msec is None:
            raise ValueError("Поле 'delay_msec' обязательно для action='wait'")
        if self.action in (Action.CLICK, Action.DOUBLE_CLICK) and self.target_template is None:
            raise ValueError("Поле 'target_template' обязательно для клика")
        return self


class StateConfig(BaseModel):
    is_terminal: bool = Field(default=False)
    is_discoverable: bool = Field(default=True)
    anchors: List[str]
    transitions: List[TransitionConfig]


class OpticFSMConfig(BaseModel):
    engine_settings: EngineSettings
    start_state: str
    states: Dict[str, StateConfig]


def load_config(file_path: str) -> OpticFSMConfig:
    with open(file_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    return OpticFSMConfig(**raw_data)