import threading
import time
import numpy as np
import cv2
import pyautogui
import logging
import math # Added as requested
from tools.interfaces import BaseMagnetismEngine

logger = logging.getLogger(__name__)

# --- Paste your OneEuroFilter class here ---
class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def __call__(self, x, t):
        if self.t_prev is None:
            self.x_prev = x
            self.t_prev = t
            return x
        t_e = t - self.t_prev
        if t_e <= 0:
            return self.x_prev
        a_d = self.smoothing_factor(t_e, self.d_cutoff)
        dx = (x - self.x_prev) / t_e
        dx_hat = self.exponential_smoothing(a_d, dx, self.dx_prev)
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self.smoothing_factor(t_e, cutoff)
        x_hat = self.exponential_smoothing(a, x, self.x_prev)
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat

    def smoothing_factor(self, t_e, cutoff):
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)

    def exponential_smoothing(self, a, x, x_prev):
        return a * x + (1 - a) * x_prev
# -------------------------------------------

class TargetMagnetism(BaseMagnetismEngine):
    def __init__(self, cursor_engine, config: dict):
        self.cursor_engine = cursor_engine
        self.config = config
        self.running = False

        self.search_radius    = self.config.get("MAGNETISM_SEARCH_RADIUS",   150)
        self.trigger_distance = self.config.get("MAGNETISM_TRIGGER_DISTANCE",  40)
        self.pull_strength    = self.config.get("MAGNETISM_PULL_STRENGTH",    0.6)
        
        # Initialize the filters for X and Y coordinates
        self.filter_x = OneEuroFilter(min_cutoff=0.1, beta=0.05)
        self.filter_y = OneEuroFilter(min_cutoff=0.1, beta=0.05)

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        logger.info("Predictive Target Magnetism started.")
        return thread

    def stop(self):
        self.running = False

    def _run(self):
        import mss
        sct = mss.mss()

        # FIX: Changed from (5, 15) to (5, 5) so it doesn't merge multiple items horizontally
        kernel = np.ones((5, 5), np.uint8) 

        lower_green = np.array([55, 200, 200])
        upper_green = np.array([65, 255, 255])

        logger.debug("Magnetism worker thread started with fresh mss instance.")

        while self.running:
            try:
                raw_target = self.cursor_engine.shared_state.get("raw_nose_target")
                if raw_target:
                    mx, my = int(raw_target[0]), int(raw_target[1])
                else:
                    mx, my = pyautogui.position()

                monitor = {
                    "top":    max(0, my - self.search_radius),
                    "left":   max(0, mx - self.search_radius),
                    "width":  self.search_radius * 2,
                    "height": self.search_radius * 2,
                }

                sct_img = sct.grab(monitor)
                img = np.array(sct_img)[:, :, :3]

                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                mask_green     = cv2.inRange(hsv, lower_green, upper_green)
                mask_non_green = cv2.bitwise_not(mask_green)
                img_masked     = cv2.bitwise_and(img, img, mask=mask_non_green)

                gray   = cv2.cvtColor(img_masked, cv2.COLOR_BGR2GRAY)
                edges  = cv2.Canny(gray, 50, 150)
                closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

                contours, _ = cv2.findContours(
                    closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )

                center_x = mx - monitor["left"]
                center_y = my - monitor["top"]

                closest_dist = float("inf")
                best_rect    = None

                for cnt in contours:
                    x, y, w, h = cv2.boundingRect(cnt)

                    if w < 15 or h < 10 or w > self.search_radius * 1.5:
                        continue

                    cx   = x + w / 2
                    cy   = y + h / 2
                    dist = ((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5

                    if dist < self.trigger_distance and dist < closest_dist:
                        closest_dist = dist
                        best_rect    = (x, y, w, h)

                current_time = time.time()

                if best_rect:
                    abs_x     = monitor["left"] + best_rect[0]
                    abs_y     = monitor["top"]  + best_rect[1]
                    raw_target_cx = abs_x + best_rect[2] / 2
                    raw_target_cy = abs_y + best_rect[3] / 2

                    # Apply the OneEuroFilter to the raw coordinates
                    filtered_cx = self.filter_x(raw_target_cx, current_time)
                    filtered_cy = self.filter_y(raw_target_cy, current_time)

                    self.cursor_engine.shared_state["magnet_target_bbox"]  = (abs_x, abs_y, best_rect[2], best_rect[3])
                    self.cursor_engine.shared_state["magnet_snap_target"]  = (filtered_cx, filtered_cy)
                else:
                    # Reset the filter's time tracking so it doesn't jump wildly when re-acquiring a target
                    self.filter_x.t_prev = None
                    self.filter_y.t_prev = None
                    
                    self.cursor_engine.shared_state["magnet_target_bbox"] = None
                    self.cursor_engine.shared_state["magnet_snap_target"] = None

                time.sleep(0.05) 

            except Exception as e:
                logger.error(f"Magnetism loop error: {e}", exc_info=True)
                time.sleep(0.5)

        try:
            sct.close()
        except Exception:
            pass
        logger.debug("Magnetism worker thread exited cleanly.")