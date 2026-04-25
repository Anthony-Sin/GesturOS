# Hands-Free Accessibility Controller

A local desktop service built in Python that acts as a hands-free accessibility controller. It translates natural head movements and facial expressions—captured via a webcam using MediaPipe Face Landmarker—into discrete OS-level actions such as mouse movements, clicking, scrolling, and keyboard macros.

## Features

- **Cursor Engine**: Moves your mouse cursor based on the position of your nose. Uses an Exponential Moving Average (EMA) for smoothness and an asymmetrical "Active Zone" multiplier to minimize physical strain. It features a dynamic **Precision Mode** that automatically slows the cursor when you hold still, and a **Micro-Deadzone** to guarantee pixel-perfect clicking stability.
- **Action Dispatcher**: Translates your facial expressions into discrete actions:
  - **Blink** (Close Both Eyes) -> Left Click
  - **Jaw Open** -> Scroll Down
  - **Smile** -> Enter
- **System Navigator**: Translates extreme head poses into OS macros for seamless web browsing:
  - **Yaw Left** -> Browser Back (`Alt + Left`)
  - **Yaw Right** -> Browser Forward (`Alt + Right`)
  - **Pitch Up** -> Scroll Up
- **Drag-and-Drop Locking**: Hold your head still over an item for 5 seconds to trigger a `mouseDown` lock (with a visual progress bar). Move your head to drag the item, and make a sharp movement to break the lock and drop it.
- **Continuous Voice Dictation**: Say **"transcribe me"** to enter dictation mode. The application will pause all head-tracking and macros so you can speak freely, continuously typing out your words using the Google Web Speech API. Say **"transcribe done"** to exit dictation and resume tracking.
- **HUD UI Overlay**: A modern, draggable, borderless HUD in the corner of your screen. It features real-time eye-tracking crosshairs, lock-progress loading bars, a fading nose-movement tail, dictation status text, and a live FPS performance counter.
- **Panic Hotkey**: Press `Alt + Q` at any time to instantly and safely force-quit the application.
- **Centralized Configuration**: All thresholds, sensitivities, deadzones, and lock timers are cleanly exposed in `config.py` for real-time hackathon tuning.

## Installation

1. Clone the repository.
2. Ensure you have Python 3.8+ installed.
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   python main.py
   ```
2. The UI overlay will appear in the bottom right corner.
3. Look at the camera to move the cursor, blink to click, and use head poses to navigate.
4. Press `Ctrl+C` in the terminal to gracefully shut down the application.

## Suggestions for Future Improvements (Hackathon Next-Steps)

- **Local LLM Integration**: Replace the Google Web Speech API with a local, privacy-first offline model like Whisper.cpp. You could then pipe the transcribed text through an LLM (like Llama 3 via Ollama) to execute complex semantic commands (e.g., "Summarize this page" or "Open Spotify and play Jazz").
- **Gaze Tracking**: Currently, the cursor is bound to the *nose tip*. Integrating a dedicated gaze-tracking model (like `GazeTracking`) would allow the user to point with their eyes while keeping their head perfectly still, reserving head movements strictly for scrolling or window management.
- **Dynamic Auto-Calibration**: Implement a brief 5-second startup calibration phase where the user moves their head in a circle. The system would dynamically calculate the `ACTIVE_ZONE_WIDTH` and `ACTIVE_ZONE_HEIGHT` bounds to perfectly match their physical mobility range.
- **Multi-Monitor Matrix**: Update the PyAutoGUI math to seamlessly scale and jump the cursor across a multi-monitor setup without getting trapped on edges.
- **Gesture Combos**: Implement state-machines to track *sequences* of blendshapes. For example, a "Wink Left + Wink Right + Smile" combo could trigger an OS-level sleep command or open a specific dashboard.
