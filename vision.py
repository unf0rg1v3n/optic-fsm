import cv2
import numpy as np
import mss
import pygetwindow as pgw
import pyautogui
import ctypes
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger("OpticFSM.Vision")

class VisionAdapter:
    def __init__(self, settings):
        """
        Инициализация модуля зрения. Настраивает DPI, находит окно 
        и высчитывает зону интереса (ROI).
        """
        self.settings = settings
        self.sct = mss.mss()
        self.roi = None
        self.window = None

        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception as e:
            logger.warning(f"Не удалось настроить DPI Awareness: {e}")

        self._calibrate_window()

    def _calibrate_window(self):
        """Ищет окно по заголовку и формирует чистый ROI без рамок."""
        windows = pgw.getWindowsWithTitle(self.settings.target_window_title)
        if not windows:
            raise ValueError(f"Окно '{self.settings.target_window_title}' не найдено!")
        
        self.window = windows[0]
        
        if self.window.isMinimized:
            self.window.restore()
        self.window.activate()
        
        time.sleep(0.5)

        border_offset = 8
        title_bar_height = 31
        
        self.roi = {
            "top": self.window.top + title_bar_height,
            "left": self.window.left + border_offset,
            "width": self.window.width - (border_offset * 2),
            "height": self.window.height - title_bar_height - border_offset
        }
        logger.info(f"Калибровка успешна. ROI: {self.roi}")

    def _get_screenshot_gray(self) -> np.ndarray:
        """Делает скриншот ROI и сразу переводит в оттенки серого."""
        sct_img = self.sct.grab(self.roi)
        img = np.array(sct_img)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

    def _find_template(self, screen_gray: np.ndarray, template_path: str) -> Optional[Tuple[int, int]]:
        """
        Ищет шаблон на ч/б скриншоте.
        Возвращает абсолютные координаты (X, Y) для мыши или None.
        """
        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.error(f"Файл шаблона не найден: {template_path}")
            return None

        res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= self.settings.confidence_threshold:
            h, w = template.shape
            
            center_x_local = max_loc[0] + w // 2
            center_y_local = max_loc[1] + h // 2
            
            abs_x = self.roi["left"] + center_x_local
            abs_y = self.roi["top"] + center_y_local
            
            return (abs_x, abs_y)
            
        return None

    def verify_anchors(self, anchors: list[str]) -> bool:
        """
        Проверяет наличие всех якорей на экране (Логическое И).
        Используется ядром для подтверждения состояния.
        """
        if not anchors:
            return True
            
        screen = self._get_screenshot_gray()
        for anchor in anchors:
            if not self._find_template(screen, anchor):
                return False
        return True

    def execute_transition(self, transition) -> bool:
        """
        Ищет целевой элемент перехода и выполняет действие (клик/ожидание).
        """
        if transition.action == "wait":
            return True 

        screen = self._get_screenshot_gray()
        coords = self._find_template(screen, transition.target_template)
        
        if not coords:
            return False

        x, y = coords
        
        if transition.action == "click":
            pyautogui.click(x, y)
        elif transition.action == "double_click":
            pyautogui.doubleClick(x, y)
            
        logger.info(f"Действие {transition.action.upper()} по {transition.target_template}")
        return True

    def perform_sleep(self, delay_msec: Optional[int] = None):
        """Делегирует паузу объекту стратегии из настроек."""
        self.settings.delay.execute(base_msec=delay_msec)