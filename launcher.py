import tkinter as tk
import threading
import speech_recognition as sr
from config import default_config

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
    height = 220
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # Position at bottom right, above taskbar
    x_position = screen_width - width - 20
    y_position = screen_height - height - 60
    root.geometry(f"{width}x{height}+{x_position}+{y_position}")

    root.configure(bg="#1E1E1E")
    root.attributes('-topmost', True)
    root.overrideredirect(True)

    # Content
    content = tk.Frame(root, bg="#1E1E1E")
    content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

    lbl_title = tk.Label(content, text="Select Mode", font=("Segoe UI", 16, "bold"), fg="#FFFFFF", bg="#1E1E1E")
    lbl_title.pack(pady=(0, 5))

    lbl_status = tk.Label(content, text="Listening for wake phrase...", font=("Segoe UI", 10, "italic"), fg="#AAAAAA", bg="#1E1E1E")
    lbl_status.pack(pady=(0, 15))

    btn_hands = tk.Button(content, text="Hands-Free Mode\n\"I can't use my hands\"",
                          font=("Segoe UI", 11), bg="#333333", fg="#FFFFFF", activebackground="#444444", activeforeground="#FFFFFF",
                          command=lambda: select_mode('standard'), bd=0, relief=tk.FLAT, pady=8)
    btn_hands.pack(fill=tk.X, pady=5)

    btn_blind = tk.Button(content, text="Blind Assist Mode\n\"I can't see\"",
                          font=("Segoe UI", 11), bg="#333333", fg="#FFFFFF", activebackground="#444444", activeforeground="#FFFFFF",
                          command=lambda: select_mode('blind'), bd=0, relief=tk.FLAT, pady=8)
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
