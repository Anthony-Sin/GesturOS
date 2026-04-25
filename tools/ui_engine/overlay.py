import tkinter as tk
import queue
import cv2
from PIL import Image, ImageTk
import collections
import time
from config import Config
from shared_state import state
from tools.audio_engine.player import AudioPlayer

class UIOverlay:
    def __init__(self, data_queue: queue.Queue):
        self.data_queue = data_queue

        # Create a Toplevel window instead of Tk() if a root already exists in this process (e.g. from launcher)
        try:
            self.root = tk.Toplevel()
        except tk.TclError:
            self.root = tk.Tk()

        self.root.title("Hands-Free Controller")

        # Make the window small and place it at the bottom right
        self.window_width = Config.UI_WIDTH
        self.window_height = Config.UI_HEIGHT

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Position at bottom right, leaving some margin for the taskbar
        x_position = screen_width - self.window_width - 20
        y_position = screen_height - self.window_height - 60

        self.root.geometry(f"{self.window_width}x{self.window_height}+{x_position}+{y_position}")

        # Always on top and remove window borders for a sleek look
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)

        # Configure a sleek black background
        self.root.configure(bg='black')

        # Variables for dragging
        self.drag_x = 0
        self.drag_y = 0

        # Create canvas to hold the HUD frame
        self.canvas = tk.Canvas(self.root, width=self.window_width, height=self.window_height, bg='black', highlightthickness=0)
        self.canvas.pack()
        self.image_on_canvas = None

        # Make the entire canvas draggable for a cleaner borderless HUD look
        self.canvas.bind("<ButtonPress-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)

        # Keep track of recent nose positions to draw a path
        self.path_points = collections.deque(maxlen=30)

        # Store blink status for visual feedback
        self.is_blinking = False

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
        # Draw high-tech aesthetic corner brackets
        color = (200, 200, 200)
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
                self.is_blinking = (blink_left > 0.65 and blink_right > 0.65)

                # Resize frame to fit the window
                frame = cv2.resize(frame, (self.window_width, self.window_height))

                # The pipeline provides normalized coordinates.
                # Since we flipped the frame in the pipeline, we must flip the x coordinate for drawing.
                draw_x = int((1.0 - nose_tip['x']) * self.window_width)
                draw_y = int(nose_tip['y'] * self.window_height)

                self.path_points.append((draw_x, draw_y))

                # Extract eye landmarks for visual tracking
                # MediaPipe Landmark 159 is top of right eye, 145 is bottom (user's right, camera left if flipped)
                # MediaPipe Landmark 386 is top of left eye, 374 is bottom
                # We'll use 468 (Left Iris) and 473 (Right Iris) if available, or fallback to center of eye corners.
                # Standard face mesh has left eye center ~ 159/145 area. Let's use 33 (left corner) and 263 (right corner) for simple position.

                if landmarks and len(landmarks) > 263:
                    # User's Left Eye (Right side of flipped camera frame)
                    left_eye_lm = landmarks[33]
                    left_eye_x = int((1.0 - left_eye_lm.x) * self.window_width)
                    left_eye_y = int(left_eye_lm.y * self.window_height)

                    # User's Right Eye (Left side of flipped camera frame)
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
                        color = (int(0 * alpha), int(255 * alpha), int(255 * alpha)) # Cyan tail
                        cv2.line(frame, pts[i-1], pts[i], color, max(1, int(3*alpha)))

                # Draw a high-tech crosshair at the current nose tip instead of a dot
                cross_color = (0, 0, 255) if self.is_blinking else (0, 255, 255)
                cv2.line(frame, (draw_x - 10, draw_y), (draw_x + 10, draw_y), cross_color, 1)
                cv2.line(frame, (draw_x, draw_y - 10), (draw_x, draw_y + 10), cross_color, 1)
                cv2.circle(frame, (draw_x, draw_y), 4, cross_color, 1)

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

                # Make the frame slightly darker/sleeker
                frame = cv2.convertScaleAbs(frame, alpha=0.8, beta=10)
                self._draw_hud_corners(frame)

                # Modern aesthetic text and elements
                font = cv2.FONT_HERSHEY_SIMPLEX
                cv2.putText(frame, f"L-EYE: {left_status}", (20, 30), font, 0.4, (0, 255, 0) if left_status=="OPEN" else (0, 0, 255), 1)
                cv2.putText(frame, f"R-EYE: {right_status}", (20, 50), font, 0.4, (0, 255, 0) if right_status=="OPEN" else (0, 0, 255), 1)

                if self.is_blinking:
                    cv2.putText(frame, "LEFT CLICK", (180, 40), cv2.FONT_HERSHEY_DUPLEX, 0.5, (0, 0, 255), 1)

                # FPS Calculation and Render
                if len(self.fps_queue) > 1:
                    time_diff = self.fps_queue[-1] - self.fps_queue[0]
                    if time_diff > 0:
                        fps = len(self.fps_queue) / time_diff
                        cv2.putText(frame, f"FPS: {fps:.1f}", (self.window_width - 80, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

                # Voice Transcriber Status
                voice_status = state.get("voice_status", "")
                if voice_status:
                    color = (0, 255, 255) if "DICTATING" in voice_status else (200, 200, 200)
                    cv2.putText(frame, voice_status, (20, self.window_height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

                # Draw Drag-Lock Status & Progress
                is_locked = payload.get('is_locked', False)
                lock_progress = payload.get('lock_progress', 0.0)

                if is_locked:
                    cv2.putText(frame, "[ DRAGGING MODE ACTIVE ]", (50, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 100), 1)
                elif lock_progress > 0.0:
                    # Play subtle tick sounds as progress increases
                    now = self.time_module.time()
                    if lock_progress > 0.1 and now - self.last_tick_time > 0.4:
                        AudioPlayer().play('lock_progress')
                        self.last_tick_time = now

                    # Draw a loading bar for lock progress
                    bar_w = 100
                    bar_h = 10
                    start_x = self.window_width // 2 - bar_w // 2
                    start_y = self.window_height - 30

                    # Background
                    cv2.rectangle(frame, (start_x, start_y), (start_x + bar_w, start_y + bar_h), (50, 50, 50), -1)
                    # Foreground
                    cv2.rectangle(frame, (start_x, start_y), (start_x + int(bar_w * lock_progress), start_y + bar_h), (0, 255, 255), -1)
                    # Border
                    cv2.rectangle(frame, (start_x, start_y), (start_x + bar_w, start_y + bar_h), (200, 200, 200), 1)

                    font = cv2.FONT_HERSHEY_SIMPLEX
                    cv2.putText(frame, "HOLD STILL TO DRAG", (start_x - 10, start_y - 5), font, 0.35, (200, 200, 200), 1)

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
