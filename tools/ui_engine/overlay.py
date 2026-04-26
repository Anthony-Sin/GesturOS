import tkinter as tk
import queue
import cv2
from PIL import Image, ImageTk
import collections
import time
import math
from tools.interfaces import BaseUIEngine


class UIOverlay(BaseUIEngine):
    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict, audio_player):
        self.data_queue = data_queue
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player

        # Create a Toplevel window instead of Tk() if a root already exists in this process (e.g. from launcher)
        try:
            self.root = tk.Toplevel()
        except tk.TclError:
            self.root = tk.Tk()

        self.root.title("Hands-Free Controller")

        # Make the window small and place it at the bottom right
        self.window_width = self.config.get("UI_WIDTH", 320)
        self.window_height = self.config.get("UI_HEIGHT", 240)

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Position at bottom right, leaving some margin for the taskbar
        x_position = screen_width - self.window_width - 20
        y_position = screen_height - self.window_height - 60

        self.root.geometry(f"{self.window_width}x{self.window_height}+{x_position}+{y_position}")

        # Always on top and remove window borders for a sleek look
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)

        # Translucency for the "glass" look
        self.root.attributes('-alpha', 0.9)

        # Configure a sleek black background
        self.root.configure(bg='black')

        # Variables for dragging
        self.drag_x = 0
        self.drag_y = 0

        # Create canvas to hold the HUD frame
        self.canvas = tk.Canvas(self.root, width=self.window_width,
                                height=self.window_height, bg='black', highlightthickness=0)
        self.canvas.pack()
        self.image_on_canvas = None

        # Make the entire canvas draggable for a cleaner borderless HUD look
        self.canvas.bind("<ButtonPress-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)

        # Keep track of recent nose positions to draw a path
        self.path_points = collections.deque(maxlen=30)

        # Store blink status for visual feedback
        self.is_blinking = False

        # Pulse animation variables
        self.pulse_phase = 0.0
        self.last_nose_pos = None
        self.cursor_speed = 0.0

        # Status banner variables
        self.banner_message = ""
        self.banner_start_time = 0.0

        # State tracking for triggers
        self.last_voice_status = ""
        self.last_mode = ""

        # FPS Tracking
        self.fps_queue = collections.deque(maxlen=30)
        self.time_module = time

        self.last_tick_time = 0

    def start_move(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def do_move(self, event):
        x = self.root.winfo_x() - self.drag_x + event.x
        y = self.root.winfo_y() - self.drag_y + event.y
        self.root.geometry(f"+{x}+{y}")

    def _draw_hud_corners(self, frame):
        # Draw high-tech aesthetic corner brackets (Neon Cyan)
        color = (255, 255, 0)  # Cyan in BGR
        thickness = 2
        length = 20
        h, w = frame.shape[:2]

        # Top-left
        cv2.line(frame, (10, 10), (10 + length, 10), color, thickness)
        cv2.line(frame, (10, 10), (10, 10 + length), color, thickness)
        # Top-right
        cv2.line(frame, (w - 10, 10), (w - 10 - length, 10), color, thickness)
        cv2.line(frame, (w - 10, 10), (w - 10, 10 + length), color, thickness)
        # Bottom-left
        cv2.line(frame, (10, h - 10), (10 + length, h - 10), color, thickness)
        cv2.line(frame, (10, h - 10), (10, h - 10 - length), color, thickness)
        # Bottom-right
        cv2.line(frame, (w - 10, h - 10), (w - 10 - length, h - 10), color, thickness)
        cv2.line(frame, (w - 10, h - 10), (w - 10, h - 10 - length), color, thickness)

        # Subtle Inner Brackets (Neon Green)
        color_inner = (0, 255, 0)
        inner_offset = 15
        inner_length = 10
        inner_thickness = 1

        # Top-left
        cv2.line(frame, (10+inner_offset, 10+inner_offset), (10+inner_offset +
                 inner_length, 10+inner_offset), color_inner, inner_thickness)
        cv2.line(frame, (10+inner_offset, 10+inner_offset), (10+inner_offset,
                 10+inner_offset + inner_length), color_inner, inner_thickness)
        # Top-right
        cv2.line(frame, (w - 10 - inner_offset, 10+inner_offset), (w - 10 - inner_offset -
                 inner_length, 10+inner_offset), color_inner, inner_thickness)
        cv2.line(frame, (w - 10 - inner_offset, 10+inner_offset), (w - 10 - inner_offset,
                 10+inner_offset + inner_length), color_inner, inner_thickness)
        # Bottom-left
        cv2.line(frame, (10+inner_offset, h - 10 - inner_offset), (10+inner_offset +
                 inner_length, h - 10 - inner_offset), color_inner, inner_thickness)
        cv2.line(frame, (10+inner_offset, h - 10 - inner_offset), (10+inner_offset,
                 h - 10 - inner_offset - inner_length), color_inner, inner_thickness)
        # Bottom-right
        cv2.line(frame, (w - 10 - inner_offset, h - 10 - inner_offset), (w - 10 - inner_offset -
                 inner_length, h - 10 - inner_offset), color_inner, inner_thickness)
        cv2.line(frame, (w - 10 - inner_offset, h - 10 - inner_offset), (w - 10 - inner_offset,
                 h - 10 - inner_offset - inner_length), color_inner, inner_thickness)

    def _draw_icon(self, frame, x, y, icon_type, color=(0, 255, 0)):
        # Draw simple geometric icons
        if icon_type == "eye":
            # Stylized eye
            cv2.ellipse(frame, (x, y), (8, 5), 0, 0, 360, color, 1)
            cv2.circle(frame, (x, y), 2, color, -1)
        elif icon_type == "mic":
            # Stylized microphone
            cv2.rectangle(frame, (x-3, y-6), (x+3, y+2), color, 1)
            cv2.circle(frame, (x, y-6), 3, color, 1)  # top curve
            cv2.ellipse(frame, (x, y+2), (5, 4), 0, 0, 180, color, 1)  # bottom cup
            cv2.line(frame, (x, y+6), (x, y+9), color, 1)  # stand
            cv2.line(frame, (x-4, y+9), (x+4, y+9), color, 1)  # base
        elif icon_type == "track":
            # Stylized crosshair/target
            cv2.circle(frame, (x, y), 6, color, 1)
            cv2.line(frame, (x-8, y), (x-3, y), color, 1)
            cv2.line(frame, (x+3, y), (x+8, y), color, 1)
            cv2.line(frame, (x, y-8), (x, y-3), color, 1)
            cv2.line(frame, (x, y+3), (x, y+8), color, 1)
            cv2.circle(frame, (x, y), 1, color, -1)

    def trigger_banner(self, message):
        self.banner_message = message
        self.banner_start_time = self.time_module.time()

    def update_frame(self):
        try:
            current_time = self.time_module.time()
            self.fps_queue.append(current_time)

            # Drain the queue to get the latest frame
            payload = None
            while not self.data_queue.empty():
                payload = self.data_queue.get_nowait()

            if payload is not None:
                frame = payload['frame']
                nose_tip = payload['nose_tip']
                blendshapes = payload['blendshapes']
                landmarks = payload.get('landmarks', [])

                # Check for full blink for visual feedback
                blink_left = blendshapes.get('eyeBlinkLeft', 0.0)
                blink_right = blendshapes.get('eyeBlinkRight', 0.0)
                was_blinking = self.is_blinking
                self.is_blinking = (blink_left > 0.65 and blink_right > 0.65)

                if self.is_blinking and not was_blinking:
                    self.trigger_banner("[*] Clicked")

                # Resize frame to fit the window
                frame = cv2.resize(frame, (self.window_width, self.window_height))

                # Make the frame darker/sleeker for neon aesthetic
                frame = cv2.convertScaleAbs(frame, alpha=0.5, beta=-20)

                # The pipeline provides normalized coordinates.
                draw_x = int((1.0 - nose_tip['x']) * self.window_width)
                draw_y = int(nose_tip['y'] * self.window_height)

                # Calculate cursor speed for animated ring
                if self.last_nose_pos:
                    dx = draw_x - self.last_nose_pos[0]
                    dy = draw_y - self.last_nose_pos[1]
                    speed = (dx**2 + dy**2)**0.5
                    # Smooth speed
                    self.cursor_speed = self.cursor_speed * 0.8 + speed * 0.2
                self.last_nose_pos = (draw_x, draw_y)

                self.path_points.append((draw_x, draw_y))

                # Extract eye landmarks
                if landmarks and len(landmarks) > 263:
                    left_eye_lm = landmarks[33]
                    left_eye_x = int((1.0 - left_eye_lm.x) * self.window_width)
                    left_eye_y = int(left_eye_lm.y * self.window_height)

                    right_eye_lm = landmarks[263]
                    right_eye_x = int((1.0 - right_eye_lm.x) * self.window_width)
                    right_eye_y = int(right_eye_lm.y * self.window_height)
                else:
                    left_eye_x, left_eye_y = -1, -1
                    right_eye_x, right_eye_y = -1, -1

                # Draw the path on the frame (Sleeker trailing effect)
                if len(self.path_points) > 1:
                    pts = list(self.path_points)
                    for i in range(1, len(pts)):
                        # Fade out the tail
                        alpha = i / len(pts)
                        color = (int(0 * alpha), int(255 * alpha), int(255 * alpha))  # Cyan tail
                        cv2.line(frame, pts[i-1], pts[i], color, max(1, int(2*alpha)))

                # Draw Animated Pulsing Ring around crosshair
                # Speed determines pulse rate and color
                if self.cursor_speed > 3.0:
                    # Fast pulse, Cyan
                    self.pulse_phase += 0.3
                    ring_color = (255, 255, 0)
                else:
                    # Slow pulse, Green
                    self.pulse_phase += 0.05
                    ring_color = (0, 255, 0)

                ring_radius = 12 + int(4 * math.sin(self.pulse_phase))
                cv2.circle(frame, (draw_x, draw_y), ring_radius, ring_color, 1)

                # Draw a high-tech crosshair
                cross_color = (0, 0, 255) if self.is_blinking else (0, 255, 255)
                cv2.line(frame, (draw_x - 6, draw_y), (draw_x + 6, draw_y), cross_color, 1)
                cv2.line(frame, (draw_x, draw_y - 6), (draw_x, draw_y + 6), cross_color, 1)
                cv2.circle(frame, (draw_x, draw_y), 2, cross_color, -1)

                # Draw HUD Corners
                self._draw_hud_corners(frame)

                # Eye Tracking Status Text & Colors
                # The prompt requested Right Click when *both* eyes close, which we implemented.
                # Here we just track individual status for the UI.
                left_closed = blink_left > 0.45
                right_closed = blink_right > 0.45

                left_status = "CLOSED" if left_closed else "OPEN"
                right_status = "CLOSED" if right_closed else "OPEN"

                # Draw Visual Eye Tracking Overlays
                if left_eye_x != -1 and left_eye_y != -1:
                    l_color = (0, 0, 255) if left_closed else (0, 255, 0)
                    cv2.circle(frame, (left_eye_x, left_eye_y), 6, l_color, 2)

                if right_eye_x != -1 and right_eye_y != -1:
                    r_color = (0, 0, 255) if right_closed else (0, 255, 0)
                    cv2.circle(frame, (right_eye_x, right_eye_y), 6, r_color, 2)

                # Modern aesthetic text and elements
                font = cv2.FONT_HERSHEY_SIMPLEX
                cv2.putText(frame, f"L-EYE: {left_status}", (20, 50), font, 0.35,
                            (0, 255, 0) if left_status == "OPEN" else (0, 0, 255), 1)
                cv2.putText(frame, f"R-EYE: {right_status}", (20, 70), font, 0.35,
                            (0, 255, 0) if right_status == "OPEN" else (0, 0, 255), 1)

                # Active States
                # Determine state
                voice_status = self.shared_state.get("voice_status", "")
                mode = self.config.get("MODE", "hands_free")

                # Check for state changes to trigger banner
                if "DICTATING" in voice_status and "DICTATING" not in self.last_voice_status:
                    self.trigger_banner("[mic] Dictating...")
                elif "DICTATING" not in voice_status and "DICTATING" in self.last_voice_status:
                    self.trigger_banner("[mic] Dictation Ended")
                self.last_voice_status = voice_status

                if mode == "blind" and self.last_mode != "blind":
                    self.trigger_banner("[eye] Blind Mode Active")
                elif mode == "hands_free" and self.last_mode != "hands_free" and self.last_mode != "":
                    self.trigger_banner("[track] Tracking Active")
                self.last_mode = mode

                if "DICTATING" in voice_status:
                    self._draw_icon(frame, 20, 20, "mic", (0, 255, 255))
                    cv2.putText(frame, "DICTATING", (30, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
                elif mode == "blind":
                    self._draw_icon(frame, 20, 20, "eye", (0, 255, 0))
                    cv2.putText(frame, "BLIND MODE", (30, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
                else:
                    self._draw_icon(frame, 20, 20, "track", (0, 255, 0))
                    cv2.putText(frame, "TRACKING", (30, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)

                # FPS Calculation and Render (Small, bottom right)
                if len(self.fps_queue) > 1:
                    time_diff = self.fps_queue[-1] - self.fps_queue[0]
                    if time_diff > 0:
                        fps = len(self.fps_queue) / time_diff
                        cv2.putText(frame, f"{fps:.0f} FPS", (self.window_width - 45,
                                    self.window_height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (100, 100, 100), 1)

                # Draw Drag-Lock Status & Progress
                is_locked = payload.get('is_locked', False)
                lock_progress = payload.get('lock_progress', 0.0)

                if is_locked:
                    cv2.putText(frame, "[ DRAGGING ]", (self.window_width//2 - 40, 45),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 100), 1)
                elif lock_progress > 0.0:
                    now = self.time_module.time()
                    if lock_progress > 0.1 and now - self.last_tick_time > 0.4:
                        from tools.audio_engine.player import AudioPlayer
                        AudioPlayer().play('lock_progress')
                        self.last_tick_time = now

                    # Draw a loading bar for lock progress
                    bar_w = 60
                    bar_h = 4
                    start_x = self.window_width // 2 - bar_w // 2
                    start_y = 40

                    # Background
                    cv2.rectangle(frame, (start_x, start_y), (start_x + bar_w, start_y + bar_h), (50, 50, 50), -1)
                    # Foreground
                    cv2.rectangle(frame, (start_x, start_y), (start_x + int(bar_w *
                                  lock_progress), start_y + bar_h), (0, 255, 0), -1)

                # Status Banner (Slide up and fade out)
                if self.banner_message:
                    elapsed = current_time - self.banner_start_time
                    banner_duration = 2.0
                    slide_duration = 0.3

                    if elapsed < banner_duration:
                        # Calculate y position (slide up from bottom)
                        if elapsed < slide_duration:
                            # Sliding up
                            progress = elapsed / slide_duration
                            banner_y = self.window_height - int(30 * progress)
                        else:
                            banner_y = self.window_height - 30

                        # Calculate opacity (fade out in last 0.5s)
                        fade_start = banner_duration - 0.5
                        if elapsed > fade_start:
                            alpha = 1.0 - (elapsed - fade_start) / 0.5
                        else:
                            alpha = 1.0

                        # Draw banner background
                        overlay = frame.copy()
                        cv2.rectangle(overlay, (0, banner_y), (self.window_width, self.window_height), (20, 20, 20), -1)
                        # Top border
                        cv2.line(overlay, (0, banner_y), (self.window_width, banner_y), (0, 255, 0), 1)

                        # Apply semi-transparent overlay
                        cv2.addWeighted(overlay, alpha * 0.8, frame, 1.0 - (alpha * 0.8), 0, frame)

                        # Draw text
                        text_size = cv2.getTextSize(self.banner_message, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0]
                        text_x = (self.window_width - text_size[0]) // 2
                        text_y = banner_y + 18

                        # Draw with opacity approximation (by merging)
                        if alpha == 1.0:
                            cv2.putText(frame, self.banner_message, (text_x, text_y),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                        else:
                            text_overlay = frame.copy()
                            cv2.putText(text_overlay, self.banner_message, (text_x, text_y),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                            cv2.addWeighted(text_overlay, alpha, frame, 1.0 - alpha, 0, frame)
                    else:
                        self.banner_message = ""

                # Convert frame to PhotoImage
                # Convert BGR to RGB for PIL
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                imgtk = ImageTk.PhotoImage(image=img)

                if self.image_on_canvas is None:
                    self.image_on_canvas = self.canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
                else:
                    self.canvas.itemconfig(self.image_on_canvas, image=imgtk)

                # Keep a reference to prevent garbage collection
                self.canvas.image = imgtk

        except queue.Empty:
            pass
        except Exception as e:
            print(f"UI Error: {e}")

        # Schedule the next update (e.g. 30ms ~ 33fps)
        self.root.after(30, self.update_frame)

    def start(self):
        print("Starting UI Overlay...")
        self.update_frame()
        self.root.mainloop()

    def stop(self):
        # Cleanly destroy the Tkinter window
        self.root.quit()
        self.root.destroy()
