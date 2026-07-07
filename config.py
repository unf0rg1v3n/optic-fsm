import json
import time
from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional
from enum import StrEnum
import random


class Action(StrEnum):
    CLICK = 'click'
    DOUBLE_CLICK = 'double_click'
    WAIT = 'wait'


class DelayStrategy(StrEnum):
    FIXED = 'fixed'
    UNIFORM = 'uniform'
    GAUSSIAN = 'gaussian'


class HumanDelay(BaseModel):
    mean: float
    std_dev: float


class EngineSettings(BaseModel):
    project_name: str
    target_window_title: str
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    global_timeout_sec: int
    human_delay: HumanDelay


class DelayConfig(BaseModel):
    strategy: DelayStrategy = Field(default=DelayStrategy.GAUSSIAN)

    mean: float = Field(default=0.8)
    std_dev: float = Field(default=0.2)

    min_val: float = Field(default=0.5)
    max_val: float = Field(default=1.5)

    def execute(self, base_msec: Optional[int] = None):
        """
        Умная функция задержки.
        Если передан base_msec (например, от действия WAIT), он используется как база,
        а стратегия накидывает сверху человеческую погрешность.
        Если это обычный CLICK, base_msec = 0.
        """
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
        print(
            f"    [Delay] Ждем {total_delay:.3f} сек. (База: {base_sec}s, Шум: {noise:.3f}s, Стратегия: {self.strategy})")
        time.sleep(total_delay)


class TransitionConfig(BaseModel):
    target_template: Optional[str] = Field(default=None)
    action: Action
    next_state: str
    retries: int = Field(default=1)
    delay_msec: Optional[int] = Field(default=None)

    @model_validator(mode="after")
    def check_action_dependencies(self) -> "TransitionConfig":
        if self.action == Action.WAIT and self.delay_msec is None:
            raise ValueError(
                "Поле 'delay_msec' обязательно для заполнения при action='wait'")

        if self.action in (Action.CLICK, Action.DOUBLE_CLICK) and self.target_template is None:
            raise ValueError(
                "Поле 'target_template' обязательно для действий 'click'")

        return self


class StateConfig(BaseModel):
    is_terminal: bool = Field(default=False)
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
