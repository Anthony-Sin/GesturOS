import threading
import time
import mss
import numpy as np
import cv2
import pyautogui

class TargetMagnetism:
    def __init__(self, cursor_engine):
        self.cursor_engine = cursor_engine
        self.running = False
        self.sct = mss.mss()
        self.search_radius = 150 # Radius in pixels around cursor to look for targets
        self.magnet_pull_strength = 0.6 # Multiplier for how hard it snaps to the center
        self.trigger_distance = 40 # Distance within which magnetism activates

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        print("Predictive Target Magnetism started.")
        return thread

    def stop(self):
        self.running = False

    def _run(self):
        # We run this on a separate thread at roughly 10-15 FPS to save CPU,
        # it doesn't need to be 60 FPS.
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

                # 3. Detect UI elements (Buttons/Links/Textboxes usually have sharp edges)
                # Use Canny edge detection
                edges = cv2.Canny(gray, threshold1=50, threshold2=150)

                # Morphological closing to group text/icons into solid blocks
                kernel = np.ones((5, 15), np.uint8) # wider than tall for text lines/buttons
                closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

                # Find contours (bounding boxes of UI elements)
                contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                closest_dist = float('inf')
                best_pull_x = 0
                best_pull_y = 0

                # Center of the captured patch (which corresponds to our mouse position)
                # Need to account for clamping at the top/left screen edges
                center_x = mx - monitor["left"]
                center_y = my - monitor["top"]

                for cnt in contours:
                    x, y, w, h = cv2.boundingRect(cnt)

                    # Ignore tiny specks or massive structural blocks
                    if w < 15 or h < 10 or w > self.search_radius*1.5:
                        continue

                    # Calculate centroid of the detected UI element
                    cx = x + (w / 2)
                    cy = y + (h / 2)

                    # Calculate distance from mouse (center of patch)
                    dist = ((cx - center_x)**2 + (cy - center_y)**2)**0.5

                    # If it's within trigger distance and is the closest target
                    if dist < self.trigger_distance and dist < closest_dist:
                        closest_dist = dist

                        # Calculate the offset needed to snap to the center of this element
                        pull_x = cx - center_x
                        pull_y = cy - center_y

                        # We apply the pull relative to the target distance
                        best_pull_x = pull_x * self.magnet_pull_strength
                        best_pull_y = pull_y * self.magnet_pull_strength

                # Smooth the magnetic pull to avoid jerky jumping
                current_mx, current_my = self.cursor_engine.magnetic_pull

                # EMA smoothing for the magnet effect
                alpha = 0.4
                new_mx = alpha * best_pull_x + (1 - alpha) * current_mx
                new_my = alpha * best_pull_y + (1 - alpha) * current_my

                self.cursor_engine.magnetic_pull = (new_mx, new_my)

                time.sleep(0.05) # ~20 FPS polling

            except Exception as e:
                # print(f"Magnetism Error: {e}")
                time.sleep(0.5)
