from config_parser import OpticFSMConfig, TransitionConfig
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

    def human_sleep(self, delay_msec: Optional[int] = None):
        if delay_msec:
            time.sleep(delay_msec / 1000.0)

        mean = self.settings.human_delay.mean
        std_dev = self.settings.human_delay.std_dev
        delay = max(0.1, random.gauss(mean, std_dev))
        time.sleep(delay)


class OpticFSM_Engine:
    def __init__(self, config: "OpticFSMConfig"):
        self.config = config
        self.current_state_name = config.start_state
        self.vision = VisionAdapter(config.engine_settings)
