import pyautogui
import queue
import time
import threading
import cv2
import numpy as np
import math

class SystemNavigator:
    def __init__(self, data_queue: queue.Queue):
        self.data_queue = data_queue
        self.running = False

        # Cooldowns to prevent spamming macros
        self.last_action_time = 0
        self.cooldown = 1.5 # seconds

        # Thresholds for extreme head poses (in degrees)
        self.yaw_threshold = 30.0   # Looking significantly left/right
        self.pitch_threshold = 20.0 # Looking significantly up/down
        self.roll_threshold = 30.0  # Tilting head

        # 3D model points (standard face model to match MediaPipe landmarks)
        # Using a minimal set of points: Nose tip, Chin, Left Eye, Right Eye, Left Mouth, Right Mouth
        self.model_points = np.array([
            (0.0, 0.0, 0.0),             # Nose tip
            (0.0, -330.0, -65.0),        # Chin
            (-225.0, 170.0, -135.0),     # Left Eye
            (225.0, 170.0, -135.0),      # Right Eye
            (-150.0, -150.0, -125.0),    # Left Mouth
            (150.0, -150.0, -125.0)      # Right Mouth
        ], dtype=np.float64)

        # Corresponding indices in MediaPipe face mesh
        # 1: Nose tip
        # 152: Chin
        # 33: Left eye (outer corner)
        # 263: Right eye (outer corner)
        # 61: Left mouth corner
        # 291: Right mouth corner
        self.landmark_indices = [1, 152, 33, 263, 61, 291]

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run)
        thread.start()
        print("System Navigator started.")
        return thread

    def stop(self):
        self.running = False

    def _get_head_pose(self, landmarks):
        # We need pseudo image dimensions. Let's assume a standard 640x480 aspect ratio mapping
        img_w, img_h = 640, 480

        image_points = []
        for idx in self.landmark_indices:
            lm = landmarks[idx]
            # Convert normalized coordinates to pixel coordinates
            x, y = int(lm.x * img_w), int(lm.y * img_h)
            image_points.append((x, y))

        image_points = np.array(image_points, dtype=np.float64)

        # Camera internals
        focal_length = img_w
        center = (img_w / 2, img_h / 2)
        camera_matrix = np.array(
            [[focal_length, 0, center[0]],
             [0, focal_length, center[1]],
             [0, 0, 1]], dtype=np.float64
        )
        dist_coeffs = np.zeros((4, 1)) # Assuming no lens distortion

        success, rotation_vector, translation_vector = cv2.solvePnP(
            self.model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return None

        # Convert rotation vector to rotation matrix
        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)

        # Convert rotation matrix to Euler angles using projection matrix decomposition
        # Create a 3x4 projection matrix from the rotation matrix and translation vector
        proj_matrix = np.hstack((rotation_matrix, translation_vector))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)

        # euler_angles format: [pitch, yaw, roll] in degrees
        pitch = euler_angles[0][0]
        yaw = euler_angles[1][0]
        roll = euler_angles[2][0]

        return pitch, yaw, roll

    def _run(self):
        while self.running:
            try:
                payload = self.data_queue.get(timeout=0.1)
                landmarks = payload['landmarks']

                pose = self._get_head_pose(landmarks)
                if not pose:
                    continue

                pitch, yaw, roll = pose
                now = time.time()

                # Check for extreme poses
                if now - self.last_action_time > self.cooldown:
                    # Pitch: positive typically means looking down, negative looking up.
                    # OpenCV conventions can vary depending on exact 3D model used. Let's assume standard right-handed.
                    if yaw > self.yaw_threshold:
                        print("System Navigator: Yaw Right detected. Minimizing window.")
                        # Windows: Win+D or Win+M. Linux: Ctrl+Super+D often. Pyautogui supports win+d
                        pyautogui.hotkey('win', 'd')
                        self.last_action_time = now
                    elif yaw < -self.yaw_threshold:
                        print("System Navigator: Yaw Left detected. Alt+Tab.")
                        pyautogui.hotkey('alt', 'tab')
                        self.last_action_time = now
                    elif pitch > self.pitch_threshold:
                        print("System Navigator: Pitch Down detected. (No action bound)")
                        pass
                    elif pitch < -self.pitch_threshold:
                        print("System Navigator: Pitch Up detected. Opening terminal.")
                        # Common terminal shortcut in Ubuntu/Debian: ctrl+alt+t
                        pyautogui.hotkey('ctrl', 'alt', 't')
                        self.last_action_time = now

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in SystemNavigator: {e}")
