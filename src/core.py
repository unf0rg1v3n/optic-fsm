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
    def __init__(self, config: OpticFSMConfig):
        self.config = config
        self.current_state_name = config.start_state
        self.vision = VisionAdapter(config.engine_settings)
        
        self.state_enter_time = time.time()
        self.session_start_time = time.time()  # <--- Старт сессии
        self.iterations_completed = 0          # <--- Счетчик циклов

    def _check_session_limits(self) -> bool:
        """Проверяет глобальные условия остановки. Возвращает True, если нужно прервать работу."""
        limits = self.config.engine_settings.session_limits
        if not limits:
            return False

        if limits.max_runtime_sec:
            total_elapsed = time.time() - self.session_start_time
            if total_elapsed > limits.max_runtime_sec:
                logger.info(f"🛑 Остановка: Достигнут лимит времени сессии ({limits.max_runtime_sec} сек).")
                return True

        if limits.max_iterations and self.iterations_completed >= limits.max_iterations:
            logger.info(f"🛑 Остановка: Выполнено максимальное количество итераций ({limits.max_iterations}).")
            return True

        if limits.stop_anchors:
            screen = self.vision._get_screenshot_gray()
            for anchor in limits.stop_anchors:
                if self.vision._find_template(screen, anchor):
                    logger.critical(f"🛑 Аварийная остановка: Обнаружен стоп-якорь на экране ({anchor})!")
                    return True

        return False

    def run(self) -> None:
        """Запускает бесконечный цикл обработки автомата."""
        logger.info(f"--- Запуск OpticFSM: {self.config.engine_settings.project_name} ---")

        while True:
            if self._check_session_limits():
                logger.info(f"Сессия завершена. Итераций: {self.iterations_completed}, Время работы: {time.time() - self.session_start_time:.1f} сек.")
                break

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

            limits = self.config.engine_settings.session_limits
            if limits and self.current_state_name == limits.iteration_trigger_state:
                self.iterations_completed += 1
                logger.info(f"✅ Итерация завершена! Выполнено: {self.iterations_completed}/{limits.max_iterations}")

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
