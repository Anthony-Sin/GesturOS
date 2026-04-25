# Hands-Free Accessibility Controller

A local desktop service built in Python that acts as a hands-free accessibility controller. It translates natural head movements and facial expressions—captured via a webcam using MediaPipe Face Landmarker—into discrete OS-level actions such as mouse movements, clicking, scrolling, and keyboard macros.

## Features

- **Cursor Engine**: Moves your mouse cursor based on the position of your nose. Uses an Exponential Moving Average (EMA) for smoothness and an "Active Zone" scaling multiplier so that small head movements map to the full screen, reducing physical strain.
- **Action Dispatcher**: Translates your facial expressions into actions:
  - **Blink** (Close Both Eyes) -> Left Click
  - **Jaw Open** -> Scroll Down
  - **Smile** -> Enter
- **System Navigator**: Translates extreme head poses into OS macros for practical navigation:
  - **Yaw Left** -> Browser Back (`Alt + Left`)
  - **Yaw Right** -> Browser Forward (`Alt + Right`)
  - **Pitch Up** -> Scroll Up
  - **Pitch Down** -> Show Desktop (`Win + D`)
- **UI Overlay**: A modern, draggable, borderless HUD at the bottom right corner showing the camera feed, a trailing path of your nose movement, live eye-tracking status, and a visual indicator when you blink.
- **Multithreaded Architecture**: The heavy vision processing runs independently from the OS command execution and UI loops, ensuring lag-free operation.

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

## Suggestions for Future Improvements

- **Configuration GUI**: Add a settings menu to let users easily bind different macros to specific facial blendshapes and head poses.
- **Calibration Tool**: An interactive initial setup phase where the user moves their head in a comfortable range to dynamically calculate the boundaries of the "Active Zone".
- **Voice Integration**: Combine this project with a local STT (Speech-to-Text) model (like Whisper) to handle complex typing tasks, leaving head-tracking strictly for navigation.
- **Multi-Monitor Support**: Update the PyAutoGUI logic to automatically scale and jump between multiple monitors when reaching edge boundaries.
