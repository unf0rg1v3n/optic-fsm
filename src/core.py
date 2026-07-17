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

    def __init__(self, config: OpticFSMConfig):
        self.config = config
        self.current_state_name = config.start_state
        self.vision = VisionAdapter(config.engine_settings)

        self.state_enter_time = time.time()
        self.session_start_time = time.time()
        self.iterations_completed = 0
        
        self.last_wait_log_time = 0.0

    def _change_state(self, new_state_name: str) -> None:
        logger.info("Смена состояния: [%s] ---> [%s]", self.current_state_name, new_state_name)
        self.current_state_name = new_state_name
        self.state_enter_time = time.time()
        self.last_wait_log_time = 0.0

        limits = self.config.engine_settings.session_limits
        if limits and new_state_name == limits.iteration_trigger_state:
            self.iterations_completed += 1
            max_iter = limits.max_iterations if limits.max_iterations else "∞"
            logger.info("✅ Итерация завершена! Выполнено: %s/%s", self.iterations_completed, max_iter)

    def _check_session_limits(self) -> bool:
        limits = self.config.engine_settings.session_limits
        if not limits:
            return False

        if limits.max_runtime_sec:
            if (time.time() - self.session_start_time) > limits.max_runtime_sec:
                logger.info("🛑 Остановка: Достигнут лимит времени сессии.")
                return True

        if limits.max_iterations and self.iterations_completed >= limits.max_iterations:
            logger.info("🛑 Остановка: Выполнено максимальное количество итераций.")
            return True

        if limits.stop_anchors:
            screen = self.vision._get_screenshot_gray()
            for anchor in limits.stop_anchors:
                if self.vision._find_template(screen, anchor):
                    logger.critical("🛑 Аварийная остановка: Обнаружен стоп-якорь!")
                    return True

        return False

    def _discover_current_state(self) -> str:
        logger.info("🔍 Запущен поиск состояния (Auto-Discovery)...")
        for state_name, state_config in self.config.states.items():
            if not getattr(state_config, 'is_discoverable', True):
                continue
            if not state_config.anchors:
                continue
                
            if self.vision.verify_anchors(state_config.anchors):
                logger.info("✅ Успех: Автомат распознал себя в состоянии '%s'", state_name)
                return state_name
                
        logger.error("❌ Авто-обнаружение провалилось. Неизвестный экран.")
        return "error_state"

    def run(self) -> None:
        logger.info("--- Запуск OpticFSM: %s ---", self.config.engine_settings.project_name)

        while True:
            if self.current_state_name == "auto":
                discovered_state = self._discover_current_state()
                if discovered_state == "error_state":
                    logger.critical("Невозможно продолжить работу. Скрипт остановлен.")
                    break
                
                self.current_state_name = discovered_state
                self.state_enter_time = time.time()
                self.last_wait_log_time = 0.0
                continue

            if self._check_session_limits():
                uptime = time.time() - self.session_start_time
                logger.info("🏁 Сессия завершена. Итераций: %d, Время работы: %.1f сек.", 
                            self.iterations_completed, uptime)
                break

            current_state = self.config.states.get(self.current_state_name)
            if not current_state:
                break

            if current_state.is_terminal:
                break

            elapsed = time.time() - self.state_enter_time
            if elapsed > self.config.engine_settings.global_timeout_sec:
                logger.warning("Таймаут в состоянии '%s'. Попытка самовосстановления...", self.current_state_name)
                self.current_state_name = "auto"
                continue

            if current_state.anchors:
                if not self.vision.verify_anchors(current_state.anchors):
                    if time.time() - self.last_wait_log_time > 5.0:
                        logger.info("👀 [%s] Ожидание якорей (экран перекрыт или грузится)...", self.current_state_name)
                        self.last_wait_log_time = time.time()
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
                if time.time() - self.last_wait_log_time > 5.0:
                    targets = [t.target_template for t in current_state.transitions if t.target_template]
                    logger.info("⏳ [%s] Якоря найдены. Ищу цели клика: %s", self.current_state_name, targets)
                    self.last_wait_log_time = time.time()
                time.sleep(0.1)