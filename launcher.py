import tkinter as tk
import threading
import speech_recognition as sr
from config import Config

def show_launcher():
    """
    Shows a borderless launcher window in the bottom right.
    Returns 'standard' or 'blind' based on user selection or voice command.
    """
    selected_mode = None

    def select_mode(mode):
        nonlocal selected_mode
        selected_mode = mode
        root.quit()

    # Create root but we will only withdraw it or destroy it safely later.
    root = tk.Tk()
    root.title("AccessiBot Launcher")

    width = 340
    height = 200
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # Position at bottom right, above taskbar
    x_position = screen_width - width - 20
    y_position = screen_height - height - 60
    root.geometry(f"{width}x{height}+{x_position}+{y_position}")

    root.configure(bg="#000000")
    root.attributes('-topmost', True)
    root.overrideredirect(True)

    # Header
    header_frame = tk.Frame(root, bg="#111111", height=30)
    header_frame.pack(fill=tk.X)
    tk.Label(header_frame, text="AccessiBot", font=("Helvetica", 12, "bold"), fg="#00FFFF", bg="#111111").pack(side=tk.LEFT, padx=10, pady=5)

    # Content
    content = tk.Frame(root, bg="#000000")
    content.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    lbl_status = tk.Label(content, text="Listening for wake phrase...", font=("Helvetica", 9, "italic"), fg="#888888", bg="#000000")
    lbl_status.pack(pady=(5, 10))

    btn_hands = tk.Button(content, text="Hands-Free Mode\n(Say: 'I can't use my hands')",
                          font=("Helvetica", 10), bg="#222222", fg="#00FF00", activebackground="#333333", activeforeground="#00FF00",
                          command=lambda: select_mode('standard'), bd=1, relief=tk.FLAT)
    btn_hands.pack(fill=tk.X, pady=5)

    btn_blind = tk.Button(content, text="Blind Assist Mode\n(Say: 'I can't see')",
                          font=("Helvetica", 10), bg="#222222", fg="#FF00FF", activebackground="#333333", activeforeground="#FF00FF",
                          command=lambda: select_mode('blind'), bd=1, relief=tk.FLAT)
    btn_blind.pack(fill=tk.X, pady=5)

    # Voice Listener Thread
    def listen_for_mode():
        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = 300

        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
                while selected_mode is None:
                    try:
                        audio = recognizer.listen(source, timeout=1, phrase_time_limit=5)
                        text = recognizer.recognize_google(audio).lower()
                        print(f"Launcher heard: {text}")

                        if "hands" in text or "can't use my hands" in text or "cannot use my hands" in text:
                            lbl_status.config(text="Hands-Free Triggered!", fg="#00FF00")
                            root.after(1000, lambda: select_mode('standard'))
                            break
                        elif "see" in text or "can't see" in text or "cannot see" in text:
                            lbl_status.config(text="Blind Mode Triggered!", fg="#FF00FF")
                            root.after(1000, lambda: select_mode('blind'))
                            break
                    except sr.WaitTimeoutError:
                        continue
                    except sr.UnknownValueError:
                        continue
                    except Exception as e:
                        print(f"Launcher SR error: {e}")
                        continue
        except OSError:
            lbl_status.config(text="Microphone not found. Click to select.", fg="#FF0000")

    listener_thread = threading.Thread(target=listen_for_mode, daemon=True)
    listener_thread.start()

    root.mainloop()

    # Cleanup window resources after mainloop breaks
    # Do NOT destroy root if we intend to open another Tk window later in the same process.
    # Instead, withdraw it so the Tcl interpreter stays alive.
    try:
        root.withdraw()
    except:
        pass

    return selected_mode

if __name__ == '__main__':
    # If the user runs launcher.py directly, we need to bootstrap the main application
    mode = show_launcher()
    print(f"Selected Mode: {mode}")

    if mode:
        import main
        if mode == 'standard':
            main.launch_standard_mode()
        elif mode == 'blind':
            main.launch_blind_mode()
