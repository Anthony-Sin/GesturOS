import queue
import time
import collections
import logging
import sys
import os
import math
import cv2

from tools.interfaces import BaseUIEngine

logger = logging.getLogger(__name__)

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_FONT_DPI"] = "96"
os.environ["QT_DPI_ADJUSTMENT_POLICY"] = "AdjustDpi"

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor, QPainter, QPen, QBrush, QPolygon

BG     = "#000000"
WHITE  = "#FFFFFF"
RED    = "#FF5C39"
YELLOW = "#FFFFFF"
CYAN   = "#FFFFFF"
GREEN  = "#FFFFFF"
GRAY   = "#6E7B8B"
EYE    = "#8AFF6A"

# MediaPipe landmark indices
L_EYE_TOP = 159; L_EYE_BOT = 145; L_EYE_INNER = 133; L_EYE_OUTER = 33
R_EYE_TOP = 386; R_EYE_BOT = 374; R_EYE_INNER = 362; R_EYE_OUTER = 263
L_BROW_INNER = 107; L_BROW_OUTER = 70
R_BROW_INNER = 336; R_BROW_OUTER = 300

COMMANDS = [
    ("SAY",  "'AGENT [task]'",   "start AI control"),
    ("SAY",  "'STOP AGENT'",     "stop AI control"),
    ("SAY",  "'PRESS [key]'",    "keyboard press"),
    ("SAY",  "'OPEN / CLICK'",   "click target"),
    ("SAY",  "'SNIPER MODE'",    "precision aim"),
]

def _safe_lm(landmarks, idx):
    try:
        return landmarks[idx]
    except (IndexError, TypeError):
        return None


