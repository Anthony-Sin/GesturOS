import tkinter as tk
import queue
import cv2
from PIL import Image, ImageTk, ImageDraw
import collections
import time
import numpy as np
import random
import logging
from tools.interfaces import BaseUIEngine

logger = logging.getLogger(__name__)

# --- COLOR PALETTE ---
COLORS = {
    "bg": "#000000",
    "sidebar_bg": "#020202",
    "yellow": "#fcee0a",
    "blue": "#00f0ff",
    "pink": "#ff003c",
    "text_dim": "#555500",
    "border": "#222200"
}

class UIOverlay(BaseUIEngine):
    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict, audio_player):
        self.data_queue = data_queue
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player

        # Base Tkinter setup
        try:
            self.root = tk.Toplevel()
        except tk.TclError:
            self.root = tk.Tk()

        self.root.title("AccessiBot Neural Interface")
        self.root.configure(bg=COLORS["bg"])

        self.window_width = 340
        self.cam_width = 280
        self.cam_height = 210

        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)

        # Main Outline Frame
        self.main_frame = tk.Frame(self.root, bg=COLORS["bg"], highlightbackground=COLORS["border"], highlightthickness=2)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # --- A. Top Status Area ---
        self.status_frame = tk.Frame(self.main_frame, bg=COLORS["bg"], height=60)
        self.status_frame.pack(fill=tk.X)

        self.sync_bar_bg = tk.Frame(self.status_frame, bg="#1a1a00", height=4)
        self.sync_bar_bg.pack(fill=tk.X)
        self.sync_bar_fg = tk.Frame(self.sync_bar_bg, bg=COLORS["yellow"], width=self.window_width - 10, height=4)
        self.sync_bar_fg.place(x=0, y=0)

        status_text_frame = tk.Frame(self.status_frame, bg=COLORS["bg"], padx=15, pady=5)
        status_text_frame.pack(fill=tk.X)

        self.lbl_currently_doing = tk.Label(status_text_frame, text="AWAITING COMMAND", fg=COLORS["blue"], bg=COLORS["bg"], font=("Courier", 8, "bold"))
        self.lbl_currently_doing.pack(side=tk.LEFT)

        self.sync_label = tk.Label(status_text_frame, text="98.8%", fg=COLORS["yellow"], bg=COLORS["bg"], font=("Courier", 10, "italic bold"))
        self.sync_label.pack(side=tk.RIGHT)

        # --- B. Activity Logs ---
        # --- Toggle Button ---
        self.stats_visible = True
        self.toggle_frame = tk.Frame(self.main_frame, bg=COLORS["sidebar_bg"], pady=2)
        self.toggle_frame.pack(fill=tk.X)
        self.toggle_btn = tk.Label(self.toggle_frame, text="[-] HIDE STATS", fg=COLORS["yellow"], bg=COLORS["sidebar_bg"], font=("Courier", 8, "bold"), cursor="hand2")
        self.toggle_btn.pack(anchor="e", padx=15)
        self.toggle_btn.bind("<Button-1>", self._toggle_stats)

        # --- B. Impact Stats Panel ---
        self.stats_frame = tk.Frame(self.main_frame, bg=COLORS["sidebar_bg"], padx=15, pady=5)
        self.stats_frame.pack(fill=tk.BOTH, expand=True)

        self.stat_labels = {}
        stats = [
            ("CLICKS SAVED", "0"),
            ("VOICE CMDS", "0"),
            ("CURSOR DIST", "0 px"),
            ("SYSTEM STATUS", "ONLINE")
        ]

        for i, (title, val) in enumerate(stats):
            row = i // 2
            col = i % 2
            self._add_stat_card(title, val, row, col)

        self.log_frame = tk.Frame(self.main_frame, bg="#080800", pady=5, padx=15)
        self.log_frame.pack(fill=tk.X)
        self.logs = ["NEURAL LINK OPTIMIZING...", "SCANNING BIO-SIGNALS...", "ICE PROTECTION ACTIVE"]
        self.log_labels = []
        for msg in self.logs:
            lbl = tk.Label(self.log_frame, text=f"» {msg}", fg=COLORS["yellow"], bg="#080800", font=("Courier", 8, "italic"), anchor="w", justify=tk.LEFT)
            lbl.pack(fill=tk.X, pady=1)
            self.log_labels.append(lbl)

        # --- C. Camera View ---
        self.cam_container = tk.Frame(self.main_frame, bg=COLORS["sidebar_bg"], padx=20, pady=10)
        self.cam_container.pack(fill=tk.X)

        self.canvas = tk.Canvas(self.cam_container, width=self.cam_width, height=self.cam_height, bg="black", highlightbackground=COLORS["yellow"], highlightthickness=2)
        self.canvas.pack()
        self.image_on_canvas = None

        # State tracking for UI
        self.fps_queue = collections.deque(maxlen=30)
        self.last_voice_status = ""
        self.bio_sync = 98.8

        self.targeting_overlay = None
        self.magnet_rect_id = None
        self.agent_rect_id = None

        # Ensure window is fully rendered before setting location or overlays
        self.root.update_idletasks()
        self.root.geometry(f"{self.window_width}x{self.root.winfo_reqheight()}+{self.screen_width - self.window_width - 20}+{self.screen_height - self.root.winfo_reqheight() - 60}")

        # Schedule the targeting overlay setup safely after main loop starts
        self.root.after(200, self._setup_targeting_overlay)

    def _toggle_stats(self, event=None):
        if self.stats_visible:
            self.stats_frame.pack_forget()
            self.toggle_btn.config(text="[+] SHOW STATS")
            self.stats_visible = False
        else:
            self.stats_frame.pack(fill=tk.BOTH, expand=True, before=self.log_frame)
            self.toggle_btn.config(text="[-] HIDE STATS")
            self.stats_visible = True

    def _add_stat_card(self, title, val, row, col):
        card = tk.Frame(self.stats_frame, bg="#0a0a00", pady=4, padx=10, highlightbackground=COLORS["yellow"], highlightthickness=1)
        card.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
        self.stats_frame.grid_columnconfigure(col, weight=1)

        icon_box = tk.Label(card, text="◈", fg=COLORS["yellow"], bg="#151500", width=3, font=("Courier", 10))
        icon_box.pack(side=tk.LEFT, padx=(0, 5))
        text_f = tk.Frame(card, bg="#0a0a00")
        text_f.pack(side=tk.LEFT, fill=tk.X)
        tk.Label(text_f, text=title, fg=COLORS["blue"], bg="#0a0a00", font=("Courier", 7, "bold")).pack(anchor="w")
        val_label = tk.Label(text_f, text=val, fg=COLORS["yellow"], bg="#0a0a00", font=("Courier", 8, "bold"))
        val_label.pack(anchor="w")

        self.stat_labels[title] = val_label

    def _setup_targeting_overlay(self):
        try:
            self.targeting_overlay = tk.Toplevel(self.root)
            self.targeting_overlay.title("Targeting Overlay")
            self.trans_color = '#000001'

            try:
                self.targeting_overlay.attributes('-transparentcolor', self.trans_color)

                import ctypes
                hwnd = self.targeting_overlay.winfo_id()
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, ctypes.windll.user32.GetWindowLongW(hwnd, -20) | 0x00080000 | 0x00000020)
            except Exception as inner_e:
                logger.warning(f"OS doesn't fully support transparent Tkinter windows: {inner_e}")
                pass

            self.targeting_overlay.configure(bg=self.trans_color)
            self.targeting_overlay.overrideredirect(True)
            self.targeting_overlay.attributes('-fullscreen', True)
            self.targeting_overlay.attributes('-topmost', True)

            self.targeting_canvas = tk.Canvas(self.targeting_overlay, bg=self.trans_color, highlightthickness=0)
            self.targeting_canvas.pack(fill=tk.BOTH, expand=True)
            self._update_targeting_overlay()
        except Exception as e:
            logger.error(f"Failed to initialize targeting overlay: {e}")

    def _update_targeting_overlay(self):
        try:
            if self.targeting_overlay:
                magnet_bbox = self.shared_state.get("magnet_target_bbox")
                if magnet_bbox:
                    if self.magnet_rect_id:
                        self.targeting_canvas.coords(self.magnet_rect_id, magnet_bbox[0], magnet_bbox[1], magnet_bbox[0]+magnet_bbox[2], magnet_bbox[1]+magnet_bbox[3])
                    else:
                        self.magnet_rect_id = self.targeting_canvas.create_rectangle(magnet_bbox[0], magnet_bbox[1], magnet_bbox[0]+magnet_bbox[2], magnet_bbox[1]+magnet_bbox[3], outline="#00FF00", width=3)
                else:
                    if self.magnet_rect_id:
                        self.targeting_canvas.delete(self.magnet_rect_id)
                        self.magnet_rect_id = None

                agent_bbox = self.shared_state.get("agent_target_bbox")
                if agent_bbox:
                    if self.agent_rect_id:
                        self.targeting_canvas.coords(self.agent_rect_id, agent_bbox[0], agent_bbox[1], agent_bbox[0]+agent_bbox[2], agent_bbox[1]+agent_bbox[3])
                    else:
                        self.agent_rect_id = self.targeting_canvas.create_rectangle(agent_bbox[0], agent_bbox[1], agent_bbox[0]+agent_bbox[2], agent_bbox[1]+agent_bbox[3], outline="#FF0000", width=4)
                else:
                    if self.agent_rect_id:
                        self.targeting_canvas.delete(self.agent_rect_id)
                        self.agent_rect_id = None
        except Exception as e:
            logger.error(f"Targeting overlay error: {e}")

        self.root.after(16, self._update_targeting_overlay)

    def trigger_log(self, message):
        self.logs.pop(0)
        self.logs.append(message)
        for i, msg in enumerate(self.logs):
            self.log_labels[i].config(text=f"» {msg}")

    def update_frame(self):
        try:
            payload = None
            while True:
                try:
                    payload = self.data_queue.get_nowait()
                except queue.Empty:
                    break

            current_time = time.time()
            self.fps_queue.append(current_time)

            # --- Update Stats ---
            doing = self.shared_state.get("currently_doing", "AWAITING COMMAND")
            self.lbl_currently_doing.config(text=doing)

            self.stat_labels["CLICKS SAVED"].config(text=str(self.shared_state.get("clicks_saved", 0)))
            self.stat_labels["VOICE CMDS"].config(text=str(self.shared_state.get("voice_commands", 0)))
            dist = self.shared_state.get("cursor_distance", 0)
            self.stat_labels["CURSOR DIST"].config(text=f"{dist:,.0f} px")

            # Random jitter for Bio Sync
            if random.random() > 0.8:
                self.bio_sync = min(99.9, 98.0 + random.random() * 1.9)
                self.sync_label.config(text=f"{self.bio_sync:.1f}%")

            voice_status = self.shared_state.get("voice_status", "")
            if voice_status != self.last_voice_status and voice_status:
                self.trigger_log(voice_status)
            self.last_voice_status = voice_status

            if payload:
                frame = payload.get('frame')
                if frame is not None:
                    frame = cv2.resize(frame, (self.cam_width, self.cam_height))
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    # Draw Reticle and Text
                    text = "ACCESSIBOT_LIVE"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    scale = 0.4
                    thickness = 1
                    (text_width, text_height), _ = cv2.getTextSize(text, font, scale, thickness)
                    text_x = (self.cam_width - text_width) // 2
                    text_y = 20
                    cv2.putText(frame_rgb, text, (text_x, text_y), font, scale, (255, 0, 0), thickness + 2) # Blue Glow
                    cv2.putText(frame_rgb, text, (text_x, text_y), font, scale, (255, 240, 0), thickness) # Cyan inner

                    nose_tip = payload.get('nose_tip')
                    landmarks = payload.get('landmarks', [])

                    # Plot eye landmarks
                    if landmarks:
                        # Known mediapipe face mesh eye indices
                        eye_indices = [384, 385, 386, 387, 388, 390, 263, 362, 398, 466, 373, 374, 249, 380, 381, 382,
                                       160, 33, 161, 163, 133, 7, 173, 144, 145, 246, 153, 154, 155, 157, 158, 159]
                        for idx in eye_indices:
                            if idx < len(landmarks):
                                lm = landmarks[idx]
                                lx, ly = int(lm.x * self.cam_width), int(lm.y * self.cam_height)
                                cv2.circle(frame_rgb, (lx, ly), 1, (0, 255, 0), -1)

                    if nose_tip:
                        nx = int(nose_tip['x'] * self.cam_width)
                        ny = int(nose_tip['y'] * self.cam_height)

                        # Blue Crosshair
                        cv2.line(frame_rgb, (nx - 10, ny), (nx + 10, ny), (255, 240, 0), 1) # Cyan
                        cv2.line(frame_rgb, (nx, ny - 10), (nx, ny + 10), (255, 240, 0), 1)
                        # Red center point
                        cv2.circle(frame_rgb, (nx, ny), 3, (60, 0, 255), -1) # Pink

                    # Yellow Box Corners
                    c_len = 15
                    c_thick = 2
                    pad = 10
                    color_corn = (10, 238, 252) # Yellow
                    cv2.line(frame_rgb, (pad, pad), (pad + c_len, pad), color_corn, c_thick)
                    cv2.line(frame_rgb, (pad, pad), (pad, pad + c_len), color_corn, c_thick)
                    cv2.line(frame_rgb, (self.cam_width - pad, pad), (self.cam_width - pad - c_len, pad), color_corn, c_thick)
                    cv2.line(frame_rgb, (self.cam_width - pad, pad), (self.cam_width - pad, pad + c_len), color_corn, c_thick)
                    cv2.line(frame_rgb, (pad, self.cam_height - pad), (pad + c_len, self.cam_height - pad), color_corn, c_thick)
                    cv2.line(frame_rgb, (pad, self.cam_height - pad), (pad, self.cam_height - pad - c_len), color_corn, c_thick)
                    cv2.line(frame_rgb, (self.cam_width - pad, self.cam_height - pad), (self.cam_width - pad - c_len, self.cam_height - pad), color_corn, c_thick)
                    cv2.line(frame_rgb, (self.cam_width - pad, self.cam_height - pad), (self.cam_width - pad, self.cam_height - pad - c_len), color_corn, c_thick)

                    img = Image.fromarray(frame_rgb)
                    imgtk = ImageTk.PhotoImage(image=img)

                    if self.image_on_canvas is None:
                        self.image_on_canvas = self.canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
                    else:
                        self.canvas.itemconfig(self.image_on_canvas, image=imgtk)

                    self.canvas.image = imgtk

        except Exception as e:
            logger.error(f"UI Error: {e}")

        self.root.after(30, self.update_frame)

    def start(self):
        logger.info("Starting UI Overlay...")
        self.update_frame()
        self.root.mainloop()

    def stop(self):
        self.root.quit()
        self.root.destroy()
