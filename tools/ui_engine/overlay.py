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
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor, QPainter, QPen, QBrush, QPolygon

BG     = "#000000"
BORDER = "#FFFF00"
TEXT   = "#00FFFF"
ACCENT = "#FF004D"
YELLOW = "#FFFF00"
GREEN  = "#00FF00"
RED_OL = "#FF0000"


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
        if screen is None:
            logger.error("TargetingOverlay: primaryScreen() is None, using fallback geometry.")
            self.setGeometry(0, 0, 1920, 1080)
        else:
            self.setGeometry(screen.geometry())
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
                logger.warning("TargetingOverlay: QPainter failed to activate, skipping paint.")
                return
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if self._magnet_bbox:
                x, y, w, h = self._magnet_bbox
                painter.setPen(QPen(QColor(GREEN), 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(x, y, w, h)
            if self._agent_bbox:
                x, y, w, h = self._agent_bbox
                painter.setPen(QPen(QColor(RED_OL), 4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(x, y, w, h)
            painter.end()
        except Exception as e:
            logger.error(f"TargetingOverlay paintEvent error: {e}", exc_info=True)


class CamCanvas(QLabel):
    CAM_W = 280
    CAM_H = 210

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.CAM_W, self.CAM_H)
        self._pixmap     = None
        self._nose       = None
        self._banner_msg = ""
        self._banner_t   = 0.0
        self.BANNER_DUR  = 2.0

    def set_frame(self, bgr_frame, nose_tip):
        try:
            frame    = cv2.resize(bgr_frame, (self.CAM_W, self.CAM_H))
            rgb_copy = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).copy()
            h, w, ch = rgb_copy.shape
            qimg = QImage(rgb_copy.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self._pixmap = QPixmap.fromImage(qimg)
            self._nose   = nose_tip
            self.update()
        except Exception as e:
            logger.error(f"CamCanvas set_frame error: {e}", exc_info=True)

    def trigger_banner(self, msg: str):
        self._banner_msg = msg
        self._banner_t   = time.time()

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

            painter.setPen(QPen(QColor(BORDER), 2))
            pad, cl = 10, 20
            W, H = self.CAM_W, self.CAM_H
            for ox, oy, sx, sy in [
                (pad,   pad,    1,  1),
                (W-pad, pad,   -1,  1),
                (pad,   H-pad,  1, -1),
                (W-pad, H-pad, -1, -1),
            ]:
                painter.drawLine(ox, oy, ox + sx*cl, oy)
                painter.drawLine(ox, oy, ox, oy + sy*cl)

            if self._nose:
                nx = int(self._nose['x'] * W)
                ny = int(self._nose['y'] * H)
                painter.setPen(QPen(QColor(TEXT), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPoint(nx, ny), 15, 15)
                painter.setPen(QPen(QColor(TEXT), 2))
                painter.drawEllipse(QPoint(nx, ny), 8, 8)
                painter.setBrush(QBrush(QColor(ACCENT)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPolygon(QPolygon([
                    QPoint(nx,   ny-4),
                    QPoint(nx+4, ny),
                    QPoint(nx,   ny+4),
                    QPoint(nx-4, ny),
                ]))

            self._draw_banner(painter)
            painter.end()
        except Exception as e:
            logger.error(f"CamCanvas paintEvent error: {e}", exc_info=True)

    def _draw_banner(self, painter: QPainter):
        if not self._banner_msg:
            return
        elapsed = time.time() - self._banner_t
        if elapsed >= self.BANNER_DUR:
            self._banner_msg = ""
            return
        BH        = 24
        slide_dur = 0.2
        by        = self.CAM_H - BH if elapsed >= slide_dur else self.CAM_H - int(BH * elapsed / slide_dur)
        fade_start = self.BANNER_DUR - 0.5
        alpha      = max(0.0, 1.0 - (elapsed - fade_start) / 0.5) if elapsed > fade_start else 1.0
        painter.setOpacity(alpha * 0.9)
        painter.fillRect(0, by, self.CAM_W, BH, QColor(30, 30, 30))
        painter.setPen(QPen(QColor(138, 43, 226), 1))
        painter.drawLine(0, by, self.CAM_W, by)
        painter.setOpacity(alpha)
        painter.setPen(QPen(QColor("white")))
        painter.setFont(QFont("Courier", 8))
        painter.drawText(0, by, self.CAM_W, BH, Qt.AlignmentFlag.AlignCenter, self._banner_msg)
        painter.setOpacity(1.0)


class UIOverlay(BaseUIEngine):
    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict, audio_player):
        self.data_queue   = data_queue
        self.config       = config
        self.shared_state = shared_state
        self.audio_player = audio_player

        self._app            = None
        self._win            = None
        self._cam_canvas     = None
        self._lbl_status     = None
        self._targeting      = None
        self._last_voice_str = ""
        self._fps_dq         = collections.deque(maxlen=30)
        self._timer          = None

    def start(self):
        logger.info("Starting UI Overlay...")
        try:
            safe_argv = [sys.argv[0]] if sys.argv else ["accessibot"]
            self._app = QApplication.instance() or QApplication(safe_argv)
            self._app.setQuitOnLastWindowClosed(False)

            self._build_ui()

            self._timer = QTimer()
            self._timer.timeout.connect(self._update_frame)
            self._timer.start(30)

            QTimer.singleShot(500, self._init_targeting_overlay)

            logger.debug("Entering Qt event loop.")
            exit_code = self._app.exec()
            logger.info(f"Qt event loop exited with code {exit_code}.")

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
            logger.error(f"Could not create TargetingOverlay (non-fatal): {e}", exc_info=True)
            self._targeting = None

    def _build_ui(self):
        win = QWidget()
        win.setWindowTitle("AccessiBot UI")
        win.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        win.setStyleSheet(f"background-color: {BG};")

        outer = QVBoxLayout(win)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ border: 3px solid {BORDER}; background-color: {BG}; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self._lbl_status = QLabel("AWAITING COMMAND")
        self._lbl_status.setFont(QFont("Courier", 10, QFont.Weight.Bold))
        self._lbl_status.setStyleSheet(f"color: {TEXT}; border: none;")
        layout.addWidget(self._lbl_status)

        layout.addWidget(self._hline())

        for text in [
            "PREDICTIVE MAGNETISM: SNAP",
            "ELEVENLABS: TTS READY",
            "AUTONOMOUS AI: ACTIVE",
        ]:
            layout.addWidget(self._info_row(text))

        layout.addWidget(self._hline())

        self._cam_canvas = CamCanvas()
        cam_row = QHBoxLayout()
        cam_row.addStretch()
        cam_row.addWidget(self._cam_canvas)
        cam_row.addStretch()
        layout.addLayout(cam_row)

        outer.addWidget(frame)
        win.adjustSize()

        screen_obj = QApplication.primaryScreen()
        if screen_obj:
            screen = screen_obj.availableGeometry()
            win.move(screen.right() - win.width() - 20, screen.bottom() - win.height() - 60)
        else:
            logger.warning("_build_ui: primaryScreen() is None, skipping window positioning.")

        win.show()
        self._win = win
        logger.debug(f"Main UI window shown: {win.width()}x{win.height()} at ({win.x()},{win.y()})")

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER}; border: 1px solid {BORDER};")
        return line

    def _info_row(self, text: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("border: none; background: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        dot = QLabel("■")
        dot.setFixedWidth(14)
        dot.setStyleSheet(f"color: {ACCENT}; border: none; font-size: 8px;")
        h.addWidget(dot)
        lbl = QLabel(text)
        lbl.setFont(QFont("Courier", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {YELLOW}; border: none; font-style: italic;")
        h.addWidget(lbl)
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

            if payload:
                frame = payload.get('frame')
                if frame is not None:
                    self._lbl_status.setText(
                        self.shared_state.get("currently_doing", "AWAITING COMMAND")
                    )
                    self._cam_canvas.set_frame(frame, payload.get('nose_tip'))

                voice_status = self.shared_state.get("voice_status", "")
                if voice_status and voice_status != self._last_voice_str:
                    self._cam_canvas.trigger_banner(voice_status)
                self._last_voice_str = voice_status

            if self._targeting:
                self._targeting.update_bboxes()

        except Exception as e:
            logger.error(f"_update_frame error: {e}", exc_info=True)