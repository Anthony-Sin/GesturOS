import queue
import time
import collections
import logging
import sys
import os
import cv2

from tools.interfaces import BaseUIEngine

logger = logging.getLogger(__name__)

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_FONT_DPI"] = "96"
os.environ["QT_DPI_ADJUSTMENT_POLICY"] = "AdjustDpi"

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor, QPainter, QPen, QBrush, QPolygon

BG     = "#0a0a0a"
RED    = "#FF004D"
YELLOW = "#FFFF00"
CYAN   = "#00FFFF"
GREEN  = "#00FF00"
GRAY   = "#555555"
EYE    = "#7CFF00"

# MediaPipe landmark indices
L_EYE_TOP = 159; L_EYE_BOT = 145; L_EYE_INNER = 133; L_EYE_OUTER = 33
R_EYE_TOP = 386; R_EYE_BOT = 374; R_EYE_INNER = 362; R_EYE_OUTER = 263
L_BROW_INNER = 107; L_BROW_OUTER = 70
R_BROW_INNER = 336; R_BROW_OUTER = 300

COMMANDS = [
    ("SAY",  "'AGENT [task]'",   "-> AI agent"),
    ("SAY",  "'TRANSCRIBE ME'",  "-> dictation"),
    ("SAY",  "'TRANSCRIBE DONE'", "-> stop dictation"),
    ("SAY",  "'PRESS [key]'",    "-> key press"),
    ("SAY",  "'OPEN / CLICK'",   "-> click target"),
    ("SAY",  "'STOP / CANCEL'",  "-> abort"),
    ("SAY",  "'SNIPER MODE'",    "-> toggle snap aim"),
    ("HOLD", "gaze still 5s",    "-> lock cursor"),
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
        self.setGeometry(screen.geometry() if screen else QRect(0, 0, 1920, 1080))
        self.show()
        logger.debug("TargetingOverlay shown.")

    def update_bboxes(self):
        self._magnet_bbox = self.shared_state.get("magnet_target_bbox")
        self._agent_bbox  = self.shared_state.get("agent_target_bbox")
        self.update()

    def paintEvent(self, event):
        if not self._magnet_bbox and not self._agent_bbox:
            return
        try:
            painter = QPainter(self)
            if not painter.isActive():
                return
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
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

            # Corner brackets
            painter.setPen(QPen(QColor(RED), 2))
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
                painter.setPen(QPen(QColor(CYAN), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPoint(nx, ny), 13, 13)
                painter.setPen(QPen(QColor(CYAN), 2))
                painter.drawEllipse(QPoint(nx, ny), 6, 6)
                painter.setBrush(QBrush(QColor(RED)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPolygon(QPolygon([
                    QPoint(nx,   ny-4), QPoint(nx+4, ny),
                    QPoint(nx,   ny+4), QPoint(nx-4, ny),
                ]))

            self._draw_banner(painter)
            painter.end()
        except Exception as e:
            logger.error(f"CamCanvas paintEvent error: {e}", exc_info=True)

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

            painter.setPen(QPen(QColor(EYE), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPoint(cx, cy), ew, eh)

            if blink > 0.55:
                painter.setPen(QPen(QColor(YELLOW), 2))
                painter.drawLine(cx - ew, cy, cx + ew, cy)
                continue

            # Gaze — clamped to stay inside ellipse
            # Invert horizontal gaze offset to match mirrored camera display.
            gx = int((lk_out - lk_in) * ew * 0.45)
            gy = int((lk_dn  - lk_up)  * eh * 0.45)
            gx = max(-ew + 2, min(gx, ew - 2))
            gy = max(-eh + 1, min(gy, eh - 1))

            iris_r = max(2, ew // 4)
            painter.setBrush(QBrush(QColor(EYE)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(cx + gx, cy + gy), iris_r, iris_r)
            painter.setBrush(QBrush(QColor(BG)))
            painter.drawEllipse(QPoint(cx + gx, cy + gy), max(1, iris_r // 2), max(1, iris_r // 2))

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
                color, width = QColor(YELLOW), 2
            elif intensity < -0.12:
                color, width = QColor(RED), 2
            else:
                color, width = QColor(GRAY), 1
            painter.setPen(QPen(color, width))
            painter.drawLine(x1, y1, x2, y2)

    def _draw_banner(self, painter: QPainter):
        if not self._banner_msg:
            return
        elapsed = time.time() - self._banner_t
        if elapsed >= self.BANNER_DUR:
            self._banner_msg = ""
            return
        BH = 26
        slide_dur = 0.15
        by = self.CAM_H - BH if elapsed >= slide_dur else self.CAM_H - int(BH * elapsed / slide_dur)
        fade_start = self.BANNER_DUR - 0.4
        alpha = max(0.0, 1.0 - (elapsed - fade_start) / 0.4) if elapsed > fade_start else 1.0
        painter.setOpacity(alpha * 0.92)
        painter.fillRect(0, by, self.CAM_W, BH, QColor(20, 0, 8))
        painter.setPen(QPen(QColor(RED), 1))
        painter.drawLine(0, by, self.CAM_W, by)
        painter.setOpacity(alpha)
        painter.setPen(QPen(QColor(YELLOW)))
        painter.setFont(QFont("Courier", 8, QFont.Weight.Bold))
        painter.drawText(0, by, self.CAM_W, BH, Qt.AlignmentFlag.AlignCenter, self._banner_msg)
        painter.setOpacity(1.0)


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
        self._last_voice_str = ""
        self._fps_dq         = collections.deque(maxlen=30)
        self._timer          = None
        self._last_status    = "AWAITING COMMAND"
        self._last_status_t  = 0.0

    def start(self):
        logger.info("Starting UI Overlay...")
        try:
            safe_argv = [sys.argv[0]] if sys.argv else ["accessibot"]
            self._app = QApplication.instance() or QApplication(safe_argv)
            self._app.setApplicationName("AccessiBot")
            self._app.setOrganizationName("AccessiBot")
            self._app.setQuitOnLastWindowClosed(False)

            self._build_ui()

            self._timer = QTimer()
            self._timer.timeout.connect(self._update_frame)
            self._timer.start(30)

            QTimer.singleShot(500, self._init_targeting_overlay)

            logger.debug("Entering Qt event loop.")
            self._app.exec()

        except Exception as e:
            logger.error(f"UI Overlay fatal error: {e}", exc_info=True)

    def stop(self):
        try:
            if self._timer:
                self._timer.stop()
            if self._app:
                self._app.quit()
        except Exception:
            pass

    def _init_targeting_overlay(self):
        try:
            self._targeting = TargetingOverlay(self.shared_state)
            logger.info("TargetingOverlay initialized successfully.")
        except Exception as e:
            logger.error(f"Could not create TargetingOverlay: {e}", exc_info=True)
            self._targeting = None

    def _build_ui(self):
        win = QWidget()
        win.setWindowTitle("AccessiBot")
        win.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        win.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        win.setStyleSheet(f"background-color: {BG}; font-family: Courier;")

        outer = QVBoxLayout(win)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ border: 2px solid {RED}; background-color: {BG}; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QLabel("⬡  A C C E S S I B O T")
        hdr.setFont(QFont("Courier", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {RED}; border: none;")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hdr)

        layout.addWidget(self._hline(RED))

        # ── Action status (big, 15s hold) ─────────────────────────────────
        self._lbl_status = QLabel("AWAITING COMMAND")
        self._lbl_status.setFont(QFont("Courier", 13, QFont.Weight.Bold))
        self._lbl_status.setStyleSheet(f"color: {CYAN}; border: none;")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_status.setWordWrap(True)
        layout.addWidget(self._lbl_status)

        # ── Voice listening sub-label ─────────────────────────────────────
        self._lbl_listening = QLabel("Listening for wake word...")
        self._lbl_listening.setFont(QFont("Courier", 10))
        self._lbl_listening.setStyleSheet(f"color: {YELLOW}; border: none;")
        self._lbl_listening.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_listening.setWordWrap(True)
        layout.addWidget(self._lbl_listening)

        layout.addWidget(self._hline(YELLOW))

        # ── Camera feed ───────────────────────────────────────────────────
        self._cam_canvas = CamCanvas()
        cam_row = QHBoxLayout()
        cam_row.addStretch()
        cam_row.addWidget(self._cam_canvas)
        cam_row.addStretch()
        layout.addLayout(cam_row)

        layout.addWidget(self._hline(YELLOW))

        # ── Commands ──────────────────────────────────────────────────────
        cmd_hdr = QLabel("── VOICE COMMANDS ──")
        cmd_hdr.setFont(QFont("Courier", 10, QFont.Weight.Bold))
        cmd_hdr.setStyleSheet(f"color: {YELLOW}; border: none;")
        cmd_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(cmd_hdr)

        for action, phrase, result in COMMANDS:
            layout.addWidget(self._cmd_row(action, phrase, result))

        layout.addWidget(self._hline(RED))

        outer.addWidget(frame)
        win.adjustSize()

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
        h.setSpacing(6)

        a = QLabel(action)
        a.setFixedWidth(42)
        a.setFont(QFont("Courier", 9, QFont.Weight.Bold))
        a.setStyleSheet(f"color: {RED}; border: none;")
        h.addWidget(a)

        p = QLabel(phrase)
        p.setFont(QFont("Courier", 10, QFont.Weight.Bold))
        p.setStyleSheet(f"color: {YELLOW}; border: none;")
        h.addWidget(p)

        r = QLabel(result)
        r.setFont(QFont("Courier", 9))
        r.setStyleSheet(f"color: {CYAN}; border: none;")
        h.addWidget(r)
        h.addStretch()
        return row

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

                if voice_status and voice_status != self._last_voice_str:
                    self._cam_canvas.trigger_banner(voice_status)
                self._last_voice_str = voice_status

            if self._targeting:
                self._targeting.update_bboxes()

            # Keep HUD anchored in bottom-right above taskbar while content changes.
            self._position_main_window_bottom_right()

        except Exception as e:
            logger.error(f"_update_frame error: {e}", exc_info=True)

