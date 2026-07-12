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

        # Таймеры и счетчики сессии
        self.state_enter_time = time.time()
        self.session_start_time = time.time()
        self.iterations_completed = 0

    def _change_state(self, new_state_name: str) -> None:
        """Изменяет текущее состояние, сбрасывает таймер и считает итерации."""
        logger.info("Смена состояния: [%s] ---> [%s]", self.current_state_name, new_state_name)
        self.current_state_name = new_state_name
        self.state_enter_time = time.time()

        # Учет завершенных итераций строго в момент перехода
        limits = self.config.engine_settings.session_limits
        if limits and new_state_name == limits.iteration_trigger_state:
            self.iterations_completed += 1
            max_iter = limits.max_iterations if limits.max_iterations else "∞"
            logger.info("✅ Итерация завершена! Выполнено: %s/%s", self.iterations_completed, max_iter)

    def _check_session_limits(self) -> bool:
        """Проверяет глобальные условия остановки. Возвращает True, если нужно прервать работу."""
        limits = self.config.engine_settings.session_limits
        if not limits:
            return False

        # 1. Проверка по времени (max_runtime_sec)
        if limits.max_runtime_sec:
            total_elapsed = time.time() - self.session_start_time
            if total_elapsed > limits.max_runtime_sec:
                logger.info("🛑 Остановка: Достигнут лимит времени сессии (%s сек).", limits.max_runtime_sec)
                return True

        # 2. Проверка по количеству итераций
        if limits.max_iterations and self.iterations_completed >= limits.max_iterations:
            logger.info("🛑 Остановка: Выполнено максимальное количество итераций (%s).", limits.max_iterations)
            return True

        # 3. Проверка на визуальные стоп-триггеры (например, капча)
        if limits.stop_anchors:
            screen = self.vision._get_screenshot_gray()
            for anchor in limits.stop_anchors:
                if self.vision._find_template(screen, anchor):
                    logger.critical("🛑 Аварийная остановка: Обнаружен стоп-якорь на экране (%s)!", anchor)
                    return True

        return False

    def run(self) -> None:
        """Запускает бесконечный цикл обработки автомата."""
        logger.info("--- Запуск OpticFSM: %s ---", self.config.engine_settings.project_name)

        while True:
            # 1. Проверка лимитов сессии
            if self._check_session_limits():
                uptime = time.time() - self.session_start_time
                logger.info("🏁 Сессия завершена. Итераций: %d, Время работы: %.1f сек.", 
                            self.iterations_completed, uptime)
                break

            # 2. Получение текущего состояния
            current_state = self.config.states.get(self.current_state_name)
            if not current_state:
                logger.error("Критическая ошибка: Состояние '%s' не найдено!", self.current_state_name)
                break

            # 3. Терминальное состояние
            if current_state.is_terminal:
                logger.info("Достигнуто терминальное состояние '%s'. Завершение.", self.current_state_name)
                break

            # 4. Проверка Watchdog таймаута
            elapsed = time.time() - self.state_enter_time
            if elapsed > self.config.engine_settings.global_timeout_sec:
                logger.warning("Таймаут в состоянии '%s' (%.1f сек).", self.current_state_name, elapsed)
                self._change_state("error_state")
                continue

            # 5. Проверка якорей (видим ли мы нужный экран?)
            if current_state.anchors:
                if not self.vision.verify_anchors(current_state.anchors):
                    time.sleep(0.5)
                    continue

            # 6. Оценка и выполнение переходов
            transition_executed = False
            for transition in current_state.transitions:
                if self.vision.execute_transition(transition):
                    # Если клик/ожидание прошло успешно, вызываем задержку
                    self.vision.settings.delay.execute(base_msec=transition.delay_msec)
                    # Меняем состояние
                    self._change_state(transition.next_state)
                    transition_executed = True
                    break

            # 7. Пауза холостого хода
            if not transition_executed:
                time.sleep(0.1)