import threading
import time
import mss
import numpy as np
import cv2
import pyautogui
from tools.interfaces import BaseMagnetismEngine

class TargetMagnetism(BaseMagnetismEngine):
    def __init__(self, cursor_engine, config: dict):
        self.cursor_engine = cursor_engine
        self.config = config
        self.running = False
        self.sct = mss.mss()
        self.search_radius = self.config.get("MAGNETISM_SEARCH_RADIUS", 150)
        self.trigger_distance = self.config.get("MAGNETISM_TRIGGER_DISTANCE", 40)

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        print("Predictive Target Magnetism started.")
        return thread

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                # 1. Get current mouse position
                mx, my = pyautogui.position()

                # Define bounding box for the screenshot
                monitor = {
                    "top": max(0, my - self.search_radius),
                    "left": max(0, mx - self.search_radius),
                    "width": self.search_radius * 2,
                    "height": self.search_radius * 2
                }

                # 2. Capture screen patch
                sct_img = self.sct.grab(monitor)
                # Convert to numpy array (BGRA) -> BGR -> Grayscale
                img = np.array(sct_img)
                gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

                # 3. Detect UI elements
                edges = cv2.Canny(gray, threshold1=50, threshold2=150)
                kernel = np.ones((5, 15), np.uint8)
                closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

                contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                closest_dist = float('inf')
                best_rect = None

                center_x = mx - monitor["left"]
                center_y = my - monitor["top"]

                for cnt in contours:
                    x, y, w, h = cv2.boundingRect(cnt)

                    if w < 15 or h < 10 or w > self.search_radius*1.5:
                        continue

                    cx = x + (w / 2)
                    cy = y + (h / 2)

                    dist = ((cx - center_x)**2 + (cy - center_y)**2)**0.5

                    if dist < self.trigger_distance and dist < closest_dist:
                        closest_dist = dist
                        best_rect = (x, y, w, h)

                if best_rect:
                    abs_x = monitor["left"] + best_rect[0]
                    abs_y = monitor["top"] + best_rect[1]

                    # Instead of calculating offset from CURRENT mouse (which causes feedback loop),
                    # We pass the absolute target coordinate via shared state and let CursorEngine snap.
                    # Or even simpler, calculate the offset from the BASE NOSE target.
                    # But the easiest zero-latency fix is to just tell CursorEngine exactly where to snap.

                    target_cx = abs_x + (best_rect[2] / 2)
                    target_cy = abs_y + (best_rect[3] / 2)

                    self.cursor_engine.shared_state["magnet_target_bbox"] = (abs_x, abs_y, best_rect[2], best_rect[3])
                    self.cursor_engine.shared_state["magnet_snap_target"] = (target_cx, target_cy)
                else:
                    self.cursor_engine.shared_state["magnet_target_bbox"] = None
                    self.cursor_engine.shared_state["magnet_snap_target"] = None

                time.sleep(0.05) # ~20 FPS polling

            except Exception as e:
                time.sleep(0.5)
