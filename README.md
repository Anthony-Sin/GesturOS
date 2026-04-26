AccessiBot: Hands-Free Controller & Blind Assistant
A local Python application that acts as a comprehensive accessibility suite. It translates natural head movements and facial expressions—captured via a webcam using MediaPipe—into precise OS-level mouse and keyboard actions. It also features a fully voice-activated AI Agent designed for blind users, powered by Gemini 2.5's Computer Use capabilities.

Core Features
Voice-Activated Launcher: Say "I can't use my hands" to boot into Standard Head-Tracking mode, or say "I can't see" to boot into the Gemini Blind Assist mode.
Cursor Engine: Moves your mouse cursor based on the position of your nose. Uses a dynamic 1 Euro Filter to eliminate jitter at slow speeds while remaining lag-free at high speeds. Includes an asymmetrical "Active Zone" multiplier to minimize physical neck strain, and a Micro-Deadzone for pixel-perfect clicking stability.
Action Dispatcher: Translates facial expressions into discrete OS actions:
Blink (Close Both Eyes for 0.4s) -> Left Click
Jaw Open -> Scroll Down
Smile -> Enter
System Navigator: Translates extreme head poses into OS macros for seamless web browsing:
Yaw Left -> Browser Back (Alt + Left)
Yaw Right -> Browser Forward (Alt + Right)
Pitch Up -> Scroll Up
Predictive Target Magnetism: Employs real-time OpenCV edge-detection (mss) around your cursor. When hovering near clickable UI elements (like buttons or text boxes), the engine generates a subtle magnetic pull, snapping your cursor precisely to the target.
Continuous Voice Dictation: Say "transcribe me" to enter dictation mode. The application automatically pauses all head-tracking and macros so you can speak freely, continuously typing out your words natively via PyAutoGUI. Say "transcribe done" to exit dictation and instantly resume tracking.
Procedural Audio Feedback: Uses pygame.mixer to generate low-latency, multi-sensory audio cues (beeps for clicks, ascending chimes for dragging/dictation) mathematically without relying on external .wav files.
HUD UI Overlay: A modern, draggable, borderless Tkinter HUD. It features real-time eye-tracking crosshairs, a fading nose-movement tail, dictation status text, and a live FPS performance counter.
Blind Accessibility Mode: A specialized mode that boots an autonomous Gemini 2.5 Agent. Say "Agent, describe my screen" to get a visual layout read to you via Text-to-Speech (pyttsx3). Issue complex instructions (e.g. "Agent, open Notepad and write a poem") and the LLM will securely parse its own UI logic into native OS commands.
Panic Hotkey: Press Alt + Q at any time to instantly and safely force-quit the application.
Installation
Clone the repository.
Ensure you have Python 3.8+ installed.
Install the dependencies:
pip install -r requirements.txt
(Optional - For Blind Mode): Create a .env file in the root directory and add your Google Gemini API key:
GEMINI_API_KEY=your_api_key_here
Usage
Run the application to open the Voice-Activated Launcher:
python main.py
(Alternatively, run python launcher.py directly).
Select your mode via voice command or by clicking the buttons.
If using Hands-Free Mode, look at the camera to move the cursor, intentionally blink to click, and use head poses to navigate.
If using Blind Mode, say the wake word "Agent" followed by a command.
Suggestions for Future Improvements (Hackathon Next-Steps)
Local LLM Integration: Replace the Google Web Speech API with a local, privacy-first offline model like Whisper.cpp. You could then pipe the transcribed text through an LLM (like Llama 3 via Ollama) to execute complex semantic commands (e.g., "Summarize this page" or "Open Spotify and play Jazz").
Gaze Tracking: Currently, the cursor is bound to the nose tip. Integrating a dedicated gaze-tracking model (like GazeTracking) would allow the user to point with their eyes while keeping their head perfectly still, reserving head movements strictly for scrolling or window management.
Dynamic Auto-Calibration: Implement a brief 5-second startup calibration phase where the user moves their head in a circle. The system would dynamically calculate the ACTIVE_ZONE_WIDTH and ACTIVE_ZONE_HEIGHT bounds to perfectly match their physical mobility range.
Multi-Monitor Matrix: Update the PyAutoGUI math to seamlessly scale and jump the cursor across a multi-monitor setup without getting trapped on edges.
Gesture Combos: Implement state-machines to track sequences of blendshapes. For example, a "Wink Left + Wink Right + Smile" combo could trigger an OS-level sleep command or open a specific dashboard.
Microservice Architecture: With the new Abstract Base Class Dependency Injection, migrating these engines to gRPC microservices would allow heavy ML vision tasks to run on a dedicated external GPU server while the client runs lightly on a laptop.