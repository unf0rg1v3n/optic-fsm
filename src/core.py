"""
Модуль ядра конечного автомата.
Управляет навигацией по графу состояний и жизненным циклом фреймворка.
"""
import logging
import time

from configuration import OpticFSMConfig
from vision import VisionAdapter

logger = logging.getLogger(__name__)


class OpticFSMEngine:
    """Главный класс движка конечного автомата."""
    # pylint: disable=too-few-public-methods

    def __init__(self, config: OpticFSMConfig):
        self.config = config
        self.current_state_name = config.start_state
        self.vision = VisionAdapter(config.engine_settings)
        self.state_enter_time = time.time()

    def _change_state(self, new_state_name: str) -> None:
        """Изменяет текущее состояние и сбрасывает Watchdog-таймер."""
        logger.info("Смена состояния: [%s] ---> [%s]", self.current_state_name, new_state_name)
        self.current_state_name = new_state_name
        self.state_enter_time = time.time()

    def run(self) -> None:
        """Запускает бесконечный цикл обработки автомата."""
        logger.info("--- Запуск OpticFSM: %s ---", self.config.engine_settings.project_name)

        while True:
            current_state = self.config.states.get(self.current_state_name)
            if not current_state:
                logger.error("Критическая ошибка: Состояние '%s' не найдено!",
                             self.current_state_name)
                break

            if current_state.is_terminal:
                logger.info("Достигнуто терминальное состояние '%s'. Завершение.",
                            self.current_state_name)
                break

            elapsed = time.time() - self.state_enter_time
            if elapsed > self.config.engine_settings.global_timeout_sec:
                logger.warning("Таймаут в состоянии '%s' (%.1f сек).",
                               self.current_state_name, elapsed)
                self._change_state("error_state")
                continue

            if current_state.anchors:
                if not self.vision.verify_anchors(current_state.anchors):
                    time.sleep(0.5)
                    continue

            transition_executed = False
            for transition in current_state.transitions:
                if self.vision.execute_transition(transition):
                    self.vision.settings.delay.execute(base_msec=transition.delay_msec)
                    self._change_state(transition.next_state)
                    transition_executed = True
                    break

            if not transition_executed:
                time.sleep(0.1)
