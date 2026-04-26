import tkinter as tk
import queue
import cv2
from PIL import Image, ImageTk, ImageDraw
import collections
import time
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

        # Configuration & Styling
        self.cam_width = 240
        self.cam_height = 180
        self.sidebar_expanded_width = 200
        self.sidebar_collapsed_width = 30

        self.is_sidebar_expanded = False

        self.bg_color = "#1E1E1E"
        self.accent_color = "#8A2BE2" # Clean minimal purple
        self.text_color = "#FFFFFF"
        self.muted_color = "#888888"

        # Position at bottom right
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        self._update_geometry()

        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)
        self.root.configure(bg=self.bg_color)

        # Main Layout Frame
        self.main_frame = tk.Frame(self.root, bg=self.bg_color)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Sidebar Frame
        self.sidebar_frame = tk.Frame(self.main_frame, bg="#151515", width=self.sidebar_collapsed_width)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)

        # Sidebar Toggle Button
        self.toggle_btn = tk.Button(self.sidebar_frame, text="▶", bg="#151515", fg=self.muted_color,
                                    bd=0, activebackground="#1E1E1E", activeforeground=self.text_color,
                                    command=self._toggle_sidebar, font=("Arial", 10))
        self.toggle_btn.pack(side=tk.TOP, pady=5, anchor="w", padx=5)

        # Sidebar Content (hidden initially)
        self.sidebar_content = tk.Frame(self.sidebar_frame, bg="#151515")
        tk.Label(self.sidebar_content, text="Voice & Face Controls", bg="#151515", fg=self.accent_color, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 5))

        instructions = [
            "👁 Blink — Left Click",
            "🎙 Say 'transcribe me' — Dictation",
            "⌨️ Say 'press [key]' — Keyboard",
            "🤖 Say 'Agent [task]' — AI takes over"
        ]

        for inst in instructions:
            tk.Label(self.sidebar_content, text=inst, bg="#151515", fg=self.text_color, font=("Segoe UI", 9)).pack(anchor="w", pady=2)

        # Camera Frame
        self.cam_frame = tk.Frame(self.main_frame, bg=self.bg_color, width=self.cam_width, height=self.cam_height)
        self.cam_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.canvas = tk.Canvas(self.cam_frame, width=self.cam_width, height=self.cam_height, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack()

        self.image_on_canvas = None

        # State tracking for UI
        self.fps_queue = collections.deque(maxlen=30)
        self.banner_message = ""
        self.banner_start_time = 0
        self.last_voice_status = ""

    def _update_geometry(self):
        w = self.cam_width + (self.sidebar_expanded_width if self.is_sidebar_expanded else self.sidebar_collapsed_width) + 8
        h = self.cam_height + 8
        x = self.screen_width - w - 20
        y = self.screen_height - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _toggle_sidebar(self):
        self.is_sidebar_expanded = not self.is_sidebar_expanded

        if self.is_sidebar_expanded:
            self.sidebar_frame.config(width=self.sidebar_expanded_width)
            self.toggle_btn.config(text="◀")
            self.sidebar_content.pack(fill=tk.BOTH, expand=True, padx=10)
        else:
            self.sidebar_content.pack_forget()
            self.sidebar_frame.config(width=self.sidebar_collapsed_width)
            self.toggle_btn.config(text="▶")

        self._update_geometry()

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

                    # Draw a subtle border inside the rounded image
                    border_draw = ImageDraw.Draw(rounded_img)
                    border_draw.rounded_rectangle((0, 0, img.size[0]-1, img.size[1]-1), radius=radius, outline=self.muted_color, width=1)

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

        # Crosshair, Nose, and Eye State Dots
        nose_tip = payload.get('nose_tip')
        if nose_tip:
            nx = int(nose_tip['x'] * self.cam_width)
            ny = int(nose_tip['y'] * self.cam_height)

            # Simple, precise, professional crosshair
            color = (138, 43, 226) # Purple Accent (RGB)
            cv2.line(frame, (nx - 4, ny), (nx + 4, ny), color, 1)
            cv2.line(frame, (nx, ny - 4), (nx, ny + 4), color, 1)
            cv2.circle(frame, (nx, ny), 1, (255, 255, 255), -1)

            # Eye State Dots near crosshair
            blendshapes = payload.get('blendshapes', {})
            blink_left = blendshapes.get('eyeBlinkLeft', 0.0)
            blink_right = blendshapes.get('eyeBlinkRight', 0.0)

            threshold = self.config.get("BLINK_THRESHOLD", 0.26)
            l_closed = blink_left > threshold
            r_closed = blink_right > threshold

            dot_color_open = (200, 200, 200)
            dot_color_closed = (138, 43, 226) # Purple

            # Draw dots slightly below and to the side of the crosshair
            cv2.circle(frame, (nx - 8, ny + 12), 3, dot_color_closed if l_closed else dot_color_open, -1 if l_closed else 1)
            cv2.circle(frame, (nx + 8, ny + 12), 3, dot_color_closed if r_closed else dot_color_open, -1 if r_closed else 1)

        # FPS counter
        if len(self.fps_queue) > 1:
            time_diff = self.fps_queue[-1] - self.fps_queue[0]
            if time_diff > 0:
                fps = len(self.fps_queue) / time_diff
                cv2.putText(frame, f"{fps:.0f} FPS", (self.cam_width - 45, self.cam_height - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (150, 150, 150), 1)

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
