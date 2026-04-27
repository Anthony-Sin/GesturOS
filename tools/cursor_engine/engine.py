import pyautogui
import queue
import time
import threading
import math
import logging
from tools.cursor_engine.one_euro import OneEuroFilter
from tools.interfaces import BaseCursorEngine

logger = logging.getLogger(__name__)


class CursorEngine(BaseCursorEngine):
    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict, audio_player):
        self.data_queue = data_queue
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player
        self.running = False

        pyautogui.FAILSAFE = False
        self.screen_w, self.screen_h = pyautogui.size()

        # Two filter pairs: one for normal tracking, one for locked/precision.
        self._build_filters()

        self.last_raw_x = None
        self.last_raw_y = None
        self.deadzone_velocity = float(self.config.get("DEADZONE_VELOCITY", 0.003))

        self.active_zone_x_center = self.config.get("ACTIVE_ZONE_X_CENTER", 0.5)
        self.active_zone_y_center = self.config.get("ACTIVE_ZONE_Y_CENTER", 0.6)
        self.active_zone_width = self.config.get("ACTIVE_ZONE_WIDTH", 0.18)
        self.active_zone_height = self.config.get("ACTIVE_ZONE_HEIGHT", 0.06)
        self.default_active_zone_x_center = float(self.active_zone_x_center)
        self.default_active_zone_y_center = float(self.active_zone_y_center)
        self.force_cursor_center_on_start = bool(self.config.get("FORCE_CURSOR_CENTER_ON_START", True))
        self.auto_center_on_start = bool(self.config.get("AUTO_CENTER_ON_START", True))
        self._did_startup_center_calibration = False
        self._did_force_startup_center = False
        self.enable_quick_calibration = bool(self.config.get("ENABLE_QUICK_CALIBRATION", False))
        self.quick_calibration_duration = max(
            0.2, float(self.config.get("QUICK_CALIBRATION_DURATION_SECONDS", 1.2))
        )
        self.quick_calibration_wait_for_ui_seconds = max(
            0.0, float(self.config.get("QUICK_CALIBRATION_WAIT_FOR_UI_SECONDS", 5.0))
        )
        self.quick_calibration_summary_seconds = max(
            1.0, float(self.config.get("QUICK_CALIBRATION_SUMMARY_SECONDS", 4.0))
        )
        self.quick_calibration_min_samples = max(
            3, int(self.config.get("QUICK_CALIBRATION_MIN_SAMPLES", 12))
        )
        self.quick_calibration_max_center_shift = max(
            0.02, float(self.config.get("QUICK_CALIBRATION_MAX_CENTER_SHIFT", 0.18))
        )
        self.quick_calibration_center_blend = max(
            0.0, min(1.0, float(self.config.get("QUICK_CALIBRATION_CENTER_BLEND", 0.85)))
        )
        self.quick_calibration_default_center_bias = max(
            0.0, min(1.0, float(self.config.get("QUICK_CALIBRATION_DEFAULT_CENTER_BIAS", 0.28)))
        )
        self.quick_calibration_force_neutral_center = bool(
            self.config.get("QUICK_CALIBRATION_FORCE_NEUTRAL_CENTER", True)
        )
        self.quick_calibration_center_min_x = max(
            0.0, min(1.0, float(self.config.get("QUICK_CALIBRATION_CENTER_MIN_X", 0.32)))
        )
        self.quick_calibration_center_max_x = max(
            self.quick_calibration_center_min_x,
            min(1.0, float(self.config.get("QUICK_CALIBRATION_CENTER_MAX_X", 0.68))),
        )
        self.quick_calibration_center_min_y = max(
            0.0, min(1.0, float(self.config.get("QUICK_CALIBRATION_CENTER_MIN_Y", 0.30)))
        )
        self.quick_calibration_center_max_y = max(
            self.quick_calibration_center_min_y,
            min(1.0, float(self.config.get("QUICK_CALIBRATION_CENTER_MAX_Y", 0.70))),
        )
        self.quick_calibration_max_seconds = max(
            2.0, float(self.config.get("QUICK_CALIBRATION_MAX_SECONDS", 12.0))
        )
        # When enabled, quick calibration will never auto-finish with partial points.
        # It will keep waiting until every calibration target is collected.
        self.quick_calibration_require_all_points = bool(
            self.config.get("QUICK_CALIBRATION_REQUIRE_ALL_POINTS", True)
        )
        self.quick_calibration_target_radius_px = max(
            30, int(self.config.get("QUICK_CALIBRATION_TARGET_RADIUS_PX", 85))
        )
        self.quick_calibration_dwell_samples = max(
            3, int(self.config.get("QUICK_CALIBRATION_DWELL_SAMPLES", 8))
        )
        self.quick_calibration_edge_padding = max(
            0.01, float(self.config.get("QUICK_CALIBRATION_EDGE_PADDING", 0.06))
        )
        self.quick_calibration_zone_scale_x = max(
            0.8, float(self.config.get("QUICK_CALIBRATION_ZONE_SCALE_X", 1.25))
        )
        self.quick_calibration_zone_scale_y = max(
            0.8, float(self.config.get("QUICK_CALIBRATION_ZONE_SCALE_Y", 1.20))
        )
        self.quick_calibration_min_width = max(
            0.05, float(self.config.get("QUICK_CALIBRATION_MIN_WIDTH", 0.13))
        )
        self.quick_calibration_min_height = max(
            0.04, float(self.config.get("QUICK_CALIBRATION_MIN_HEIGHT", 0.10))
        )
        self.quick_calibration_max_width = max(
            self.quick_calibration_min_width,
            float(self.config.get("QUICK_CALIBRATION_MAX_WIDTH", 0.42)),
        )
        self.quick_calibration_max_height = max(
            self.quick_calibration_min_height,
            float(self.config.get("QUICK_CALIBRATION_MAX_HEIGHT", 0.34)),
        )
        configured_points = self.config.get(
            "QUICK_CALIBRATION_POINTS",
            [
                (0.5, 0.5),
                (0.3, 0.5),
                (0.7, 0.5),
                (0.5, 0.35),
                (0.5, 0.65),
            ],
        )
        self.quick_calibration_points = []
        try:
            for point in configured_points:
                px, py = float(point[0]), float(point[1])
                self.quick_calibration_points.append((max(0.05, min(0.95, px)), max(0.05, min(0.95, py))))
        except Exception:
            self.quick_calibration_points = [(0.5, 0.5), (0.3, 0.5), (0.7, 0.5), (0.5, 0.35), (0.5, 0.65)]
        if len(self.quick_calibration_points) < 3:
            self.quick_calibration_points = [(0.5, 0.5), (0.3, 0.5), (0.7, 0.5), (0.5, 0.35), (0.5, 0.65)]
        self._cursor_started_at = None
        self._quick_calibration_started_at = None
        self._quick_calibration_samples = []
        self._quick_calibration_done = not self.enable_quick_calibration
        self._quick_calibration_initial_center = (
            float(self.active_zone_x_center),
            float(self.active_zone_y_center),
        )
        self._quick_calibration_point_index = 0
        self._quick_calibration_point_samples = []
        self._quick_calibration_collected = []
        self._quick_calibration_timeout_logged = False
        self._calibration_wait_logged = False
        self.shared_state["calibration_active"] = False
        self.shared_state["calibration_progress"] = 0.0
        self.shared_state["calibration_remaining"] = 0.0
        self.shared_state["calibration_sample_count"] = 0
        self.shared_state["calibration_sample_target"] = self.quick_calibration_min_samples
        self.shared_state["calibration_nose_xy"] = None
        self.shared_state["calibration_target_xy"] = (0.5, 0.5)
        self.shared_state.setdefault("ui_ready", False)
        self.shared_state.setdefault("targeting_overlay_ready", False)
        self.shared_state.setdefault("calibration_allow_start", False)
        self.shared_state["calibration_summary_active"] = False
        self.shared_state["calibration_summary_until"] = 0.0
        self.shared_state["calibration_summary_text"] = ""
        self.shared_state.setdefault("request_quick_calibration", False)
        self.shared_state["calibration_screen_active"] = False
        self.shared_state["calibration_screen_target"] = None
        self.shared_state["calibration_screen_user"] = None
        self.shared_state["calibration_screen_step"] = 0
        self.shared_state["calibration_screen_steps"] = len(self.quick_calibration_points)
        self.shared_state["calibration_screen_progress"] = 0.0
        self.shared_state["calibration_screen_message"] = ""

        # Gradual precision control (slow near center, faster toward edges).
        self.cursor_response_exponent_x = max(
            1.0, float(self.config.get("CURSOR_RESPONSE_EXPONENT_X", 1.75))
        )
        self.cursor_response_exponent_y = max(
            1.0, float(self.config.get("CURSOR_RESPONSE_EXPONENT_Y", 2.0))
        )
        self.cursor_response_exponent_y_up = max(
            1.0, float(self.config.get("CURSOR_RESPONSE_EXPONENT_Y_UP", self.cursor_response_exponent_y))
        )
        self.cursor_response_exponent_y_down = max(
            1.0,
            float(
                self.config.get(
                    "CURSOR_RESPONSE_EXPONENT_Y_DOWN",
                    max(1.0, self.cursor_response_exponent_y - 0.3),
                )
            ),
        )
        self.cursor_downward_boost = max(
            1.0, float(self.config.get("CURSOR_DOWNWARD_BOOST", 1.12))
        )
        self.cursor_micro_gain = max(
            0.1, min(1.0, float(self.config.get("CURSOR_MICRO_GAIN", 0.38)))
        )
        self.cursor_micro_radius = max(
            0.05, min(1.0, float(self.config.get("CURSOR_MICRO_RADIUS", 0.34)))
        )
        self.cursor_pixel_deadzone = max(
            0.0, float(self.config.get("CURSOR_PIXEL_DEADZONE", 1.25))
        )
        self.cursor_max_step_px = max(
            0.0, float(self.config.get("CURSOR_MAX_STEP_PX", 55.0))
        )
        # Anti-drift hold: if head movement stays below threshold for a few frames
        # and target is already near the current cursor, freeze to prevent creep.
        self.cursor_stillness_head_threshold = max(
            0.0, float(self.config.get("CURSOR_STILLNESS_HEAD_THRESHOLD", self.deadzone_velocity))
        )
        self.cursor_stillness_target_window_px = max(
            0.0, float(self.config.get("CURSOR_STILLNESS_TARGET_WINDOW_PX", 14.0))
        )
        self.cursor_stillness_frames = max(
            1, int(self.config.get("CURSOR_STILLNESS_FRAMES", 5))
        )
        self._cursor_still_frame_count = 0

        self.magnetism_pull_strength = max(
            0.0, min(1.0, float(self.config.get("MAGNETISM_PULL_STRENGTH", 0.35)))
        )
        self.magnetism_release_distance = float(
            self.config.get(
                "MAGNETISM_RELEASE_DISTANCE",
                self.config.get("MAGNETISM_TRIGGER_DISTANCE", 40) * 1.8,
            )
        )

        self.last_cursor_pos = None

    def _reset_quick_calibration_state(self):
        self._quick_calibration_started_at = None
        self._quick_calibration_samples = []
        self._quick_calibration_done = not self.enable_quick_calibration
        self._quick_calibration_point_index = 0
        self._quick_calibration_point_samples = []
        self._quick_calibration_collected = []
        self._quick_calibration_timeout_logged = False
        self._quick_calibration_initial_center = (
            float(self.active_zone_x_center),
            float(self.active_zone_y_center),
        )
        self._calibration_wait_logged = False
        self.shared_state["calibration_active"] = False
        self.shared_state["calibration_progress"] = 0.0
        self.shared_state["calibration_remaining"] = 0.0
        self.shared_state["calibration_sample_count"] = 0
        self.shared_state["calibration_sample_target"] = self.quick_calibration_min_samples
        self.shared_state["calibration_nose_xy"] = None
        self.shared_state["calibration_target_xy"] = (0.5, 0.5)
        self.shared_state["calibration_summary_active"] = False
        self.shared_state["calibration_summary_until"] = 0.0
        self.shared_state["calibration_summary_text"] = ""
        self.shared_state["calibration_screen_active"] = False
        self.shared_state["calibration_screen_target"] = None
        self.shared_state["calibration_screen_user"] = None
        self.shared_state["calibration_screen_step"] = 0
        self.shared_state["calibration_screen_steps"] = len(self.quick_calibration_points)
        self.shared_state["calibration_screen_progress"] = 0.0
        self.shared_state["calibration_screen_message"] = ""

    def _build_filters(self):
        """(Re)build both filter pairs from config. Safe to call any time."""
        normal_cutoff = self.config.get("FILTER_MIN_CUTOFF", 0.001)
        normal_beta = self.config.get("FILTER_BETA_NORMAL", 0.8)
        locked_cutoff = self.config.get("FILTER_MIN_CUTOFF_LOCKED", 0.001)
        locked_beta = self.config.get("FILTER_BETA_LOCKED", 0.01)

        self.filter_x_normal = OneEuroFilter(min_cutoff=normal_cutoff, beta=normal_beta)
        self.filter_y_normal = OneEuroFilter(min_cutoff=normal_cutoff, beta=normal_beta)
        self.filter_x_locked = OneEuroFilter(min_cutoff=locked_cutoff, beta=locked_beta)
        self.filter_y_locked = OneEuroFilter(min_cutoff=locked_cutoff, beta=locked_beta)

        # Active pointers - swapped, never mutated
        self.filter_x = self.filter_x_normal
        self.filter_y = self.filter_y_normal

    def start(self):
        self.running = True
        self._cursor_started_at = time.time()
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        logger.info(f"Cursor Engine started. Screen resolution: {self.screen_w}x{self.screen_h}")
        return thread

    def stop(self):
        self.running = False

    def _normalize_to_active_zone(self, val, center, size):
        size = max(0.001, float(size))
        min_bound = center - size / 2.0
        max_bound = center + size / 2.0
        val_clamped = max(min_bound, min(val, max_bound))
        return (val_clamped - min_bound) / size

    @staticmethod
    def _smoothstep(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    @staticmethod
    def _curve_axis(value: float, exponent: float) -> float:
        if value == 0.0:
            return 0.0
        sign = 1.0 if value > 0.0 else -1.0
        return sign * (abs(value) ** exponent)

    def _apply_precision_response_curve(self, normalized_x: float, normalized_y: float):
        # Convert to centered offsets [-1..1], damp near center, then map back.
        offset_x = (normalized_x - 0.5) * 2.0
        offset_y = (normalized_y - 0.5) * 2.0
        radius = min(1.0, math.hypot(offset_x, offset_y))

        curved_x = self._curve_axis(offset_x, self.cursor_response_exponent_x)
        if offset_y >= 0.0:
            y_exponent = self.cursor_response_exponent_y_down
            y_input = max(-1.0, min(1.0, offset_y * self.cursor_downward_boost))
        else:
            y_exponent = self.cursor_response_exponent_y_up
            y_input = offset_y
        curved_y = self._curve_axis(y_input, y_exponent)

        gain_t = radius / self.cursor_micro_radius if self.cursor_micro_radius > 0 else 1.0
        gain = self.cursor_micro_gain + (1.0 - self.cursor_micro_gain) * self._smoothstep(gain_t)

        out_x = 0.5 + (curved_x * gain) / 2.0
        out_y = 0.5 + (curved_y * gain) / 2.0
        out_x = max(0.0, min(1.0, out_x))
        out_y = max(0.0, min(1.0, out_y))
        return out_x, out_y

    def _move_cursor(self, fx: int, fy: int) -> bool:
        if self.last_cursor_pos:
            dx = fx - self.last_cursor_pos[0]
            dy = fy - self.last_cursor_pos[1]
            dist = math.hypot(dx, dy)
            if self.cursor_max_step_px > 0.0 and dist > self.cursor_max_step_px:
                scale = self.cursor_max_step_px / dist
                fx = int(self.last_cursor_pos[0] + dx * scale)
                fy = int(self.last_cursor_pos[1] + dy * scale)
                dist = self.cursor_max_step_px
            if dist < self.cursor_pixel_deadzone:
                return False
            self.shared_state["cursor_distance"] = (
                self.shared_state.get("cursor_distance", 0) + dist
            )
        pyautogui.moveTo(fx, fy)
        self.last_cursor_pos = (fx, fy)
        return True

    @staticmethod
    def _median(values):
        ordered = sorted(values)
        n = len(ordered)
        if n == 0:
            return None
        mid = n // 2
        if n % 2 == 1:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0

    def _raw_to_screen_px(self, raw_x: float, raw_y: float):
        sx = int((1.0 - float(raw_x)) * self.screen_w)
        sy = int(float(raw_y) * self.screen_h)
        sx = max(0, min(self.screen_w - 1, sx))
        sy = max(0, min(self.screen_h - 1, sy))
        return sx, sy

    def _target_norm_to_screen_px(self, target_xy):
        tx = int(float(target_xy[0]) * self.screen_w)
        ty = int(float(target_xy[1]) * self.screen_h)
        tx = max(0, min(self.screen_w - 1, tx))
        ty = max(0, min(self.screen_h - 1, ty))
        return tx, ty

    def _set_calibration_screen_state(self, active: bool, target_xy=None, user_px=None, progress=0.0, message=""):
        self.shared_state["calibration_screen_active"] = bool(active)
        self.shared_state["calibration_screen_target"] = (
            self._target_norm_to_screen_px(target_xy) if target_xy is not None else None
        )
        self.shared_state["calibration_screen_user"] = user_px
        self.shared_state["calibration_screen_step"] = int(self._quick_calibration_point_index + 1)
        self.shared_state["calibration_screen_steps"] = int(len(self.quick_calibration_points))
        self.shared_state["calibration_screen_progress"] = max(0.0, min(1.0, float(progress)))
        self.shared_state["calibration_screen_message"] = str(message or "")

    def _finalize_quick_calibration(self, timestamp: float, now: float):
        # Resolve collected points by index.
        point_map = {}
        for item in self._quick_calibration_collected:
            idx = int(item.get("index", -1))
            if idx >= 0:
                point_map[idx] = item

        center_raw = point_map.get(0, {}).get("raw")
        if center_raw is None:
            all_x = [it["raw"][0] for it in self._quick_calibration_collected if "raw" in it]
            all_y = [it["raw"][1] for it in self._quick_calibration_collected if "raw" in it]
            if all_x and all_y:
                center_raw = (self._median(all_x), self._median(all_y))
        if center_raw is None:
            self._quick_calibration_done = True
            self.shared_state["calibration_active"] = False
            self.shared_state["currently_doing"] = "CALIBRATION FAILED (USING DEFAULT)"
            self._set_calibration_screen_state(False)
            return True

        center_tx = 1.0 - float(center_raw[0])
        center_ty = float(center_raw[1])

        left_raw = point_map.get(1, {}).get("raw")
        right_raw = point_map.get(2, {}).get("raw")
        up_raw = point_map.get(3, {}).get("raw")
        down_raw = point_map.get(4, {}).get("raw")

        width_est = self.active_zone_width
        if left_raw is not None and right_raw is not None:
            tx_left = 1.0 - float(left_raw[0])
            tx_right = 1.0 - float(right_raw[0])
            width_est = abs(tx_right - tx_left) * self.quick_calibration_zone_scale_x

        height_est = self.active_zone_height
        if up_raw is not None and down_raw is not None:
            ty_up = float(up_raw[1])
            ty_down = float(down_raw[1])
            height_est = abs(ty_down - ty_up) * self.quick_calibration_zone_scale_y

        width_est = max(self.quick_calibration_min_width, min(self.quick_calibration_max_width, float(width_est)))
        height_est = max(self.quick_calibration_min_height, min(self.quick_calibration_max_height, float(height_est)))
        # Keep some memory of previous values to reduce abrupt jumps.
        self.active_zone_width = max(
            self.quick_calibration_min_width,
            min(self.quick_calibration_max_width, 0.75 * width_est + 0.25 * float(self.active_zone_width)),
        )
        self.active_zone_height = max(
            self.quick_calibration_min_height,
            min(self.quick_calibration_max_height, 0.75 * height_est + 0.25 * float(self.active_zone_height)),
        )

        half_w = self.active_zone_width / 2.0
        half_h = self.active_zone_height / 2.0
        edge_pad = self.quick_calibration_edge_padding
        min_x = edge_pad + half_w
        max_x = 1.0 - edge_pad - half_w
        min_y = edge_pad + half_h
        max_y = 1.0 - edge_pad - half_h
        if min_x > max_x:
            min_x, max_x = half_w, 1.0 - half_w
        if min_y > max_y:
            min_y, max_y = half_h, 1.0 - half_h

        target_x_center = max(min_x, min(max_x, center_tx))
        target_y_center = max(min_y, min(max_y, center_ty))
        # Keep the calibrated center in a comfort band so neutral tracking does not drift to edges.
        target_x_center = max(
            self.quick_calibration_center_min_x,
            min(self.quick_calibration_center_max_x, target_x_center),
        )
        target_y_center = max(
            self.quick_calibration_center_min_y,
            min(self.quick_calibration_center_max_y, target_y_center),
        )
        if not self.quick_calibration_force_neutral_center:
            # Blend measured center with previous center to avoid large jumps between runs.
            target_x_center = (
                self.quick_calibration_center_blend * target_x_center
                + (1.0 - self.quick_calibration_center_blend) * float(self.active_zone_x_center)
            )
            target_y_center = (
                self.quick_calibration_center_blend * target_y_center
                + (1.0 - self.quick_calibration_center_blend) * float(self.active_zone_y_center)
            )
            # Add slight bias back toward configured defaults for consistency across sessions.
            target_x_center = (
                (1.0 - self.quick_calibration_default_center_bias) * target_x_center
                + self.quick_calibration_default_center_bias * self.default_active_zone_x_center
            )
            target_y_center = (
                (1.0 - self.quick_calibration_default_center_bias) * target_y_center
                + self.quick_calibration_default_center_bias * self.default_active_zone_y_center
            )

            dx = target_x_center - self.active_zone_x_center
            dy = target_y_center - self.active_zone_y_center
            if abs(dx) > self.quick_calibration_max_center_shift:
                target_x_center = self.active_zone_x_center + math.copysign(self.quick_calibration_max_center_shift, dx)
            if abs(dy) > self.quick_calibration_max_center_shift:
                target_y_center = self.active_zone_y_center + math.copysign(self.quick_calibration_max_center_shift, dy)

        self.active_zone_x_center = max(min_x, min(max_x, target_x_center))
        self.active_zone_y_center = max(min_y, min(max_y, target_y_center))
        self._did_startup_center_calibration = True
        self._quick_calibration_done = True
        initial_x, initial_y = self._quick_calibration_initial_center
        shift_x = self.active_zone_x_center - initial_x
        shift_y = self.active_zone_y_center - initial_y
        collected_count = len(self._quick_calibration_collected)
        self.shared_state["currently_doing"] = (
            f"CALIBRATION COMPLETE X{initial_x:.3f}->{self.active_zone_x_center:.3f} "
            f"Y{initial_y:.3f}->{self.active_zone_y_center:.3f}"
        )
        self.shared_state["calibration_active"] = False
        self.shared_state["calibration_progress"] = 1.0
        self.shared_state["calibration_remaining"] = 0.0
        self.shared_state["calibration_nose_xy"] = center_raw
        self.shared_state["calibration_summary_active"] = True
        self.shared_state["calibration_summary_until"] = now + self.quick_calibration_summary_seconds
        self.shared_state["calibration_summary_text"] = (
            f"X {initial_x:.3f}->{self.active_zone_x_center:.3f} "
            f"Y {initial_y:.3f}->{self.active_zone_y_center:.3f} "
            f"SAMPLES {collected_count} "
            f"SHIFT ({shift_x:+.3f},{shift_y:+.3f})"
        )
        self._set_calibration_screen_state(False)

        center_x = int(self.screen_w / 2)
        center_y = int(self.screen_h / 2)
        try:
            pyautogui.moveTo(center_x, center_y)
        except Exception as e:
            logger.warning(f"Calibration center move error: {e}")
        self.last_cursor_pos = (center_x, center_y)
        self.filter_x(center_x, timestamp)
        self.filter_y(center_y, timestamp)
        logger.info(
            "Quick calibration complete: center=(%.3f, %.3f) zone=(%.3f, %.3f) from %d collected targets.",
            self.active_zone_x_center,
            self.active_zone_y_center,
            self.active_zone_width,
            self.active_zone_height,
            collected_count,
        )
        return True

    def _run_quick_calibration(self, raw_x: float, raw_y: float, timestamp: float):
        now = time.time()
        if self._quick_calibration_started_at is None:
            self._quick_calibration_started_at = now
            self._quick_calibration_timeout_logged = False
            self._quick_calibration_initial_center = (
                float(self.active_zone_x_center),
                float(self.active_zone_y_center),
            )
            self.shared_state["currently_doing"] = "FULLSCREEN CALIBRATION STARTED"
            self.shared_state["calibration_active"] = True
            self.shared_state["calibration_screen_steps"] = len(self.quick_calibration_points)

        elapsed = now - self._quick_calibration_started_at
        remaining = max(0.0, self.quick_calibration_max_seconds - elapsed)
        if elapsed >= self.quick_calibration_max_seconds:
            if self.quick_calibration_require_all_points:
                remaining = 0.0
                if not self._quick_calibration_timeout_logged:
                    logger.info(
                        "Quick calibration soft timeout reached; waiting for all points instead of auto-finalizing."
                    )
                    self._quick_calibration_timeout_logged = True
            else:
                logger.warning("Quick calibration timed out; finalizing with collected points.")
                return self._finalize_quick_calibration(timestamp, now)

        idx = min(self._quick_calibration_point_index, len(self.quick_calibration_points) - 1)
        target_norm = self.quick_calibration_points[idx]
        user_px = self._raw_to_screen_px(raw_x, raw_y)
        target_px = self._target_norm_to_screen_px(target_norm)
        dist_px = math.hypot(user_px[0] - target_px[0], user_px[1] - target_px[1])

        in_target = dist_px <= self.quick_calibration_target_radius_px
        if in_target:
            self._quick_calibration_point_samples.append((raw_x, raw_y))
        else:
            if self._quick_calibration_point_samples:
                self._quick_calibration_point_samples = []

        dwell_ratio = min(
            1.0,
            len(self._quick_calibration_point_samples) / float(max(1, self.quick_calibration_dwell_samples)),
        )
        progress = (
            self._quick_calibration_point_index + dwell_ratio
        ) / float(max(1, len(self.quick_calibration_points)))

        self.shared_state["currently_doing"] = (
            f"CALIBRATING TARGET {idx + 1}/{len(self.quick_calibration_points)}"
        )
        self.shared_state["calibration_active"] = True
        self.shared_state["calibration_progress"] = progress
        self.shared_state["calibration_remaining"] = remaining
        self.shared_state["calibration_sample_count"] = len(self._quick_calibration_point_samples)
        self.shared_state["calibration_sample_target"] = self.quick_calibration_dwell_samples
        self.shared_state["calibration_nose_xy"] = (raw_x, raw_y)
        self.shared_state["calibration_target_xy"] = target_norm
        self._set_calibration_screen_state(
            True,
            target_xy=target_norm,
            user_px=user_px,
            progress=progress,
            message=(
                "Move BLUE circle into RED circle and hold"
                if remaining > 0.0
                else "Timer ended. Keep going until every target is captured."
            ),
        )

        if len(self._quick_calibration_point_samples) < self.quick_calibration_dwell_samples:
            return False

        xs = [sample[0] for sample in self._quick_calibration_point_samples]
        ys = [sample[1] for sample in self._quick_calibration_point_samples]
        point_raw = (self._median(xs), self._median(ys))
        if point_raw[0] is None or point_raw[1] is None:
            self._quick_calibration_point_samples = []
            return False

        self._quick_calibration_collected.append(
            {"index": idx, "target": target_norm, "raw": point_raw}
        )
        self._quick_calibration_point_index += 1
        self._quick_calibration_point_samples = []

        if self._quick_calibration_point_index >= len(self.quick_calibration_points):
            return self._finalize_quick_calibration(timestamp, now)

        return False

    def _run(self):
        was_locked = False
        was_looking_away = False
        use_locked_filter = False

        while self.running:
            try:
                payload = self.data_queue.get(timeout=0.1)

                if self.shared_state.get("request_quick_calibration", False):
                    self.shared_state["request_quick_calibration"] = False
                    if self.enable_quick_calibration:
                        self._reset_quick_calibration_state()
                        self.shared_state["currently_doing"] = "WAITING FOR CALIBRATION OVERLAY..."
                        logger.info("Quick calibration reset requested from UI.")
                    else:
                        self.shared_state["currently_doing"] = "TRACKING ENABLED"

                if self.shared_state.get("tracking_paused", False) or self.shared_state.get("agent_active", False):
                    self._cursor_still_frame_count = 0
                    continue

                # Look-away pause
                is_looking_away = payload.get('is_looking_away', False)
                if is_looking_away:
                    if not was_looking_away:
                        self.shared_state["currently_doing"] = "TRACKING PAUSED (LOOK AWAY)"
                        was_looking_away = True
                    self._cursor_still_frame_count = 0
                    continue
                else:
                    if was_looking_away:
                        self.shared_state["currently_doing"] = "AWAITING COMMAND"
                        was_looking_away = False

                if self.shared_state.get("dictation_active", False):
                    self._cursor_still_frame_count = 0
                    continue
                if self.shared_state.get("continuous_scroll_active"):
                    self._cursor_still_frame_count = 0
                    continue

                # Lock state -> swap filter pair (no mutation)
                is_locked = payload.get('is_locked', False)
                lock_progress = payload.get('lock_progress', 0.0)
                should_use_locked = (lock_progress > 0.0 or is_locked)

                if should_use_locked != use_locked_filter:
                    use_locked_filter = should_use_locked
                    if use_locked_filter:
                        self.filter_x = self.filter_x_locked
                        self.filter_y = self.filter_y_locked
                    else:
                        self.filter_x = self.filter_x_normal
                        self.filter_y = self.filter_y_normal

                # Lock engage / release audio
                if is_locked and not was_locked:
                    if self.audio_player:
                        try:
                            self.audio_player.play('lock_engage')
                        except Exception as e:
                            logger.warning(f"Audio play error: {e}")
                    was_locked = True
                elif not is_locked and was_locked:
                    if self.audio_player:
                        try:
                            self.audio_player.play('lock_release')
                        except Exception as e:
                            logger.warning(f"Audio play error: {e}")
                    was_locked = False

                # Nose tracking
                nose_tip = payload['nose_tip']
                timestamp = payload['timestamp'] / 1000.0

                raw_x = nose_tip['x']
                raw_y = nose_tip['y']

                if self.force_cursor_center_on_start and not self._did_force_startup_center:
                    center_x = int(self.screen_w / 2)
                    center_y = int(self.screen_h / 2)
                    try:
                        pyautogui.moveTo(center_x, center_y)
                    except Exception as e:
                        logger.warning(f"Startup hard-center move error: {e}")
                    self.last_cursor_pos = (center_x, center_y)
                    # Seed filters at center to avoid a jump.
                    self.filter_x(center_x, timestamp)
                    self.filter_y(center_y, timestamp)
                    self._did_force_startup_center = True

                if self.enable_quick_calibration and not self._quick_calibration_done:
                    ui_ready = bool(self.shared_state.get("ui_ready", False))
                    overlay_ready = bool(self.shared_state.get("targeting_overlay_ready", False))
                    allow_start = bool(self.shared_state.get("calibration_allow_start", False))
                    started_at = self._cursor_started_at or time.time()
                    waited = time.time() - started_at
                    if not (ui_ready and overlay_ready and allow_start):
                        if not self._calibration_wait_logged:
                            logger.info(
                                "Quick calibration waiting for overlay handshake (ui_ready=%s, overlay_ready=%s, allow_start=%s, waited=%.2fs).",
                                ui_ready,
                                overlay_ready,
                                allow_start,
                                waited,
                            )
                            self._calibration_wait_logged = True
                        wait_note = ""
                        if waited >= self.quick_calibration_wait_for_ui_seconds:
                            wait_note = " (slow UI startup)"
                        self.shared_state["currently_doing"] = f"WAITING FOR CALIBRATION OVERLAY{wait_note}"
                        continue
                    self._run_quick_calibration(raw_x, raw_y, timestamp)
                    continue

                if (
                    self.auto_center_on_start
                    and not self.enable_quick_calibration
                    and not self._did_startup_center_calibration
                ):
                    half_w = self.active_zone_width / 2.0
                    half_h = self.active_zone_height / 2.0
                    # Clamp so active zone remains valid while making neutral face map to screen center.
                    normalized_x_for_mapping = 1.0 - raw_x
                    self.active_zone_x_center = max(half_w, min(1.0 - half_w, normalized_x_for_mapping))
                    self.active_zone_y_center = max(half_h, min(1.0 - half_h, raw_y))
                    self._did_startup_center_calibration = True

                    center_x = int(self.screen_w / 2)
                    center_y = int(self.screen_h / 2)
                    try:
                        pyautogui.moveTo(center_x, center_y)
                    except Exception as e:
                        logger.warning(f"Startup center move error: {e}")
                    self.last_cursor_pos = (center_x, center_y)
                    self.filter_x(center_x, timestamp)
                    self.filter_y(center_y, timestamp)

                if self.last_raw_x is not None and self.last_raw_y is not None:
                    dx = raw_x - self.last_raw_x
                    dy = raw_y - self.last_raw_y
                    head_velocity = (dx**2 + dy**2) ** 0.5
                    self.shared_state["head_velocity"] = head_velocity
                else:
                    head_velocity = 0.0
                self.last_raw_x = raw_x
                self.last_raw_y = raw_y

                scaled_x = self._normalize_to_active_zone(
                    1.0 - raw_x, self.active_zone_x_center, self.active_zone_width
                )
                scaled_y = self._normalize_to_active_zone(
                    raw_y, self.active_zone_y_center, self.active_zone_height
                )
                scaled_x, scaled_y = self._apply_precision_response_curve(scaled_x, scaled_y)

                target_x = scaled_x * self.screen_w
                target_y = scaled_y * self.screen_h
                self.shared_state["raw_nose_target"] = (target_x, target_y)

                if self.last_cursor_pos:
                    target_drift_px = math.hypot(
                        float(target_x) - float(self.last_cursor_pos[0]),
                        float(target_y) - float(self.last_cursor_pos[1]),
                    )
                    still_now = (
                        head_velocity <= self.cursor_stillness_head_threshold
                        and target_drift_px <= self.cursor_stillness_target_window_px
                    )
                    if still_now:
                        self._cursor_still_frame_count += 1
                    else:
                        self._cursor_still_frame_count = 0

                    if self._cursor_still_frame_count >= self.cursor_stillness_frames:
                        self.shared_state["cursor_still"] = True
                        # Re-seed active filters at the current cursor location to
                        # prevent OneEuro residual drift while user stays still.
                        self.filter_x(self.last_cursor_pos[0], timestamp)
                        self.filter_y(self.last_cursor_pos[1], timestamp)
                        continue
                else:
                    self._cursor_still_frame_count = 0
                self.shared_state["cursor_still"] = False

                # Magnetism snap
                snap_target = self.shared_state.get("magnet_snap_target")
                sniper_mode_active = bool(self.shared_state.get("sniper_mode_active", False))

                if sniper_mode_active:
                    # In sniper/focus mode, cursor moves EXACTLY to the snap target, and
                    # normal head movements only serve to cycle candidates (handled in magnetism.py),
                    # so we completely block the free cursor movement.
                    if snap_target:
                        try:
                            sx, sy = float(snap_target[0]), float(snap_target[1])
                            # Re-seed the filters to the exact snap target so OneEuro doesn't trail
                            self.filter_x(sx, timestamp)
                            self.filter_y(sy, timestamp)

                            fx, fy = int(sx), int(sy)
                            # Directly move to the snapped item
                            self._move_cursor(fx, fy)
                            continue
                        except Exception as e:
                            logger.warning(f"Sniper magnetism jump error: {e}")
                    else:
                        # Sniper mode active but no valid target nearby? Keep cursor still,
                        # but keep updating filters so we don't jump when it toggles off.
                        self.filter_x(self.last_cursor_pos[0] if self.last_cursor_pos else target_x, timestamp)
                        self.filter_y(self.last_cursor_pos[1] if self.last_cursor_pos else target_y, timestamp)
                        continue
                else:
                    if snap_target:
                        try:
                            sx, sy = float(snap_target[0]), float(snap_target[1])
                            breakout_dist = math.hypot(target_x - sx, target_y - sy)
                            if breakout_dist > self.magnetism_release_distance:
                                # User moved away intentionally: clear stale snap state.
                                self.shared_state["magnet_snap_target"] = None
                                self.shared_state["magnet_target_bbox"] = None
                            else:
                                pulled_x = target_x + (sx - target_x) * self.magnetism_pull_strength
                                pulled_y = target_y + (sy - target_y) * self.magnetism_pull_strength
                                filtered_x = self.filter_x(pulled_x, timestamp)
                                filtered_y = self.filter_y(pulled_y, timestamp)
                                fx, fy = int(filtered_x), int(filtered_y)
                                self._move_cursor(fx, fy)
                                continue
                        except Exception as e:
                            logger.warning(f"Magnetism pull error: {e}")

                    # Normal filter + move
                    try:
                        filtered_x = self.filter_x(target_x, timestamp)
                        filtered_y = self.filter_y(target_y, timestamp)
                        fx, fy = int(filtered_x), int(filtered_y)
                        self._move_cursor(fx, fy)
                    except Exception as e:
                        logger.error(f"Filter/moveTo error: {e}", exc_info=True)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"CursorEngine _run error: {e}", exc_info=True)
                time.sleep(0.05)
