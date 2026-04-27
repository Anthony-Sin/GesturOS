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
        self.shared_state = self.cursor_engine.shared_state
        self.running = False

        # Do not create mss.mss() here; it must be created in the worker thread.
        self.search_radius = self.config.get("MAGNETISM_SEARCH_RADIUS", 150)
        self.trigger_distance = self.config.get("MAGNETISM_TRIGGER_DISTANCE", 40)
        self.pull_strength = self.config.get("MAGNETISM_PULL_STRENGTH", 0.6)

        self.sniper_switch_threshold_px = int(self.config.get("SNIPER_SWITCH_THRESHOLD_PX", 60))
        self.sniper_candidate_distance = int(
            self.config.get("SNIPER_CANDIDATE_DISTANCE", max(self.trigger_distance, 70))
        )

        self._sniper_last_mode = False
        self._sniper_anchor_point = None
        self._sniper_selected_index = 0
        self._sniper_last_switch_time = 0

    def _reset_sniper_state(self):
        self._sniper_anchor_point = None
        self._sniper_selected_index = 0
        self._sniper_last_switch_time = 0
        self.shared_state["magnet_target_bbox"] = None
        self.shared_state["magnet_snap_target"] = None
        self.shared_state["sniper_candidate_index"] = 0
        self.shared_state["sniper_candidate_count"] = 0

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        logger.info("Predictive Target Magnetism started.")
        return thread

    def stop(self):
        self.running = False

    def _run(self):
        # Import and instantiate mss inside this thread.
        import mss

        sct = mss.mss()

        kernel = np.ones((5, 5), np.uint8)

        # HSV bounds for pure #00FF00 in OpenCV scale.
        lower_green = np.array([55, 200, 200])
        upper_green = np.array([65, 255, 255])

        logger.debug("Magnetism worker thread started with fresh mss instance.")

        while self.running:
            try:
                if (
                    self.shared_state.get("tracking_paused", False)
                    or self.shared_state.get("agent_active", False)
                    or self.shared_state.get("dictation_active", False)
                ):
                    self._sniper_last_mode = False
                    self._reset_sniper_state()
                    time.sleep(0.05)
                    continue

                sniper_mode_active = bool(self.shared_state.get("sniper_mode_active", False))
                if not sniper_mode_active:
                    if self._sniper_last_mode:
                        logger.info("Sniper mode OFF: magnetism disengaged.")
                    self._sniper_last_mode = False
                    self._reset_sniper_state()
                    time.sleep(0.05)
                    continue

                if not self._sniper_last_mode:
                    logger.info("Sniper mode ON: selective magnetism engaged.")
                    self._reset_sniper_state()
                    self._sniper_last_mode = True

                raw_target = self.shared_state.get("raw_nose_target")
                if raw_target:
                    mx, my = int(raw_target[0]), int(raw_target[1])
                else:
                    mx, my = pyautogui.position()

                if self._sniper_anchor_point is None:
                    self._sniper_anchor_point = (mx, my)

                monitor = {
                    "top": max(0, my - self.search_radius),
                    "left": max(0, mx - self.search_radius),
                    "width": self.search_radius * 2,
                    "height": self.search_radius * 2,
                }

                sct_img = sct.grab(monitor)
                img = np.array(sct_img)[:, :, :3]  # BGRA -> BGR

                # Mask out our own green UI box so it cannot self-lock.
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                mask_green = cv2.inRange(hsv, lower_green, upper_green)
                mask_non_green = cv2.bitwise_not(mask_green)
                img_masked = cv2.bitwise_and(img, img, mask=mask_non_green)

                gray = cv2.cvtColor(img_masked, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

                contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                center_x = mx - monitor["left"]
                center_y = my - monitor["top"]

                candidates = []
                for cnt in contours:
                    x, y, w, h = cv2.boundingRect(cnt)

                    if w < 15 or h < 10 or w > self.search_radius * 1.5:
                        continue

                    cx_local = x + w / 2
                    cy_local = y + h / 2
                    dist = ((cx_local - center_x) ** 2 + (cy_local - center_y) ** 2) ** 0.5
                    if dist > self.sniper_candidate_distance:
                        continue

                    abs_x = monitor["left"] + x
                    abs_y = monitor["top"] + y
                    candidates.append((dist, abs_x, abs_y, w, h, abs_x + w / 2, abs_y + h / 2))

                if not candidates:
                    self._sniper_selected_index = 0
                    self.shared_state["magnet_target_bbox"] = None
                    self.shared_state["magnet_snap_target"] = None
                    self.shared_state["sniper_candidate_index"] = 0
                    self.shared_state["sniper_candidate_count"] = 0
                    self._sniper_anchor_point = (mx, my)
                    time.sleep(0.05)
                    continue

                candidates.sort(key=lambda item: item[0])

                now = time.time()
                if len(candidates) > 1 and self._sniper_anchor_point is not None:
                    if now - self._sniper_last_switch_time > 0.5: # 0.5 seconds cooldown
                        anchor_x, anchor_y = self._sniper_anchor_point
                        move_dx = mx - anchor_x
                        move_dy = my - anchor_y
                        if abs(move_dx) >= self.sniper_switch_threshold_px:
                            step = 1 if move_dx > 0 else -1
                            self._sniper_selected_index = (self._sniper_selected_index + step) % len(candidates)
                            self._sniper_anchor_point = (mx, my)
                            self._sniper_last_switch_time = now
                        elif abs(move_dy) >= self.sniper_switch_threshold_px:
                            step = 1 if move_dy > 0 else -1
                            self._sniper_selected_index = (self._sniper_selected_index + step) % len(candidates)
                            self._sniper_anchor_point = (mx, my)
                            self._sniper_last_switch_time = now

                self._sniper_selected_index = max(0, min(self._sniper_selected_index, len(candidates) - 1))
                _, abs_x, abs_y, w, h, target_cx, target_cy = candidates[self._sniper_selected_index]

                self.shared_state["sniper_candidate_count"] = len(candidates)
                self.shared_state["sniper_candidate_index"] = self._sniper_selected_index + 1
                self.shared_state["magnet_target_bbox"] = (abs_x, abs_y, w, h)
                self.shared_state["magnet_snap_target"] = (target_cx, target_cy)

                time.sleep(0.05)  # ~20 FPS

            except Exception as e:
                logger.error(f"Magnetism loop error: {e}", exc_info=True)
                time.sleep(0.5)

        try:
            sct.close()
        except Exception:
            pass
        logger.debug("Magnetism worker thread exited cleanly.")
