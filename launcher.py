import tkinter as tk
import subprocess
import sys

def launch_hands_free():
    root.destroy()
    subprocess.Popen([sys.executable, "main.py", "--mode=standard"])

def launch_blind_mode():
    root.destroy()
    subprocess.Popen([sys.executable, "main.py", "--mode=blind"])

root = tk.Tk()
root.title("Accessibility Suite Launcher")
root.geometry("400x300")
root.configure(bg="#1e1e1e")

# Center the window
root.eval('tk::PlaceWindow . center')

header = tk.Label(root, text="Select Accessibility Mode", font=("Helvetica", 14, "bold"), fg="white", bg="#1e1e1e")
header.pack(pady=30)

btn_hands_free = tk.Button(root, text="1. Standard Hands-Free Controller\n(Head Tracking, Gestures, Dictation)",
                           font=("Helvetica", 11), bg="#3498db", fg="white", activebackground="#2980b9",
                           command=launch_hands_free, height=3, width=35)
btn_hands_free.pack(pady=10)

btn_blind = tk.Button(root, text="2. Blind Accessibility Mode\n(Voice Command Desktop Agent & Screen Reader)",
                      font=("Helvetica", 11), bg="#9b59b6", fg="white", activebackground="#8e44ad",
                      command=launch_blind_mode, height=3, width=35)
btn_blind.pack(pady=10)

root.mainloop()
