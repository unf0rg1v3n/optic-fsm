from config import OpticFSMConfig, TransitionConfig
from typing import Optional
import time
import logging
import random


class VisionAdapter:
    def __init__(self, settings):
        self.settings = settings

    def verify_anchors(self, anchors: list[str]) -> bool:
        pass

    def execute_transition(self, transition: "TransitionConfig") -> bool:
        pass

    def perform_sleep(self, delay_msec: Optional[int] = None):
        self.settings.delay.execute(base_msec=delay_msec)


class OpticFSM_Engine:
    def __init__(self, config: "OpticFSMConfig"):
        self.config = config
        self.current_state_name = config.start_state
        self.vision = VisionAdapter(config.engine_settings)
