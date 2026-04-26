import cv2
import mediapipe as mp
import numpy as np
import math
import time
import queue
import urllib.request
import os
import logging

from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from tools.interfaces import BaseVisionEngine

logger = logging.getLogger(__name__)

MODEL_PATH = 'face_landmarker.task'
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'

def download_model_if_missing():
    if not os.path.exists(MODEL_PATH):
        logger.info("Downloading Face Landmarker model...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        logger.info("Download complete.")

def rotation_matrix_to_angles(rotation_matrix):
    """
    Calculate Euler angles from rotation matrix.
    :param rotation_matrix: A 3x3 matrix representing the rotation
    :return: A tuple (pitch, yaw, roll) in degrees
    """
    x = math.atan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
    y = math.atan2(-rotation_matrix[2, 0], math.sqrt(rotation_matrix[2, 1] ** 2 + rotation_matrix[2, 2] ** 2))
    z = math.atan2(rotation_matrix[1, 0], rotation_matrix[0, 0])

    pitch = math.degrees(x)
    yaw = math.degrees(y)
    roll = math.degrees(z)

    return pitch, yaw, roll

class VisionPipeline(BaseVisionEngine):
    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict):
        self.data_queue = data_queue
        self.config = config
        self.shared_state = shared_state

        self.target_fps = self.config.get("TARGET_FPS", 30)
        self.frame_duration = 1.0 / self.target_fps
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
        self.lock_duration_threshold = self.config.get("LOCK_DURATION_THRESHOLD", 5.0)
        self.movement_threshold = self.config.get("LOCK_MOVEMENT_THRESHOLD", 0.025)
        self.breakout_threshold = self.config.get("LOCK_BREAKOUT_THRESHOLD", 0.12)

        # Frame diffing optimization
        self.frame_diff_threshold = self.config.get("FRAME_DIFF_THRESHOLD", 2.0)
        self.previous_frame_gray = None
        self.last_known_payload = None

        # Look away auto-pause settings
        self.look_away_pitch_thresh = self.config.get("LOOK_AWAY_PITCH_THRESHOLD", 35.0)
        self.look_away_yaw_thresh = self.config.get("LOOK_AWAY_YAW_THRESHOLD", 35.0)

    def start(self):
        self.running = True
        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            logger.warning("Could not open video capture. Stopping vision pipeline.")
            self.running = False
            return

        logger.info("Vision pipeline started.")
        while self.running:
            start_time = time.time()

            success, frame = cap.read()
            if not success:
                logger.debug("Ignoring empty camera frame.")
                continue

            timestamp_ms = int(time.time() * 1000)

            current_frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            should_process_mediapipe = True
            if self.previous_frame_gray is not None and self.last_known_payload is not None:
                diff = cv2.absdiff(current_frame_gray, self.previous_frame_gray)
                mean_diff = np.mean(diff)

                if mean_diff < self.frame_diff_threshold:
                    should_process_mediapipe = False

            landmarks = None
            blendshape_dict = {}
            nose_tip = None
            is_looking_away = False

            if not should_process_mediapipe:
                landmarks = self.last_known_payload['landmarks']
                blendshape_dict = self.last_known_payload['blendshapes']
                nose_tip_dict = self.last_known_payload['nose_tip']
                is_looking_away = self.last_known_payload.get('is_looking_away', False)

                class MockNoseTip:
                    def __init__(self, d):
                        self.x = d['x']
                        self.y = d['y']
                        self.z = d.get('z', 0)
                nose_tip = MockNoseTip(nose_tip_dict)
            else:
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                detection_result = self.detector.detect_for_video(mp_image, timestamp_ms)

                if detection_result.face_landmarks:
                    landmarks = detection_result.face_landmarks[0]
                    blendshapes = detection_result.face_blendshapes[0] if detection_result.face_blendshapes else []

                    nose_tip = landmarks[1]
                    blendshape_dict = {cat.category_name: cat.score for cat in blendshapes}

                    # Check for "Look Away" using transformation matrix
                    if detection_result.facial_transformation_matrixes:
                        matrix = detection_result.facial_transformation_matrixes[0]
                        # Extract 3x3 rotation matrix from the 4x4 matrix
                        rotation_matrix = matrix[:3, :3]
                        pitch, yaw, roll = rotation_matrix_to_angles(rotation_matrix)

                        if abs(pitch) > self.look_away_pitch_thresh or abs(yaw) > self.look_away_yaw_thresh:
                            is_looking_away = True

            if nose_tip is not None:
                current_time = time.time()

                lock_progress = 0.0
                if self.anchor_point is None:
                    self.anchor_point = {'x': nose_tip.x, 'y': nose_tip.y}
                    self.anchor_start_time = current_time
                else:
                    dx = nose_tip.x - self.anchor_point['x']
                    dy = nose_tip.y - self.anchor_point['y']
                    distance = (dx**2 + dy**2)**0.5

                    if not self.is_locked:
                        if distance > self.movement_threshold:
                            self.anchor_point = {'x': nose_tip.x, 'y': nose_tip.y}
                            self.anchor_start_time = current_time
                        else:
                            elapsed = current_time - self.anchor_start_time
                            hide_duration = 3.0

                            if elapsed > hide_duration:
                                visible_duration = self.lock_duration_threshold - hide_duration
                                lock_progress = min(1.0, (elapsed - hide_duration) / visible_duration)
                            else:
                                lock_progress = 0.0

                            if elapsed >= self.lock_duration_threshold:
                                self.is_locked = True
                                logger.info("Pipeline: Interface LOCKED.")
                                lock_progress = 1.0
                    else:
                        lock_progress = 1.0
                        if distance > self.breakout_threshold:
                            self.is_locked = False
                            logger.info("Pipeline: Interface UNLOCKED.")
                            self.anchor_point = {'x': nose_tip.x, 'y': nose_tip.y}
                            self.anchor_start_time = current_time
                            lock_progress = 0.0

                payload = {
                    'timestamp': timestamp_ms,
                    'nose_tip': {'x': nose_tip.x, 'y': nose_tip.y, 'z': nose_tip.z},
                    'blendshapes': blendshape_dict,
                    'landmarks': landmarks,
                    'frame': cv2.flip(frame, 1),
                    'is_locked': self.is_locked,
                    'lock_progress': lock_progress,
                    'is_looking_away': is_looking_away
                }

                self.last_known_payload = payload
                self.previous_frame_gray = current_frame_gray

                try:
                    self.data_queue.put_nowait(payload)
                except queue.Full:
                    pass

            elapsed = time.time() - start_time
            sleep_time = self.frame_duration - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()
        self.detector.close()
        logger.info("Vision pipeline stopped.")

    def stop(self):
        self.running = False
