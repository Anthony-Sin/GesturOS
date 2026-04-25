import tkinter as tk
import queue
import cv2
from PIL import Image, ImageTk
import collections

class UIOverlay:
    def __init__(self, data_queue: queue.Queue):
        self.data_queue = data_queue

        self.root = tk.Tk()
        self.root.title("Hands-Free Controller")

        # Make the window small and place it at the bottom right
        self.window_width = 320
        self.window_height = 240

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

        # Create a header frame for dragging the borderless window
        self.header = tk.Frame(self.root, bg='#222222', height=24)
        self.header.pack(fill=tk.X)
        self.header_label = tk.Label(self.header, text="Hands-Free Controller", fg='white', bg='#222222', font=("Helvetica", 10, "bold"))
        self.header_label.pack(side=tk.LEFT, padx=10)

        # Variables for dragging
        self.drag_x = 0
        self.drag_y = 0
        self.header.bind("<ButtonPress-1>", self.start_move)
        self.header.bind("<B1-Motion>", self.do_move)
        self.header_label.bind("<ButtonPress-1>", self.start_move)
        self.header_label.bind("<B1-Motion>", self.do_move)

        self.canvas = tk.Canvas(self.root, width=self.window_width, height=self.window_height, bg='black', highlightthickness=0)
        self.canvas.pack()
        self.image_on_canvas = None

        # Keep track of recent nose positions to draw a path
        self.path_points = collections.deque(maxlen=30)

        # Store blink status for visual feedback
        self.is_blinking = False

    def start_move(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def do_move(self, event):
        x = self.root.winfo_x() - self.drag_x + event.x
        y = self.root.winfo_y() - self.drag_y + event.y
        self.root.geometry(f"+{x}+{y}")

    def update_frame(self):
        try:
            # Drain the queue to get the latest frame
            payload = None
            while not self.data_queue.empty():
                payload = self.data_queue.get_nowait()

            if payload is not None:
                frame = payload['frame']
                nose_tip = payload['nose_tip']
                blendshapes = payload['blendshapes']

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

                # Draw the path on the frame
                if len(self.path_points) > 1:
                    pts = list(self.path_points)
                    for i in range(1, len(pts)):
                        cv2.line(frame, pts[i-1], pts[i], (0, 255, 0), 2)

                # Draw a dot at the current nose tip
                color = (0, 0, 255) if self.is_blinking else (255, 0, 0)
                cv2.circle(frame, (draw_x, draw_y), 5, color, -1)

                # Make the frame slightly darker/sleeker
                frame = cv2.convertScaleAbs(frame, alpha=0.8, beta=10)

                # Modern aesthetic text and elements
                if self.is_blinking:
                    cv2.putText(frame, "CLICK", (20, 40), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 200, 255), 2)

                # Draw Drag-Lock Status
                is_locked = payload.get('is_locked', False)
                if is_locked:
                    cv2.putText(frame, "DRAGGING", (20, 80), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 255, 100), 2)

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
