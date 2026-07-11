"""
Модуль компьютерного зрения.
Отвечает за работу с экраном, поиск шаблонов и системные клики.
"""
import ctypes
import logging
import time
from typing import List, Optional, Tuple

import cv2
import mss
import numpy as np
import pyautogui
import pygetwindow as pgw

from configuration import Action, EngineSettings, TransitionConfig

logger = logging.getLogger(__name__)


class VisionAdapter:
    """Интерфейс для работы с графическим интерфейсом ОС и OpenCV."""

    def __init__(self, settings: EngineSettings):
        self.settings = settings
        self.sct = mss.mss()
        self.roi = None
        self.window = None

        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Не удалось настроить DPI Awareness: %s", exc)

        self._calibrate_window()

    def _calibrate_window(self) -> None:
        """Ищет окно тестируемого приложения и вычисляет его координаты."""
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
        logger.info("Окно откалибровано. ROI: %s", self.roi)

    def _get_screenshot_gray(self) -> np.ndarray:
        """Создает скриншот зоны интереса в оттенках серого."""
        sct_img = self.sct.grab(self.roi)
        img = np.array(sct_img)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

    def _find_template(self, screen: np.ndarray, template_path: str) -> Optional[Tuple[int, int]]:
        """Ищет шаблон на изображении экрана."""
        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.error("Шаблон не найден: %s", template_path)
            return None

        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= self.settings.confidence_threshold:
            height, width = template.shape
            center_x_local = max_loc[0] + width // 2
            center_y_local = max_loc[1] + height // 2
            abs_x = self.roi["left"] + center_x_local
            abs_y = self.roi["top"] + center_y_local
            return (abs_x, abs_y)

        return None

    def verify_anchors(self, anchors: List[str]) -> bool:
        """Проверяет присутствие микро-якорей на экране."""
        if not anchors:
            return True
        screen = self._get_screenshot_gray()
        for anchor in anchors:
            if not self._find_template(screen, anchor):
                return False
        return True

    def execute_transition(self, transition: TransitionConfig) -> bool:
        """Осуществляет поиск цели и производит физическое действие (клик/ожидание)."""
        if transition.action == Action.WAIT:
            return True

        screen = self._get_screenshot_gray()
        coords = self._find_template(screen, transition.target_template)

        if not coords:
            return False

        abs_x, abs_y = coords
        if transition.action == Action.CLICK:
            pyautogui.click(abs_x, abs_y)
        elif transition.action == Action.DOUBLE_CLICK:
            pyautogui.doubleClick(abs_x, abs_y)

        logger.info("Выполнено действие: %s по %s", transition.action, transition.target_template)
        return True