class TargetingOverlay(QWidget):
    def __init__(self, shared_state: dict):
        super().__init__()
        self.shared_state = shared_state
        self._magnet_bbox = None
        self._agent_bbox  = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.virtualGeometry())
        else:
            self.setGeometry(QRect(0, 0, 1920, 1080))
        self.show()
        logger.debug("TargetingOverlay shown.")

    def update_bboxes(self):
        self._magnet_bbox = self.shared_state.get("magnet_target_bbox")
        self._agent_bbox  = self.shared_state.get("agent_target_bbox")
        self.update()

    def _draw_fullscreen_calibration(self, painter: QPainter):
        target = self.shared_state.get("calibration_screen_target")
        user = self.shared_state.get("calibration_screen_user")
        step = int(self.shared_state.get("calibration_screen_step", 0) or 0)
        steps = int(self.shared_state.get("calibration_screen_steps", 0) or 0)
        progress = float(self.shared_state.get("calibration_screen_progress", 0.0) or 0.0)
        message = str(self.shared_state.get("calibration_screen_message", "") or "")

        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        # Top panel with instructions.
        panel_w = max(360, min(980, self.width() - 80))
        panel_h = 58
        panel_x = (self.width() - panel_w) // 2
        panel_y = 26
        painter.setPen(QPen(QColor(YELLOW), 2))
        painter.setBrush(QBrush(QColor(12, 12, 12, 220)))
        painter.drawRoundedRect(panel_x, panel_y, panel_w, panel_h, 10, 10)
        painter.setFont(QFont("Courier", 10, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(YELLOW), 1))
        headline = f"CALIBRATION {step}/{max(1, steps)}"
        painter.drawText(panel_x + 14, panel_y + 24, headline)
        painter.setPen(QPen(QColor(CYAN), 1))
        painter.drawText(panel_x + 14, panel_y + 45, message[:120])

        if target:
            tx, ty = int(target[0]), int(target[1])
            painter.setPen(QPen(QColor(RED), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPoint(tx, ty), 54, 54)
            painter.drawEllipse(QPoint(tx, ty), 26, 26)
            painter.drawLine(tx - 74, ty, tx + 74, ty)
            painter.drawLine(tx, ty - 74, tx, ty + 74)

        if user:
            ux, uy = int(user[0]), int(user[1])
            painter.setPen(QPen(QColor(CYAN), 3))
            painter.setBrush(QBrush(QColor(0, 220, 255, 80)))
            painter.drawEllipse(QPoint(ux, uy), 24, 24)
            if target:
                painter.setPen(QPen(QColor(CYAN), 1))
                painter.drawLine(ux, uy, tx, ty)

        # Bottom progress bar
        bar_w = min(760, self.width() - 120)
        bar_x = (self.width() - bar_w) // 2
        bar_y = self.height() - 42
        painter.setPen(QPen(QColor(YELLOW), 1))
        painter.setBrush(QBrush(QColor(30, 30, 30, 220)))
        painter.drawRect(bar_x, bar_y, bar_w, 14)
        fill_w = int(max(0.0, min(1.0, progress)) * bar_w)
        painter.fillRect(bar_x, bar_y, fill_w, 14, QColor(255, 32, 32, 220))

    def _draw_calibration_summary_overlay(self, painter: QPainter):
        summary_text = str(self.shared_state.get("calibration_summary_text", "") or "")
        painter.fillRect(self.rect(), QColor(0, 0, 0, 96))

        box_w = max(420, min(980, self.width() - 120))
        box_h = 120
        box_x = (self.width() - box_w) // 2
        box_y = max(34, self.height() // 2 - box_h // 2)

        painter.setPen(QPen(QColor(GREEN), 2))
        painter.setBrush(QBrush(QColor(10, 16, 10, 220)))
        painter.drawRoundedRect(box_x, box_y, box_w, box_h, 12, 12)

        painter.setFont(QFont("Courier", 11, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(GREEN), 1))
        painter.drawText(box_x + 16, box_y + 30, "CALIBRATION OVERVIEW")

        painter.setFont(QFont("Courier", 10))
        painter.setPen(QPen(QColor(CYAN), 1))
        detail = summary_text[:220] if summary_text else "No summary data."
        painter.drawText(box_x + 16, box_y + 60, detail)

        painter.setPen(QPen(QColor(YELLOW), 1))
        painter.drawText(box_x + 16, box_y + 90, "Neutral face should now map near the screen center.")

    def paintEvent(self, event):
        calibration_active = bool(self.shared_state.get("calibration_screen_active", False))
        summary_active = bool(self.shared_state.get("calibration_summary_active", False))
        if not self._magnet_bbox and not self._agent_bbox and not calibration_active and not summary_active:
            return
        try:
            painter = QPainter(self)
            if not painter.isActive():
                return
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            if calibration_active:
                self._draw_fullscreen_calibration(painter)
            elif summary_active:
                self._draw_calibration_summary_overlay(painter)
            if self._magnet_bbox:
                x, y, w, h = self._magnet_bbox
                painter.setPen(QPen(QColor(GREEN), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(x, y, w, h)
            if self._agent_bbox:
                x, y, w, h = self._agent_bbox
                painter.setPen(QPen(QColor(RED), 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(x, y, w, h)
            painter.end()
        except Exception as e:
            logger.error(f"TargetingOverlay paintEvent error: {e}", exc_info=True)


class CamCanvas(QLabel):
    CAM_W = 294
    CAM_H = 220

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.CAM_W, self.CAM_H)
        self._pixmap      = None
        self._nose        = None
        self._landmarks   = None
        self._blendshapes = {}
        self._banner_msg  = ""
        self._banner_t    = 0.0
        self.BANNER_DUR   = 2.5
        self._calibration_active = False
        self._calibration_progress = 0.0
        self._calibration_remaining = 0.0
        self._calibration_sample_count = 0
        self._calibration_sample_target = 0
        self._calibration_nose_xy = None
        self._calibration_target_xy = (0.5, 0.5)
        self._calibration_summary_active = False
        self._calibration_summary_text = ""
        self._scan_phase = 0.0

    def set_frame(self, bgr_frame, nose_tip, landmarks=None, blendshapes=None):
        try:
            frame    = cv2.resize(bgr_frame, (self.CAM_W, self.CAM_H))
            rgb_copy = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).copy()
            h, w, ch = rgb_copy.shape
            qimg = QImage(rgb_copy.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self._pixmap      = QPixmap.fromImage(qimg)
            self._nose        = nose_tip
            self._landmarks   = landmarks
            self._blendshapes = blendshapes or {}
            self.update()
        except Exception as e:
            logger.error(f"CamCanvas set_frame error: {e}", exc_info=True)

    def trigger_banner(self, msg: str):
        self._banner_msg = msg
        self._banner_t   = time.time()

    def set_calibration_state(
        self,
        active: bool,
        progress: float = 0.0,
        remaining: float = 0.0,
        sample_count: int = 0,
        sample_target: int = 0,
        nose_xy=None,
        target_xy=None,
    ):
        self._calibration_active = bool(active)
        self._calibration_progress = max(0.0, min(1.0, float(progress or 0.0)))
        self._calibration_remaining = max(0.0, float(remaining or 0.0))
        self._calibration_sample_count = int(sample_count or 0)
        self._calibration_sample_target = int(sample_target or 0)
        self._calibration_nose_xy = nose_xy
        self._calibration_target_xy = target_xy or (0.5, 0.5)
        self.update()

    def set_calibration_summary(self, active: bool, text: str = ""):
        self._calibration_summary_active = bool(active)
        self._calibration_summary_text = str(text or "")
        self.update()

    def _lm_px(self, lm):
        # Camera frame is mirrored before display, so mirror x for overlays too.
        return int((1.0 - lm.x) * self.CAM_W), int(lm.y * self.CAM_H)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            if not painter.isActive():
                return
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            if self._pixmap:
                painter.drawPixmap(0, 0, self._pixmap)
            else:
                painter.fillRect(self.rect(), QColor(BG))

            self._scan_phase = (self._scan_phase + 0.035) % 1.0
            self._draw_scan_sweep(painter)

            # Corner brackets
            painter.setPen(QPen(QColor(CYAN), 2))
            pad, cl = 8, 20
            W, H = self.CAM_W, self.CAM_H
            for ox, oy, sx, sy in [
                (pad,   pad,    1,  1), (W-pad, pad,   -1,  1),
                (pad,   H-pad,  1, -1), (W-pad, H-pad, -1, -1),
            ]:
                painter.drawLine(ox, oy, ox + sx*cl, oy)
                painter.drawLine(ox, oy, ox, oy + sy*cl)

            if self._landmarks:
                self._draw_eyebrows(painter)
                self._draw_eyes(painter)

            # Nose reticle
            if self._nose:
                nx = int((1.0 - self._nose['x']) * W)
                ny = int(self._nose['y'] * H)
                pulse = 1.0 + 0.22 * math.sin(time.time() * 5.8)
                outer_r = max(11, int(14 * pulse))
                painter.setPen(QPen(QColor(CYAN), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPoint(nx, ny), outer_r, outer_r)
                painter.setPen(QPen(QColor(CYAN), 2))
                painter.drawEllipse(QPoint(nx, ny), 7, 7)
                painter.setBrush(QBrush(QColor(RED)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPolygon(QPolygon([
                    QPoint(nx,   ny-4), QPoint(nx+4, ny),
                    QPoint(nx,   ny+4), QPoint(nx-4, ny),
                ]))

            self._draw_tracking_chip(painter)

            if self._calibration_active:
                self._draw_calibration_overlay(painter)
            elif self._calibration_summary_active:
                self._draw_calibration_summary(painter)

            self._draw_banner(painter)
            painter.end()
        except Exception as e:
            logger.error(f"CamCanvas paintEvent error: {e}", exc_info=True)

    def _draw_scan_sweep(self, painter: QPainter):
        if not self._pixmap:
            return
        sweep_h = 26
        center_y = int(self._scan_phase * (self.CAM_H + sweep_h)) - sweep_h
        painter.setOpacity(0.22)
        painter.fillRect(0, center_y, self.CAM_W, sweep_h, QColor(48, 223, 255, 95))
        painter.setOpacity(0.38)
        painter.setPen(QPen(QColor(48, 223, 255, 160), 1))
        painter.drawLine(0, center_y + sweep_h // 2, self.CAM_W, center_y + sweep_h // 2)
        painter.setOpacity(1.0)

    def _draw_tracking_chip(self, painter: QPainter):
        tracking_ready = bool(self._landmarks and self._nose)
        label = "FACE TRACKING LOCKED" if tracking_ready else "SCANNING FOR FACE..."
        chip_color = QColor(WHITE)
        bg_color = QColor(0, 0, 0, 212)
        chip_w = self.CAM_W - 14
        chip_h = 20
        chip_x = 7
        chip_y = 7

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(chip_color, 1))
        painter.drawRoundedRect(chip_x, chip_y, chip_w, chip_h, 6, 6)
        painter.setPen(QPen(chip_color, 1))
        painter.setFont(QFont("Courier", 8, QFont.Weight.Bold))
        painter.drawText(chip_x + 8, chip_y + 14, label)

    def _draw_eyes(self, painter: QPainter):
        lms = self._landmarks
        bs  = self._blendshapes

        pairs = [
            (L_EYE_TOP, L_EYE_BOT, L_EYE_INNER, L_EYE_OUTER,
             bs.get("eyeBlinkLeft",   0.0),
             bs.get("eyeLookInLeft",  0.0), bs.get("eyeLookOutLeft",  0.0),
             bs.get("eyeLookUpLeft",  0.0), bs.get("eyeLookDownLeft", 0.0)),
            (R_EYE_TOP, R_EYE_BOT, R_EYE_INNER, R_EYE_OUTER,
             bs.get("eyeBlinkRight",  0.0),
             bs.get("eyeLookInRight", 0.0), bs.get("eyeLookOutRight",  0.0),
             bs.get("eyeLookUpRight", 0.0), bs.get("eyeLookDownRight", 0.0)),
        ]

        for top_i, bot_i, inn_i, out_i, blink, lk_in, lk_out, lk_up, lk_dn in pairs:
            top = _safe_lm(lms, top_i); bot = _safe_lm(lms, bot_i)
            inn = _safe_lm(lms, inn_i); out = _safe_lm(lms, out_i)
            if not all([top, bot, inn, out]):
                continue

            cx = int((1.0 - ((inn.x + out.x) / 2)) * self.CAM_W)
            cy = int(((top.y + bot.y) / 2) * self.CAM_H)

            # Use raw geometry — no amplification, cap height to 40% of width
            ew = max(4, int(abs(inn.x - out.x) * self.CAM_W))
            raw_eh = int(abs(top.y - bot.y) * self.CAM_H)
            eh = max(2, min(raw_eh, int(ew * 0.4)))

            painter.setPen(QPen(QColor(EYE), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPoint(cx, cy), ew, eh)

            if blink > 0.55:
                painter.setPen(QPen(QColor(RED), 3))
                painter.drawLine(cx - ew, cy, cx + ew, cy)
                continue

            # Gaze — clamped to stay inside ellipse
            # Invert horizontal gaze offset to match mirrored camera display.
            gx = int((lk_out - lk_in) * ew * 0.45)
            gy = int((lk_dn  - lk_up)  * eh * 0.45)
            gx = max(-ew + 2, min(gx, ew - 2))
            gy = max(-eh + 1, min(gy, eh - 1))

            iris_r = max(2, ew // 4)
            painter.setBrush(QBrush(QColor(CYAN)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(cx + gx, cy + gy), iris_r, iris_r)
            painter.setBrush(QBrush(QColor(BG)))
            painter.drawEllipse(QPoint(cx + gx, cy + gy), max(1, iris_r // 2), max(1, iris_r // 2))
            painter.setBrush(QBrush(QColor(EYE)))
            painter.drawEllipse(QPoint(cx + gx + 1, cy + gy - 1), 1, 1)

    def _draw_eyebrows(self, painter: QPainter):
        lms = self._landmarks
        bs  = self._blendshapes
        inner_up = bs.get("browInnerUp", 0.0)

        pairs = [
            (L_BROW_INNER, L_BROW_OUTER,
             bs.get("browOuterUpLeft",  0.0) + inner_up * 0.5,
             bs.get("browDownLeft",  0.0)),
            (R_BROW_INNER, R_BROW_OUTER,
             bs.get("browOuterUpRight", 0.0) + inner_up * 0.5,
             bs.get("browDownRight", 0.0)),
        ]

        for inn_i, out_i, brow_up, brow_dn in pairs:
            inn = _safe_lm(lms, inn_i); out = _safe_lm(lms, out_i)
            if not inn or not out:
                continue
            x1, y1 = self._lm_px(inn)
            x2, y2 = self._lm_px(out)
            intensity = brow_up - brow_dn
            if intensity > 0.12:
                color, width = QColor(GREEN), 3
            elif intensity < -0.12:
                color, width = QColor(RED), 3
            else:
                color, width = QColor(GRAY), 2
            painter.setPen(QPen(color, width))
            painter.drawLine(x1, y1, x2, y2)

    def _draw_banner(self, painter: QPainter):
        if not self._banner_msg:
            return
        elapsed = time.time() - self._banner_t
        if elapsed >= self.BANNER_DUR:
            self._banner_msg = ""
            return
        BH = 30
        slide_dur = 0.15
        by = self.CAM_H - BH if elapsed >= slide_dur else self.CAM_H - int(BH * elapsed / slide_dur)
        fade_start = self.BANNER_DUR - 0.4
        alpha = max(0.0, 1.0 - (elapsed - fade_start) / 0.4) if elapsed > fade_start else 1.0
        painter.setOpacity(alpha * 0.92)
        painter.fillRect(0, by, self.CAM_W, BH, QColor(0, 0, 0, 220))
        painter.setPen(QPen(QColor(WHITE), 1))
        painter.drawLine(0, by, self.CAM_W, by)
        painter.setOpacity(alpha)
        painter.setPen(QPen(QColor(WHITE)))
        painter.setFont(QFont("Courier", 9, QFont.Weight.Bold))
        painter.drawText(0, by, self.CAM_W, BH, Qt.AlignmentFlag.AlignCenter, self._banner_msg)
        painter.setOpacity(1.0)

    def _draw_calibration_overlay(self, painter: QPainter):
        tx_norm, ty_norm = self._calibration_target_xy if self._calibration_target_xy else (0.5, 0.5)
        tx = int((1.0 - float(tx_norm)) * self.CAM_W)
        ty = int(float(ty_norm) * self.CAM_H)

        painter.setPen(QPen(QColor(RED), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPoint(tx, ty), 18, 18)
        painter.drawLine(tx - 24, ty, tx + 24, ty)
        painter.drawLine(tx, ty - 24, tx, ty + 24)

        if self._calibration_nose_xy:
            nx = int((1.0 - float(self._calibration_nose_xy[0])) * self.CAM_W)
            ny = int(float(self._calibration_nose_xy[1]) * self.CAM_H)
            painter.setPen(QPen(QColor(CYAN), 2))
            painter.setBrush(QBrush(QColor(CYAN)))
            painter.drawEllipse(QPoint(nx, ny), 5, 5)
            painter.setPen(QPen(QColor(CYAN), 1))
            painter.drawLine(nx, ny, tx, ty)

        # Top instruction box
        painter.setOpacity(0.86)
        painter.fillRect(8, 8, self.CAM_W - 16, 30, QColor(7, 16, 26))
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor(YELLOW), 1))
        painter.drawRect(8, 8, self.CAM_W - 16, 30)
        painter.setFont(QFont("Courier", 9, QFont.Weight.Bold))
        txt = f"CALIBRATING {self._calibration_remaining:.1f}s  ({self._calibration_sample_count}/{max(1, self._calibration_sample_target)})"
        painter.drawText(12, 28, txt)

        # Bottom progress bar
        bar_x = 10
        bar_w = self.CAM_W - 20
        bar_y = self.CAM_H - 14
        painter.fillRect(bar_x, bar_y, bar_w, 8, QColor(22, 28, 36))
        fill_w = int(bar_w * self._calibration_progress)
        painter.fillRect(bar_x, bar_y, fill_w, 8, QColor(46, 215, 255))
        painter.setPen(QPen(QColor(46, 215, 255), 1))
        painter.drawRect(bar_x, bar_y, bar_w, 8)

    def _draw_calibration_summary(self, painter: QPainter):
        box_x = 8
        box_y = self.CAM_H - 64
        box_w = self.CAM_W - 16
        box_h = 54
        painter.setOpacity(0.88)
        painter.fillRect(box_x, box_y, box_w, box_h, QColor(7, 16, 26))
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor(GREEN), 1))
        painter.drawRect(box_x, box_y, box_w, box_h)
        painter.setFont(QFont("Courier", 9, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(GREEN), 1))
        painter.drawText(box_x + 6, box_y + 16, "CALIBRATION OVERVIEW")
        painter.setPen(QPen(QColor(CYAN), 1))
        detail = self._calibration_summary_text[:220] if self._calibration_summary_text else "No summary data."
        painter.drawText(box_x + 6, box_y + 34, detail)
        painter.setPen(QPen(QColor(YELLOW), 1))
        painter.drawText(box_x + 6, box_y + 49, "Neutral face should map to screen center.")


class UIOverlay(BaseUIEngine):
    STATUS_HOLD_SECS = 15.0
    WINDOW_MARGIN_PX = 12

    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict, audio_player):
        self.data_queue   = data_queue
        self.config       = config
        self.shared_state = shared_state
        self.audio_player = audio_player

        self._app            = None
        self._win            = None
        self._cam_canvas     = None
        self._lbl_status     = None
        self._lbl_listening  = None
        self._targeting      = None
        self._btn_start      = None
        self._last_voice_str = ""
        self._fps_dq         = collections.deque(maxlen=30)
        self._timer          = None
        self._last_status    = "AWAITING COMMAND"
        self._last_status_t  = 0.0
        self._calibration_handshake_sent = False

    def start(self):
        logger.info("Starting UI Overlay...")
        try:
            self.shared_state["ui_ready"] = False
            self.shared_state["targeting_overlay_ready"] = False
            self.shared_state["calibration_allow_start"] = False
            self.shared_state["start_tracking_requested"] = False
            safe_argv = [sys.argv[0]] if sys.argv else ["gesturos"]
            self._app = QApplication.instance() or QApplication(safe_argv)
            self._app.setApplicationName("GesturOS")
            self._app.setOrganizationName("GesturOS")
            self._app.setQuitOnLastWindowClosed(False)

            self._build_ui()
            self.shared_state["ui_ready"] = True

            self._timer = QTimer()
            self._timer.timeout.connect(self._update_frame)
            self._timer.start(30)

            QTimer.singleShot(0, self._init_targeting_overlay)

            logger.debug("Entering Qt event loop.")
            self._app.exec()

        except Exception as e:
            logger.error(f"UI Overlay fatal error: {e}", exc_info=True)

    def stop(self):
        try:
            self.shared_state["ui_ready"] = False
            self.shared_state["targeting_overlay_ready"] = False
            self.shared_state["calibration_allow_start"] = False
            self.shared_state["start_tracking_requested"] = False
            if self._timer:
                self._timer.stop()
            if self._app:
                self._app.quit()
        except Exception:
            pass

    def _init_targeting_overlay(self):
        try:
            self._targeting = TargetingOverlay(self.shared_state)
            self.shared_state["targeting_overlay_ready"] = True
            logger.info("TargetingOverlay initialized successfully.")
        except Exception as e:
            logger.error(f"Could not create TargetingOverlay: {e}", exc_info=True)
            self._targeting = None
            self.shared_state["targeting_overlay_ready"] = False

    def _build_ui(self):
        win = QWidget()
        win.setWindowTitle("GesturOS")
        win.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        win.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        win.setStyleSheet(
            f"font-family: Courier; background-color: {BG}; color: {WHITE};"
        )

        outer = QVBoxLayout(win)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ border: 2px solid {WHITE}; background-color: {BG}; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QLabel("GESTUROS")
        hdr.setFont(QFont("Courier", 15, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {WHITE}; border: none; letter-spacing: 1px;")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hdr)

        layout.addWidget(self._hline(WHITE))

        # ── Action status (big, 15s hold) ─────────────────────────────────
        self._lbl_status = QLabel("AWAITING COMMAND")
        self._lbl_status.setFont(QFont("Courier", 16, QFont.Weight.Bold))
        self._lbl_status.setStyleSheet(f"color: {WHITE}; border: none;")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_status.setWordWrap(True)
        layout.addWidget(self._lbl_status)

        # ── Voice listening sub-label ─────────────────────────────────────
        self._lbl_listening = QLabel("Listening for wake word...")
        self._lbl_listening.setFont(QFont("Courier", 12))
        self._lbl_listening.setStyleSheet(f"color: {WHITE}; border: none;")
        self._lbl_listening.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_listening.setWordWrap(True)
        layout.addWidget(self._lbl_listening)
        self._btn_start = self._make_button("PLAY + CALIBRATE", WHITE, self._on_start_tracking_clicked)
        layout.addWidget(self._btn_start)

        layout.addWidget(self._hline(WHITE))

        # ── Camera feed ───────────────────────────────────────────────────
        self._cam_canvas = CamCanvas()
        cam_row = QHBoxLayout()
        cam_row.addStretch()
        cam_row.addWidget(self._cam_canvas)
        cam_row.addStretch()
        layout.addLayout(cam_row)

        layout.addWidget(self._hline(WHITE))

        # ── Commands ──────────────────────────────────────────────────────
        cmd_hdr = QLabel("VOICE COMMANDS")
        cmd_hdr.setFont(QFont("Courier", 12, QFont.Weight.Bold))
        cmd_hdr.setStyleSheet(f"color: {WHITE}; border: none;")
        cmd_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(cmd_hdr)

        for action, phrase, result in COMMANDS:
            layout.addWidget(self._cmd_row(action, phrase, result))

        layout.addWidget(self._hline(WHITE))

        outer.addWidget(frame)
        win.adjustSize()
        # Keep the panel compact while increasing legibility.
        win.setFixedWidth(self._cam_canvas.CAM_W + 44)

        win.show()
        self._win = win
        self._position_main_window_bottom_right()
        logger.debug(f"Main UI window shown: {win.width()}x{win.height()} at ({win.x()},{win.y()})")

    def _position_main_window_bottom_right(self):
        if not self._win:
            return
        screen_obj = QApplication.primaryScreen()
        if not screen_obj:
            return

        ag = screen_obj.availableGeometry()
        margin = self.WINDOW_MARGIN_PX
        target_x = ag.x() + ag.width() - self._win.width() - margin
        target_y = ag.y() + ag.height() - self._win.height() - margin
        # Clamp so the panel always stays fully visible above taskbar/docks.
        target_x = max(ag.x(), target_x)
        target_y = max(ag.y(), target_y)
        self._win.move(target_x, target_y)

    def _hline(self, color=RED):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {color}; border: 1px solid {color}; max-height: 1px;")
        return line

    def _cmd_row(self, action: str, phrase: str, result: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("border: none; background: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 1, 2, 1)
        h.setSpacing(4)

        a = QLabel(action)
        a.setFixedWidth(48)
        a.setFont(QFont("Courier", 11, QFont.Weight.Bold))
        a.setStyleSheet(f"color: {WHITE}; border: none;")
        h.addWidget(a)

        detail = QLabel(f"{phrase}   {result}")
        detail.setFont(QFont("Courier", 11))
        detail.setStyleSheet(f"color: {WHITE}; border: none;")
        detail.setWordWrap(True)
        h.addWidget(detail, 1)
        return row

    def _make_button(self, text: str, border_color: str, click_handler):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Courier", 11, QFont.Weight.Bold))
        btn.setFixedHeight(34)
        btn.setStyleSheet(
            "QPushButton {"
            f"color: {border_color};"
            "background-color: #0b0b0b;"
            f"border: 1px solid {border_color};"
            "padding: 5px 10px;"
            "}"
            "QPushButton:hover { background-color: #1a1a1a; }"
            "QPushButton:pressed { background-color: #030303; }"
        )
        btn.clicked.connect(click_handler)
        return btn

    def _start_calibration_and_intro(self):
        self._calibration_handshake_sent = False
        self.shared_state["tracking_paused"] = False
        self.shared_state["start_tracking_requested"] = True
        self.shared_state["request_quick_calibration"] = True
        self.shared_state["calibration_allow_start"] = False
        self.shared_state["calibration_summary_active"] = False
        if self.shared_state.get("targeting_overlay_ready", False):
            self.shared_state["currently_doing"] = "PLAY REQUESTED (WAITING FOR CAMERA FRAME)"
        else:
            self.shared_state["currently_doing"] = "PLAY REQUESTED (WAITING FOR CALIBRATION OVERLAY)"
        self.shared_state["voice_status"] = "STARTED: GESTUROS INTRO + CALIBRATION"
        if self._cam_canvas:
            self._cam_canvas.trigger_banner("STARTED: CALIBRATING")
        if not self.shared_state.get("dictation_active", False):
            if self.audio_player and hasattr(self.audio_player, "play_gesturos_intro"):
                self.audio_player.play_gesturos_intro()
            elif self.audio_player and hasattr(self.audio_player, "play_judge_intro"):
                self.audio_player.play_judge_intro()
            elif self.audio_player:
                self.audio_player.speak(
                    "Welcome to GesturOS. I will now calibrate your neutral pose. Move your blue marker into each red target and hold briefly."
                )
        if self.audio_player:
            self.audio_player.play('lock_engage')

    def _on_start_tracking_clicked(self):
        if self._btn_start:
            self._btn_start.hide()
        self._start_calibration_and_intro()

    def _update_frame(self):
        try:
            payload = None
            while True:
                try:
                    payload = self.data_queue.get_nowait()
                except queue.Empty:
                    break

            self._fps_dq.append(time.time())

            # ── Status with 15s hold ──────────────────────────────────────
            current_status = self.shared_state.get("currently_doing", "AWAITING COMMAND")
            now = time.time()

            if current_status != "AWAITING COMMAND":
                self._last_status   = current_status
                self._last_status_t = now

            if current_status == "AWAITING COMMAND" and (now - self._last_status_t < self.STATUS_HOLD_SECS):
                display_status = self._last_status
            else:
                display_status = current_status

            self._lbl_status.setText(display_status)

            # ── Listening sub-label ───────────────────────────────────────
            voice_status = self.shared_state.get("voice_status", "")
            if voice_status:
                self._lbl_listening.setText(voice_status)

            # ── Camera + tracking ─────────────────────────────────────────
            if payload:
                frame = payload.get('frame')
                if frame is not None:
                    self._cam_canvas.set_frame(
                        frame,
                        payload.get('nose_tip'),
                        payload.get('landmarks'),
                        payload.get('blendshapes'),
                    )
                    if (
                        self.shared_state.get("ui_ready", False)
                        and self.shared_state.get("targeting_overlay_ready", False)
                        and self.shared_state.get("start_tracking_requested", False)
                    ):
                        self.shared_state["calibration_allow_start"] = True
                        self.shared_state["start_tracking_requested"] = False
                        if not self._calibration_handshake_sent:
                            logger.info("Calibration overlay handshake ready. Quick calibration can start.")
                            self._calibration_handshake_sent = True

                if voice_status and voice_status != self._last_voice_str:
                    self._cam_canvas.trigger_banner(voice_status)
                self._last_voice_str = voice_status

            fullscreen_calibration = bool(self.shared_state.get("calibration_screen_active", False))
            self._cam_canvas.set_calibration_state(
                active=self.shared_state.get("calibration_active", False) and not fullscreen_calibration,
                progress=self.shared_state.get("calibration_progress", 0.0),
                remaining=self.shared_state.get("calibration_remaining", 0.0),
                sample_count=self.shared_state.get("calibration_sample_count", 0),
                sample_target=self.shared_state.get("calibration_sample_target", 0),
                nose_xy=self.shared_state.get("calibration_nose_xy"),
                target_xy=self.shared_state.get("calibration_target_xy", (0.5, 0.5)),
            )
            summary_active = bool(self.shared_state.get("calibration_summary_active", False))
            summary_until = float(self.shared_state.get("calibration_summary_until", 0.0) or 0.0)
            if summary_active and summary_until and time.time() > summary_until:
                self.shared_state["calibration_summary_active"] = False
                summary_active = False
            cam_summary_active = summary_active and not bool(
                self.shared_state.get("targeting_overlay_ready", False)
            )
            self._cam_canvas.set_calibration_summary(
                active=cam_summary_active,
                text=self.shared_state.get("calibration_summary_text", ""),
            )

            if self._btn_start:
                tracking_paused = bool(self.shared_state.get("tracking_paused", False))
                if tracking_paused:
                    self._btn_start.show()
                else:
                    self._btn_start.hide()

                if self.shared_state.get("calibration_active", False):
                    self._btn_start.setText("CALIBRATING...")
                    self._btn_start.setEnabled(False)
                else:
                    self._btn_start.setEnabled(True)
                    self._btn_start.setText("PLAY + CALIBRATE")

            if self._targeting:
                self._targeting.update_bboxes()

            # Keep HUD anchored in bottom-right above taskbar while content changes.
            self._position_main_window_bottom_right()

        except Exception as e:
            logger.error(f"_update_frame error: {e}", exc_info=True)


