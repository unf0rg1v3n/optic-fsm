"""
Модуль компьютерного зрения.
Отвечает за работу с экраном, поиск шаблонов и системные клики.
"""
import ctypes
import logging
import time
from ctypes import wintypes
from typing import List, Optional, Tuple

import cv2
import mss
import numpy as np
import pyautogui
import pygetwindow as pgw

from configuration import Action, EngineSettings, TransitionConfig

logger = logging.getLogger(__name__)

# --- Определение структур Windows API для получения чистых координат ---
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class VisionAdapter:
    """Интерфейс для работы с графическим интерфейсом ОС и OpenCV."""

    def __init__(self, settings: EngineSettings):
        self.settings = settings
        self.sct = mss.mss()
        self.roi = None
        self.window = None
        self.cached_scale = 1.0
        
        self._calibrate_window()
        self._init_scale_cache()
    
    def _init_scale_cache(self) -> None:
        """
        Предварительно вычисляет масштаб, если известно базовое разрешение
        монитора, на котором создавались шаблоны.
        """
        scale_cfg = self.settings.scale_settings
        res = scale_cfg.parsed_resolution
        if res:
            base_w, base_h = res
            current_w = ctypes.windll.user32.GetSystemMetrics(0)
            
            if current_w > 0 and base_w > 0:
                self.cached_scale = current_w / base_w
                logger.info("⚙️ Разрешение %sx%s. Расчетный стартовый масштаб: %.2f", 
                            base_w, base_h, self.cached_scale)

    def _enable_dpi_awareness(self) -> None:
        """Включает строгий режим физических пикселей для всех мониторов (Windows 10+)."""
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:  # pylint: disable=broad-exception-caught
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("Не удалось настроить DPI Awareness: %s", exc)

    def _calibrate_window(self) -> None:
        """
        Ищет окно тестируемого приложения и вычисляет координаты его клиентской области 
        (без системных рамок и заголовков) через прямой вызов WinAPI.
        """
        windows = pgw.getWindowsWithTitle(self.settings.target_window_title)
        if not windows:
            raise ValueError(f"Окно '{self.settings.target_window_title}' не найдено!")

        self.window = windows[0]
        if self.window.isMinimized:
            self.window.restore()
        self.window.activate()
        time.sleep(0.5)

        hwnd = self.window._hWnd  # pylint: disable=protected-access

        client_rect = RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(client_rect))

        pt_topleft = POINT(client_rect.left, client_rect.top)
        pt_bottomright = POINT(client_rect.right, client_rect.bottom)
        
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt_topleft))
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt_bottomright))

        self.roi = {
            "top": pt_topleft.y,
            "left": pt_topleft.x,
            "width": pt_bottomright.x - pt_topleft.x,
            "height": pt_bottomright.y - pt_topleft.y
        }
        
        logger.info("Окно откалибровано через WinAPI. ROI: %s", self.roi)

    def _get_screenshot_gray(self) -> np.ndarray:
        sct_img = self.sct.grab(self.roi)
        img = np.array(sct_img)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

    def _find_template(self, screen: np.ndarray, template_path: str) -> Optional[Tuple[int, int]]:
        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.error("Шаблон не найден: %s", template_path)
            return None

        t_height, t_width = template.shape

        if self.cached_scale > 0:
            new_width = int(t_width * self.cached_scale)
            new_height = int(t_height * self.cached_scale)
            
            if new_width > 0 and new_height > 0 and new_height <= screen.shape[0] and new_width <= screen.shape[1]:
                resized = cv2.resize(template, (new_width, new_height), interpolation=cv2.INTER_AREA)
                res = cv2.matchTemplate(screen, resized, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                
                if max_val >= self.settings.confidence_threshold:
                    center_x = max_loc[0] + new_width // 2
                    center_y = max_loc[1] + new_height // 2
                    return (self.roi["left"] + center_x, self.roi["top"] + center_y)

        best_match = None
        scale_cfg = self.settings.scale_settings
        
        scales = np.arange(scale_cfg.min_scale, scale_cfg.max_scale + (scale_cfg.scale_step / 2), scale_cfg.scale_step)[::-1]
        
        for scale in scales:
            new_width = int(t_width * scale)
            new_height = int(t_height * scale)
            
            if new_width <= 0 or new_height <= 0 or new_height > screen.shape[0] or new_width > screen.shape[1]:
                continue

            resized = cv2.resize(template, (new_width, new_height), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(screen, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if best_match is None or max_val > best_match["val"]:
                best_match = {
                    "val": max_val, "loc": max_loc, 
                    "scale": scale, "width": new_width, "height": new_height
                }

        if best_match and best_match["val"] >= self.settings.confidence_threshold:
            if abs(self.cached_scale - best_match["scale"]) > 0.01:
                logger.info("📐 Масштаб интерфейса скорректирован пирамидально: %.2f", best_match["scale"])
                self.cached_scale = best_match["scale"]
                
            center_x = best_match["loc"][0] + best_match["width"] // 2
            center_y = best_match["loc"][1] + best_match["height"] // 2
            return (self.roi["left"] + center_x, self.roi["top"] + center_y)

        return None

    def verify_anchors(self, anchors: List[str]) -> bool:
        if not anchors:
            return True
        screen = self._get_screenshot_gray()
        for anchor in anchors:
            if not self._find_template(screen, anchor):
                return False
        return True

    def execute_transition(self, transition: TransitionConfig) -> bool:
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