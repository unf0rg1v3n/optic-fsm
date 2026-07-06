from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional
from enum import StrEnum

class Action(StrEnum):
    CLICK = 'click'
    DOUBLE_CLICK = 'double_click'
    WAIT = 'wait'


class HumanDelay(BaseModel):
    mean: float
    std_dev: float

class EngineSettings(BaseModel):
    project_name: str
    target_window_title: str
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    global_timeout_sec: int
    human_delay: HumanDelay

class TransitionConfig(BaseModel):
    target_template: Optional[str] = Field(default=None)
    action: Action
    next_state: str
    retries: int = Field(default=1)
    delay_msec: Optional[int] = Field(default=None)

    @model_validator(mode="after")
    def check_action_dependencies(self) -> "TransitionConfig":
        if self.action == Action.WAIT and self.delay_msec is None:
            raise ValueError("Поле 'delay_msec' обязательно для заполнения при action='wait'")
        
        if self.action in (Action.CLICK, Action.DOUBLE_CLICK) and self.target_template is None:
            raise ValueError("Поле 'target_template' обязательно для действий 'click'")
        
        return self

class StateConfig(BaseModel):
    is_terminal: bool = Field(default=False)
    anchors: List[str]
    transitions: List[TransitionConfig]

class OpticFSMConfig(BaseModel):
    engine_settings: EngineSettings
    start_state: str
    states: Dict[str, StateConfig]

import json

def load_config(file_path: str) -> OpticFSMConfig:
    with open(file_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    return OpticFSMConfig(**raw_data)
