default_config = {
    # --- Vision Pipeline ---
    "TARGET_FPS": 30,
    # Optional quick startup calibration for different seating/camera positions.
    "ENABLE_QUICK_CALIBRATION": True,
    "QUICK_CALIBRATION_DURATION_SECONDS": 1.2,
    "QUICK_CALIBRATION_WAIT_FOR_UI_SECONDS": 5.0,
    "QUICK_CALIBRATION_SUMMARY_SECONDS": 4.0,
    "QUICK_CALIBRATION_MIN_SAMPLES": 12,
    "QUICK_CALIBRATION_MAX_CENTER_SHIFT": 0.12,
    "QUICK_CALIBRATION_MAX_SECONDS": 8.0,
    "QUICK_CALIBRATION_REQUIRE_ALL_POINTS": True,
    "QUICK_CALIBRATION_TARGET_RADIUS_PX": 85,
    "QUICK_CALIBRATION_DWELL_SAMPLES": 6,
    "QUICK_CALIBRATION_EDGE_PADDING": 0.06,
    "QUICK_CALIBRATION_ZONE_SCALE_X": 1.25,
    "QUICK_CALIBRATION_ZONE_SCALE_Y": 1.20,
    "QUICK_CALIBRATION_MIN_WIDTH": 0.13,
    "QUICK_CALIBRATION_MIN_HEIGHT": 0.10,
    "QUICK_CALIBRATION_MAX_WIDTH": 0.42,
    "QUICK_CALIBRATION_MAX_HEIGHT": 0.34,
    # Keep final center in a comfortable middle band to reduce edge bias.
    "QUICK_CALIBRATION_CENTER_BLEND": 1.0,
    "QUICK_CALIBRATION_DEFAULT_CENTER_BIAS": 0.0,
    "QUICK_CALIBRATION_FORCE_NEUTRAL_CENTER": True,
    "QUICK_CALIBRATION_CENTER_MIN_X": 0.32,
    "QUICK_CALIBRATION_CENTER_MAX_X": 0.68,
    "QUICK_CALIBRATION_CENTER_MIN_Y": 0.30,
    "QUICK_CALIBRATION_CENTER_MAX_Y": 0.70,
    "QUICK_CALIBRATION_POINTS": [
        (0.50, 0.50),
        (0.30, 0.50),
        (0.70, 0.50),
        (0.50, 0.34),
        (0.50, 0.70),
    ],
    # Set to 0 to disable stale-frame reuse and keep overlay/cursor low-latency.
    "FRAME_DIFF_THRESHOLD": 0.0,
    # Safety cap if frame-diff reuse is re-enabled.
    "MAX_REUSED_LANDMARK_FRAMES": 1,
    # Locking behavior: less accidental lock, easier breakout.
    "LOCK_DURATION_THRESHOLD": 6.5,
    "LOCK_MOVEMENT_THRESHOLD": 0.018,
    "LOCK_BREAKOUT_THRESHOLD": 0.07,

    # --- Cursor Engine ---
    "ACTIVE_ZONE_X_CENTER": 0.5,
    "ACTIVE_ZONE_Y_CENTER": 0.50,
    # Always place cursor at screen center on startup for predictable default position.
    "FORCE_CURSOR_CENTER_ON_START": True,
    # Disable one-frame startup calibration (can bias position too high/low).
    "AUTO_CENTER_ON_START": False,

    # FURTHER REDUCED: Minimal physical head movement required.
    # Wider zones = slower movement. X intentionally slower per request.
    "ACTIVE_ZONE_WIDTH": 0.16,
    # Slightly taller zone to reduce vertical sensitivity and dead feeling.
    "ACTIVE_ZONE_HEIGHT": 0.13,

    # HEAVILY REDUCED: Massive smoothing applied. Cursor will trail behind your head smoothly.
    "BASE_ALPHA": 0.03, 
    "PRECISION_ALPHA": 0.01,
    # OneEuro cursor filtering: tuned for responsiveness with controlled jitter.
    "FILTER_MIN_CUTOFF": 1.75,
    "FILTER_BETA_NORMAL": 0.13,
    "FILTER_MIN_CUTOFF_LOCKED": 0.8,
    "FILTER_BETA_LOCKED": 0.02,
    # Gradual sensitivity shaping: slower micro-movement around focus area.
    "CURSOR_RESPONSE_EXPONENT_X": 2.25,
    "CURSOR_RESPONSE_EXPONENT_Y": 2.45,
    # Directional Y shaping: make downward movement easier while keeping top control stable.
    "CURSOR_RESPONSE_EXPONENT_Y_UP": 2.45,
    "CURSOR_RESPONSE_EXPONENT_Y_DOWN": 2.05,
    "CURSOR_DOWNWARD_BOOST": 1.18,
    "CURSOR_MICRO_GAIN": 0.22,
    "CURSOR_MICRO_RADIUS": 0.46,
    "CURSOR_PIXEL_DEADZONE": 1.6,
    # Hard cap on per-frame movement to prevent jumpy cursor spikes.
    "CURSOR_MAX_STEP_PX": 55.0,
    # Anti-drift hold when head remains still near current cursor target.
    "CURSOR_STILLNESS_HEAD_THRESHOLD": 0.0014,
    "CURSOR_STILLNESS_TARGET_WINDOW_PX": 14.0,
    "CURSOR_STILLNESS_FRAMES": 5,

    # Keeping deadzones high to prevent resting jitter.
    "VELOCITY_THRESHOLD": 0.005, 
    "DEADZONE_VELOCITY": 0.0015,

    # --- Action Dispatcher (Blendshapes) ---
    "BLINK_THRESHOLD": 0.5,
    "BLINK_DURATION_THRESHOLD": 0.35,
    "BLINK_COOLDOWN": 2.0,

    # --- UI Overlay ---
    "UI_WIDTH": 320,
    "UI_HEIGHT": 240,
    "HUD_COLOR_MAIN": (0, 255, 255),
    "HUD_COLOR_WARN": (0, 0, 255),
    "HUD_COLOR_GOOD": (0, 255, 0),

    # --- Target Magnetism ---
    "MAGNETISM_SEARCH_RADIUS": 150,
    # Use a soft pull to prevent hard lock-in behavior.
    "MAGNETISM_PULL_STRENGTH": 0.35,
    "MAGNETISM_TRIGGER_DISTANCE": 40,
    # Break out from magnetism without forcing head backtracking.
    "MAGNETISM_RELEASE_DISTANCE": 72,
    # Sniper mode (voice-controlled magnetism) settings.
    "SNIPER_SWITCH_THRESHOLD_PX": 60,
    "SNIPER_CANDIDATE_DISTANCE": 70,

    # --- AI Models ---
    "LLM_FLASH_MODEL": "gemini-2.5-flash-lite",
    "LLM_AGENT_MODEL": "gemini-2.5-computer-use-preview-10-2025",
    # Browser automation backend for Computer Use actions.
    "AGENT_BROWSER_BACKEND": "playwright",
    "PLAYWRIGHT_USER_DATA_DIR": r"C:\Users\antho\AppData\Local\Microsoft\Edge\User Data",
    "PLAYWRIGHT_BROWSER_CHANNEL": "msedge",
    "PLAYWRIGHT_VIEWPORT_W": 1440,
    "PLAYWRIGHT_VIEWPORT_H": 900,
    # Do not play automatic TTS at app startup.
    "AGENT_STARTUP_TTS": False,
    # --- LLM Cost / Safety Guardrails ---
    "LLM_ROUTER_MAX_OUTPUT_TOKENS": 96,
    "AGENT_MAX_OUTPUT_TOKENS": 256,
    "AGENT_MAX_TURNS": 6,
    "AGENT_MAX_ACTIONS_PER_TASK": 18,
    "AGENT_MAX_TOOL_ERRORS": 4,
    "AGENT_MAX_HISTORY_ITEMS": 8,
    "AGENT_SCREENSHOT_MAX_W": 1280,
    "AGENT_SCREENSHOT_MAX_H": 800,
    # Hard billing/loop safety caps.
    "AGENT_MAX_API_CALLS_PER_TASK": 4,
    "AGENT_MAX_RUNTIME_SECONDS": 70,
    "AGENT_MIN_SECONDS_BETWEEN_RUNS": 10.0,
    "AGENT_SESSION_RUN_LIMIT": 8,

    # --- Scrolling Settings ---
    "SCROLL_BROW_THRESHOLD": 0.4,
    "SCROLL_HOLD_DURATION": 5.0,
    # After N brow-triggered scroll activations, force a short gesture reset window.
    "SCROLL_RESET_AFTER_ACTIVATIONS": 4,
    "SCROLL_RESET_COOLDOWN": 0.9,

    # --- Look Away Auto-Pause Settings ---
    "LOOK_AWAY_PITCH_THRESHOLD": 35.0,
    "LOOK_AWAY_YAW_THRESHOLD": 35.0
}
