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
        self.data_queue   = data_queue
        self.config       = config
        self.shared_state = shared_state
        self.audio_player = audio_player
        self.running      = False

        pyautogui.FAILSAFE = False

        self.screen_w, self.screen_h = pyautogui.size()

        # ── Two filter pairs: one for normal tracking, one for locked/precision ──
        # OneEuroFilter does NOT support mutating .beta after construction.
        # Doing so creates a dangling instance attribute that bypasses the
        # internal __slots__ / property and corrupts filter state — leading to
        # NaN outputs and a silent thread crash exactly when LOCKED fires.
        # Solution: keep two pre-built filters and swap between them.
        self._build_filters()

        self.last_raw_x = None
        self.last_raw_y = None
        self.deadzone_velocity = self.config.get("DEADZONE_VELOCITY", 0.003)

        self.active_zone_x_center = self.config.get("ACTIVE_ZONE_X_CENTER", 0.5)
        self.active_zone_y_center = self.config.get("ACTIVE_ZONE_Y_CENTER", 0.6)
        self.active_zone_width    = self.config.get("ACTIVE_ZONE_WIDTH",    0.18)
        self.active_zone_height   = self.config.get("ACTIVE_ZONE_HEIGHT",   0.06)

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

    def _build_filters(self):
        """(Re)build both filter pairs from config. Safe to call any time."""
        normal_cutoff = self.config.get("FILTER_MIN_CUTOFF", 0.001)
        normal_beta   = self.config.get("FILTER_BETA_NORMAL", 0.8)
        locked_cutoff = self.config.get("FILTER_MIN_CUTOFF_LOCKED", 0.001)
        locked_beta   = self.config.get("FILTER_BETA_LOCKED", 0.01)

        self.filter_x_normal = OneEuroFilter(min_cutoff=normal_cutoff, beta=normal_beta)
        self.filter_y_normal = OneEuroFilter(min_cutoff=normal_cutoff, beta=normal_beta)
        self.filter_x_locked = OneEuroFilter(min_cutoff=locked_cutoff, beta=locked_beta)
        self.filter_y_locked = OneEuroFilter(min_cutoff=locked_cutoff, beta=locked_beta)

        # Active pointers — swapped, never mutated
        self.filter_x = self.filter_x_normal
        self.filter_y = self.filter_y_normal

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        logger.info(f"Cursor Engine started. Screen resolution: {self.screen_w}x{self.screen_h}")
        return thread

    def stop(self):
        self.running = False

    def _normalize_to_active_zone(self, val, center, size):
        min_bound  = center - size / 2
        max_bound  = center + size / 2
        val_clamped = max(min_bound, min(val, max_bound))
        return (val_clamped - min_bound) / size

    def _run(self):
        was_locked      = False
        was_looking_away = False
        use_locked_filter = False

        while self.running:
            try:
                payload = self.data_queue.get(timeout=0.1)

                # ── Look-away pause ───────────────────────────────────────────
                is_looking_away = payload.get('is_looking_away', False)
                if is_looking_away:
                    if not was_looking_away:
                        self.shared_state["currently_doing"] = "TRACKING PAUSED (LOOK AWAY)"
                        was_looking_away = True
                    continue
                else:
                    if was_looking_away:
                        self.shared_state["currently_doing"] = "AWAITING COMMAND"
                        was_looking_away = False

                if self.shared_state.get("dictation_active", False):
                    continue
                if self.shared_state.get("continuous_scroll_active"):
                    continue

                # ── Lock state → swap filter pair (no mutation) ───────────────
                is_locked    = payload.get('is_locked', False)
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

                # ── Lock engage / release audio ───────────────────────────────
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

                # ── Nose tracking ─────────────────────────────────────────────
                nose_tip  = payload['nose_tip']
                timestamp = payload['timestamp'] / 1000.0

                raw_x = nose_tip['x']
                raw_y = nose_tip['y']

                skip_movement = False
                if self.last_raw_x is not None and self.last_raw_y is not None:
                    dx = raw_x - self.last_raw_x
                    dy = raw_y - self.last_raw_y
                    if (dx**2 + dy**2) ** 0.5 < self.deadzone_velocity:
                        skip_movement = True

                self.last_raw_x = raw_x
                self.last_raw_y = raw_y

                scaled_x = self._normalize_to_active_zone(
                    1.0 - raw_x, self.active_zone_x_center, self.active_zone_width
                )
                scaled_y = self._normalize_to_active_zone(
                    raw_y, self.active_zone_y_center, self.active_zone_height
                )

                target_x = scaled_x * self.screen_w
                target_y = scaled_y * self.screen_h

                self.shared_state["raw_nose_target"] = (target_x, target_y)

                if skip_movement:
                    continue

                # ── Magnetism snap ────────────────────────────────────────────
                snap_target = self.shared_state.get("magnet_snap_target")
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
                            pyautogui.moveTo(fx, fy)
                            if self.last_cursor_pos:
                                dist = math.hypot(fx - self.last_cursor_pos[0],
                                                  fy - self.last_cursor_pos[1])
                                self.shared_state["cursor_distance"] = (
                                    self.shared_state.get("cursor_distance", 0) + dist
                                )
                            self.last_cursor_pos = (fx, fy)
                            continue
                    except Exception as e:
                        logger.warning(f"Magnetism pull error: {e}")

                # ── Normal filter + move ──────────────────────────────────────
                try:
                    filtered_x = self.filter_x(target_x, timestamp)
                    filtered_y = self.filter_y(target_y, timestamp)
                    fx, fy = int(filtered_x), int(filtered_y)
                    pyautogui.moveTo(fx, fy)
                    if self.last_cursor_pos:
                        dist = math.hypot(fx - self.last_cursor_pos[0],
                                          fy - self.last_cursor_pos[1])
                        self.shared_state["cursor_distance"] = (
                            self.shared_state.get("cursor_distance", 0) + dist
                        )
                    self.last_cursor_pos = (fx, fy)
                except Exception as e:
                    logger.error(f"Filter/moveTo error: {e}", exc_info=True)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"CursorEngine _run error: {e}", exc_info=True)
                time.sleep(0.05)  # brief pause before retrying so we don't spin
