import threading
import time
import numpy as np
import cv2
import pyautogui
import logging
from tools.interfaces import BaseMagnetismEngine

logger = logging.getLogger(__name__)


class TargetMagnetism(BaseMagnetismEngine):
    def __init__(self, cursor_engine, config: dict):
        self.cursor_engine = cursor_engine
        self.config = config
        self.running = False

        # ── DO NOT create mss.mss() here. ──────────────────────────────────
        # mss uses a per-thread display context on Windows. Creating it in
        # __init__ (main thread) and then calling .grab() from the worker
        # thread causes a silent context mismatch that deadlocks after ~60-120s,
        # especially when PyQt6 is also active. Always create it inside _run().

        self.search_radius    = self.config.get("MAGNETISM_SEARCH_RADIUS",   150)
        self.trigger_distance = self.config.get("MAGNETISM_TRIGGER_DISTANCE",  40)
        self.pull_strength    = self.config.get("MAGNETISM_PULL_STRENGTH",    0.6)

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        logger.info("Predictive Target Magnetism started.")
        return thread

    def stop(self):
        self.running = False

    def _run(self):
        # Import and instantiate mss HERE — same thread that calls .grab()
        import mss
        sct = mss.mss()

        # Pre-build the morphology kernel once
        kernel = np.ones((5, 15), np.uint8)

        # Correct HSV bounds for pure #00FF00 (H=60 in OpenCV's 0-179 scale)
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
                img = np.array(sct_img)[:, :, :3]  # BGRA → BGR

                # Mask out the green bounding box we draw so it can't self-lock
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

                if best_rect:
                    abs_x     = monitor["left"] + best_rect[0]
                    abs_y     = monitor["top"]  + best_rect[1]
                    target_cx = abs_x + best_rect[2] / 2
                    target_cy = abs_y + best_rect[3] / 2

                    self.cursor_engine.shared_state["magnet_target_bbox"]  = (abs_x, abs_y, best_rect[2], best_rect[3])
                    self.cursor_engine.shared_state["magnet_snap_target"]  = (target_cx, target_cy)
                else:
                    self.cursor_engine.shared_state["magnet_target_bbox"] = None
                    self.cursor_engine.shared_state["magnet_snap_target"] = None

                time.sleep(0.05)  # ~20 FPS

            except Exception as e:
                logger.error(f"Magnetism loop error: {e}", exc_info=True)
                time.sleep(0.5)

        # Clean up mss when the loop exits
        try:
            sct.close()
        except Exception:
            pass
        logger.debug("Magnetism worker thread exited cleanly.")