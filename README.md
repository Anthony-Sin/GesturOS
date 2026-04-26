# AccessiBot: Hands-Free Accessibility Suite
A comprehensive Python application designed for motor-impaired users. It translates natural head movements and voice commands into precise OS-level interactions, combining computer vision cursor tracking with a fully autonomous, voice-activated AI Desktop Agent.

## Core Features
*   **Cursor Engine**: Moves your mouse cursor based on the position of your nose using MediaPipe. Features a dynamic 1 Euro Filter to eliminate jitter and an asymmetrical "Active Zone" to minimize physical neck strain.
*   **Action Dispatcher**: Translates facial expressions into discrete OS actions:
    *   Blink (Close Both Eyes for 0.25s) -> Left Click
*   **Voice Control & Dictation**:
    *   Say "transcribe me" to enter continuous dictation mode and type hands-free. Say "transcribe done" to exit.
    *   Say "press [key]" (e.g., "press tab", "press enter") to execute keyboard commands.
*   **Predictive Target Magnetism**: Employs real-time OpenCV edge-detection around your cursor. When hovering near clickable UI elements, the engine generates a subtle magnetic pull to snap your cursor precisely to the target.
*   **Autonomous Gemini Desktop Agent**: A fully voice-activated AI assistant. Say "Agent, [task]" (e.g., "Agent, fill out this form") to trigger the Gemini Computer Use model. The agent will take screenshots, analyze the screen, and execute multi-step mouse and keyboard actions autonomously. For highly destructive actions, it will ask for verbal confirmation via ElevenLabs TTS before proceeding.
*   **Procedural Audio Feedback**: Uses `pygame.mixer` to generate low-latency audio cues for clicks and tracking modes.
*   **Modern UI Overlay**: A sleek, minimal, dark-mode Tkinter overlay positioned in the bottom-right corner. It features a live webcam feed with a retractable sidebar containing voice/face instructions, dynamic crosshairs, eye-state indicators, and a status banner.
*   **Panic Hotkey**: Press `Alt + Q` at any time to instantly and safely force-quit the application.

## Installation
1. Clone the repository.
2. Ensure you have Python 3.10+ installed.
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. **API Keys (Required)**: Create a `.env` file in the root directory and add the following keys exactly as written:
   ```env
   GEMINI_API_KEY=your_google_gemini_key_here
   ELEVENLABS_API_KEY=your_elevenlabs_tts_key_here
   ```

## Model Configuration
You can configure which Gemini models are used for specific tasks by editing the `default_config` dictionary in `config.py`.
*   `LLM_FLASH_MODEL`: Used for fast-path reasoning and simple intent translation (Default: `gemini-1.5-flash`).
*   `LLM_AGENT_MODEL`: Used for the multi-step visual Computer Use Agent loop (Default: `gemini-2.5-computer-use-preview-10-2025`).

## Usage
Run the application to boot directly into hands-free mode:
```bash
python main.py
```
Look at the camera to move the cursor. Expand the UI sidebar via the arrow toggle to view the available commands. Use "Agent [command]" for complex autonomous tasks.
Suggestions for Future Improvements (Hackathon Next-Steps)
Local LLM Integration: Replace the Google Web Speech API with a local, privacy-first offline model like Whisper.cpp. You could then pipe the transcribed text through an LLM (like Llama 3 via Ollama) to execute complex semantic commands (e.g., "Summarize this page" or "Open Spotify and play Jazz").
Gaze Tracking: Currently, the cursor is bound to the nose tip. Integrating a dedicated gaze-tracking model (like GazeTracking) would allow the user to point with their eyes while keeping their head perfectly still, reserving head movements strictly for scrolling or window management.
Dynamic Auto-Calibration: Implement a brief 5-second startup calibration phase where the user moves their head in a circle. The system would dynamically calculate the ACTIVE_ZONE_WIDTH and ACTIVE_ZONE_HEIGHT bounds to perfectly match their physical mobility range.
Multi-Monitor Matrix: Update the PyAutoGUI math to seamlessly scale and jump the cursor across a multi-monitor setup without getting trapped on edges.
Gesture Combos: Implement state-machines to track sequences of blendshapes. For example, a "Wink Left + Wink Right + Smile" combo could trigger an OS-level sleep command or open a specific dashboard.
Microservice Architecture: With the new Abstract Base Class Dependency Injection, migrating these engines to gRPC microservices would allow heavy ML vision tasks to run on a dedicated external GPU server while the client runs lightly on a laptop.