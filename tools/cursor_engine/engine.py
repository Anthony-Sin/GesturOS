import pyautogui
import queue
import time
import threading

class CursorEngine:
    def __init__(self, data_queue: queue.Queue):
        self.data_queue = data_queue
        self.running = False

        # Disable failsafe to prevent edge-case crashes
        pyautogui.FAILSAFE = False

        self.screen_w, self.screen_h = pyautogui.size()

        # Exponential Moving Average state
        self.ema_x = None
        self.ema_y = None
        self.alpha = 0.3 # Smoothing factor: lower = smoother, higher = more responsive

        # Active Zone Multiplier Configuration
        # We assume the user's nose will mostly move within a central bounding box of the camera frame.
        # e.g. center x +/- 0.1, center y +/- 0.1
        self.active_zone_x_center = 0.5
        self.active_zone_y_center = 0.5
        self.active_zone_width = 0.2  # Map 20% of the camera width to the full screen
        self.active_zone_height = 0.2 # Map 20% of the camera height to the full screen

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run)
        thread.start()
        print(f"Cursor Engine started. Screen resolution: {self.screen_w}x{self.screen_h}")
        return thread

    def stop(self):
        self.running = False

    def _normalize_to_active_zone(self, val, center, size):
        # Calculate min and max bounds for the active zone
        min_bound = center - (size / 2)
        max_bound = center + (size / 2)

        # Clamp the value to the active zone bounds
        val_clamped = max(min_bound, min(val, max_bound))

        # Normalize to [0, 1] within the active zone
        normalized = (val_clamped - min_bound) / size
        return normalized

    def _run(self):
        while self.running:
            try:
                # Use a small timeout so we can periodically check self.running
                payload = self.data_queue.get(timeout=0.1)

                if payload.get('is_locked', False):
                    continue

                nose_tip = payload['nose_tip']

                raw_x = nose_tip['x']
                raw_y = nose_tip['y']

                # Apply Active Zone scaling
                # Note: Webcam X axis is usually mirrored. Let's assume raw_x needs to be inverted.
                scaled_x = self._normalize_to_active_zone(1.0 - raw_x, self.active_zone_x_center, self.active_zone_width)
                scaled_y = self._normalize_to_active_zone(raw_y, self.active_zone_y_center, self.active_zone_height)

                # Map to screen coordinates
                target_x = scaled_x * self.screen_w
                target_y = scaled_y * self.screen_h

                # Apply EMA
                if self.ema_x is None or self.ema_y is None:
                    self.ema_x = target_x
                    self.ema_y = target_y
                else:
                    self.ema_x = self.alpha * target_x + (1 - self.alpha) * self.ema_x
                    self.ema_y = self.alpha * target_y + (1 - self.alpha) * self.ema_y

                # Move physical mouse
                try:
                    pyautogui.moveTo(int(self.ema_x), int(self.ema_y))
                except Exception as e:
                    print(f"Failed to move mouse: {e}")

            except queue.Empty:
                continue
