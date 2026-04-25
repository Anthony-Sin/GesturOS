import cv2
import mediapipe as mp
import time
import queue
import urllib.request
import os

from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = 'face_landmarker.task'
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'

def download_model_if_missing():
    if not os.path.exists(MODEL_PATH):
        print("Downloading Face Landmarker model...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Download complete.")

class VisionPipeline:
    def __init__(self, data_queue: queue.Queue, target_fps: int = 30):
        self.data_queue = data_queue
        self.target_fps = target_fps
        self.frame_duration = 1.0 / target_fps
        self.running = False

        download_model_if_missing()

        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            num_faces=1,
            running_mode=vision.RunningMode.VIDEO
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)

        # Locking mechanism variables
        self.is_locked = False
        self.anchor_point = None
        self.anchor_start_time = 0
        self.lock_duration_threshold = 10.0  # seconds for dragging lock
        self.movement_threshold = 0.015      # tight threshold for holding still
        self.breakout_threshold = 0.08       # Larger movement required to break out of lock (drop item)

    def start(self):
        self.running = True
        cap = cv2.VideoCapture(0)

        # If camera cannot be opened (e.g. headless environment), log and exit gracefully
        if not cap.isOpened():
            print("Warning: Could not open video capture. Stopping vision pipeline.")
            self.running = False
            return

        print("Vision pipeline started.")
        while self.running:
            start_time = time.time()

            success, frame = cap.read()
            if not success:
                print("Ignoring empty camera frame.")
                continue

            # Convert the frame received from OpenCV to a MediaPipe’s Image object.
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            # The timestamp must be monotonically increasing.
            timestamp_ms = int(time.time() * 1000)

            detection_result = self.detector.detect_for_video(mp_image, timestamp_ms)

            if detection_result.face_landmarks:
                landmarks = detection_result.face_landmarks[0]
                blendshapes = detection_result.face_blendshapes[0] if detection_result.face_blendshapes else []

                # Extract nose tip (landmark 1 is often used, sometimes 4 depending on the specific topology, we'll use 1)
                # Note: MediaPipe coordinates are normalized [0.0, 1.0]
                nose_tip = landmarks[1]

                # Extract relevant blendshapes into a fast dict
                blendshape_dict = {cat.category_name: cat.score for cat in blendshapes}

                # --- Locking Mechanism Logic ---
                current_time = time.time()

                if self.anchor_point is None:
                    self.anchor_point = {'x': nose_tip.x, 'y': nose_tip.y}
                    self.anchor_start_time = current_time
                else:
                    # Calculate distance from anchor
                    dx = nose_tip.x - self.anchor_point['x']
                    dy = nose_tip.y - self.anchor_point['y']
                    distance = (dx**2 + dy**2)**0.5

                    if not self.is_locked:
                        # Check if we should lock
                        if distance > self.movement_threshold:
                            # Reset anchor if moved
                            self.anchor_point = {'x': nose_tip.x, 'y': nose_tip.y}
                            self.anchor_start_time = current_time
                        else:
                            # Check if duration has passed
                            if (current_time - self.anchor_start_time) >= self.lock_duration_threshold:
                                self.is_locked = True
                                print("Pipeline: Interface LOCKED.")
                    else:
                        # We are locked. Check if we should unlock (breakout)
                        if distance > self.breakout_threshold:
                            self.is_locked = False
                            print("Pipeline: Interface UNLOCKED.")
                            self.anchor_point = {'x': nose_tip.x, 'y': nose_tip.y}
                            self.anchor_start_time = current_time

                payload = {
                    'timestamp': timestamp_ms,
                    'nose_tip': {'x': nose_tip.x, 'y': nose_tip.y, 'z': nose_tip.z},
                    'blendshapes': blendshape_dict,
                    'landmarks': landmarks, # Passing all landmarks for the navigator to use
                    'frame': cv2.flip(frame, 1), # Add a flipped copy of the frame for the UI
                    'is_locked': self.is_locked
                }

                # Non-blocking put
                try:
                    self.data_queue.put_nowait(payload)
                except queue.Full:
                    pass # Drop frame if queue is full to maintain real-time performance

            # Throttle to target FPS
            elapsed = time.time() - start_time
            sleep_time = self.frame_duration - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()
        self.detector.close()
        print("Vision pipeline stopped.")

    def stop(self):
        self.running = False
