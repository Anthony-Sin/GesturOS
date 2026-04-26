import tkinter as tk
import queue
import cv2
from PIL import Image, ImageTk, ImageDraw
import collections
import time
import numpy as np
from tools.interfaces import BaseUIEngine

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

        self.root.title("AccessiBot UI")

        # Configuration & Styling (Cyberpunk aesthetic as requested)
        # Using a fixed size as requested that looks proportional (e.g. 300 width)
        self.window_width = 300
        # The height is determined dynamically by the components to match the layout
        self.cam_width = 280
        self.cam_height = 210

        self.bg_color = "#000000"
        self.border_color = "#FFFF00" # Yellow outline
        self.text_color = "#00FFFF" # Cyan text
        self.accent_color = "#FF004D" # Red accent
        self.yellow_text = "#FFFF00"

        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)
        self.root.configure(bg=self.bg_color)

        # Main Layout Frame with Thick Yellow Border
        self.main_frame = tk.Frame(self.root, bg=self.bg_color, highlightbackground=self.border_color, highlightthickness=3)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Top Section: Currently Doing ---
        self.top_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        self.top_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.lbl_currently_doing = tk.Label(self.top_frame, text="C U R R E N T L Y _ D O I N G", bg=self.bg_color, fg=self.text_color, font=("Courier", 10, "bold"))
        self.lbl_currently_doing.pack(side=tk.LEFT)

        # Yellow separator line
        tk.Frame(self.main_frame, bg=self.border_color, height=1).pack(fill=tk.X, padx=5, pady=5)

        # --- Middle Section: Abilities / Info Squares ---
        self.info_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        self.info_frame.pack(fill=tk.X, padx=10, pady=5)

        def create_info_row(parent, text):
            row = tk.Frame(parent, bg=self.bg_color)
            row.pack(fill=tk.X, pady=2)
            # Red square
            canvas = tk.Canvas(row, width=10, height=10, bg=self.bg_color, highlightthickness=0)
            canvas.pack(side=tk.LEFT, padx=(0, 5))
            canvas.create_rectangle(2, 2, 8, 8, fill=self.accent_color, outline="")
            # Yellow text
            tk.Label(row, text=text, bg=self.bg_color, fg=self.yellow_text, font=("Courier", 9, "italic", "bold")).pack(side=tk.LEFT)

        create_info_row(self.info_frame, "PREDICTIVE MAGNETISM: SNAP")
        create_info_row(self.info_frame, "ELEVENLABS: TTS READY")
        create_info_row(self.info_frame, "AUTONOMOUS AI: ACTIVE")

        # Yellow separator line
        tk.Frame(self.main_frame, bg=self.border_color, height=1).pack(fill=tk.X, padx=5, pady=5)

        # --- Bottom Section: Webcam Feed ---
        self.cam_frame = tk.Frame(self.main_frame, bg=self.bg_color, width=self.cam_width, height=self.cam_height)
        self.cam_frame.pack(pady=(0, 10), padx=10)

        self.canvas = tk.Canvas(self.cam_frame, width=self.cam_width, height=self.cam_height, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack()

        self.image_on_canvas = None

        # State tracking for UI
        self.fps_queue = collections.deque(maxlen=30)
        self.banner_message = ""
        self.banner_start_time = 0
        self.last_voice_status = ""

        # Update geometry and position after components are built
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = self.screen_width - w - 20
        y = self.screen_height - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def trigger_banner(self, message):
        self.banner_message = message
        self.banner_start_time = time.time()

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

            if payload:
                frame = payload.get('frame')
                if frame is not None:
                    # Update label
                    doing = self.shared_state.get("currently_doing", "AWAITING COMMAND")
                    self.lbl_currently_doing.config(text=f"{doing}")

                    # Resize frame to fit canvas
                    frame = cv2.resize(frame, (self.cam_width, self.cam_height))

                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    # Draw UI Elements via OpenCV
                    self._draw_overlays(frame_rgb, payload)

                    # Apply rounded corners using PIL mask
                    img = Image.fromarray(frame_rgb)

                    # Create rounded mask
                    mask = Image.new('L', img.size, 0)
                    draw = ImageDraw.Draw(mask)
                    radius = 12
                    draw.rounded_rectangle((0, 0, img.size[0], img.size[1]), radius=radius, fill=255)

                    # Apply mask and background
                    rounded_img = Image.new('RGBA', img.size, self.bg_color)
                    rounded_img.paste(img, (0, 0), mask=mask)

                    # Draw yellow border with rounded corners
                    border_draw = ImageDraw.Draw(rounded_img)
                    border_draw.rounded_rectangle((0, 0, img.size[0]-1, img.size[1]-1), radius=radius, outline=self.border_color, width=2)

                    imgtk = ImageTk.PhotoImage(image=rounded_img)

                    if self.image_on_canvas is None:
                        self.image_on_canvas = self.canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
                    else:
                        self.canvas.itemconfig(self.image_on_canvas, image=imgtk)

                    self.canvas.image = imgtk

        except Exception as e:
            print(f"UI Error: {e}")

        self.root.after(30, self.update_frame)

    def _draw_overlays(self, frame, payload):
        current_time = time.time()

        # Draw Yellow Corner Brackets
        c_len = 20
        c_thick = 2
        pad = 10
        # Top Left
        cv2.line(frame, (pad, pad), (pad + c_len, pad), (255, 255, 0), c_thick)
        cv2.line(frame, (pad, pad), (pad, pad + c_len), (255, 255, 0), c_thick)
        # Top Right
        cv2.line(frame, (self.cam_width - pad, pad), (self.cam_width - pad - c_len, pad), (255, 255, 0), c_thick)
        cv2.line(frame, (self.cam_width - pad, pad), (self.cam_width - pad, pad + c_len), (255, 255, 0), c_thick)
        # Bottom Left
        cv2.line(frame, (pad, self.cam_height - pad), (pad + c_len, self.cam_height - pad), (255, 255, 0), c_thick)
        cv2.line(frame, (pad, self.cam_height - pad), (pad, self.cam_height - pad - c_len), (255, 255, 0), c_thick)
        # Bottom Right
        cv2.line(frame, (self.cam_width - pad, self.cam_height - pad), (self.cam_width - pad - c_len, self.cam_height - pad), (255, 255, 0), c_thick)
        cv2.line(frame, (self.cam_width - pad, self.cam_height - pad), (self.cam_width - pad, self.cam_height - pad - c_len), (255, 255, 0), c_thick)

        # Crosshair, Nose
        nose_tip = payload.get('nose_tip')
        if nose_tip:
            nx = int(nose_tip['x'] * self.cam_width)
            ny = int(nose_tip['y'] * self.cam_height)

            # High-tech crosshair (cyan rings with red diamond center)
            color_ring = (0, 255, 255) # Cyan in RGB
            color_center = (255, 0, 77) # Red Accent

            # Draw Rings
            cv2.circle(frame, (nx, ny), 15, color_ring, 1)
            cv2.circle(frame, (nx, ny), 8, color_ring, 2)

            # Draw Red Diamond
            pts = np.array([[nx, ny - 4], [nx + 4, ny], [nx, ny + 4], [nx - 4, ny]], np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.fillPoly(frame, [pts], color_center)

        # Voice Status Monitoring
        voice_status = self.shared_state.get("voice_status", "")
        if voice_status != self.last_voice_status and voice_status:
            self.trigger_banner(voice_status)
        self.last_voice_status = voice_status

        # Banner Sliding Logic
        if self.banner_message:
            elapsed = current_time - self.banner_start_time
            banner_duration = 2.0
            slide_duration = 0.2
            banner_h = 24

            if elapsed < banner_duration:
                # Slide up y calculation
                if elapsed < slide_duration:
                    progress = elapsed / slide_duration
                    banner_y = self.cam_height - int(banner_h * progress)
                else:
                    banner_y = self.cam_height - banner_h

                # Alpha calculation for fading out
                fade_start = banner_duration - 0.5
                if elapsed > fade_start:
                    alpha = max(0.0, 1.0 - (elapsed - fade_start) / 0.5)
                else:
                    alpha = 1.0

                # Draw banner background on a copy to blend
                overlay = frame.copy()
                cv2.rectangle(overlay, (0, banner_y), (self.cam_width, self.cam_height), (30, 30, 30), -1)

                # Top accent line
                cv2.line(overlay, (0, banner_y), (self.cam_width, banner_y), (138, 43, 226), 1)

                # Blend the banner background
                cv2.addWeighted(overlay, alpha * 0.9, frame, 1.0 - (alpha * 0.9), 0, frame)

                # Draw text
                text_size = cv2.getTextSize(self.banner_message, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)[0]
                text_x = (self.cam_width - text_size[0]) // 2
                text_y = banner_y + 16

                # Hacky text opacity: If alpha < 1, blend a text overlay
                if alpha == 1.0:
                    cv2.putText(frame, self.banner_message, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
                else:
                    text_overlay = frame.copy()
                    cv2.putText(text_overlay, self.banner_message, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
                    cv2.addWeighted(text_overlay, alpha, frame, 1.0 - alpha, 0, frame)
            else:
                self.banner_message = ""

    def start(self):
        print("Starting UI Overlay...")
        self.update_frame()
        self.root.mainloop()

    def stop(self):
        self.root.quit()
        self.root.destroy()
