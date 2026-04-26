default_config = {
    # --- Vision Pipeline ---
    "TARGET_FPS": 30,
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
    "ACTIVE_ZONE_Y_CENTER": 0.45,
    # Always place cursor at screen center on startup for predictable default position.
    "FORCE_CURSOR_CENTER_ON_START": True,
    # Disable one-frame startup calibration (can bias position too high/low).
    "AUTO_CENTER_ON_START": False,

    # FURTHER REDUCED: Minimal physical head movement required.
    # Wider zones = slower movement. X intentionally slower per request.
    "ACTIVE_ZONE_WIDTH": 0.11,
    # Slightly taller zone to reduce vertical sensitivity and dead feeling.
    "ACTIVE_ZONE_HEIGHT": 0.08,

    # HEAVILY REDUCED: Massive smoothing applied. Cursor will trail behind your head smoothly.
    "BASE_ALPHA": 0.03, 
    "PRECISION_ALPHA": 0.01,
    # OneEuro cursor filtering: tuned for responsiveness with controlled jitter.
    "FILTER_MIN_CUTOFF": 1.2,
    "FILTER_BETA_NORMAL": 0.08,
    "FILTER_MIN_CUTOFF_LOCKED": 0.8,
    "FILTER_BETA_LOCKED": 0.02,

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
    # --- LLM Cost / Safety Guardrails ---
    "LLM_ROUTER_MAX_OUTPUT_TOKENS": 96,
    "AGENT_MAX_OUTPUT_TOKENS": 256,
    "AGENT_MAX_TURNS": 6,
    "AGENT_MAX_ACTIONS_PER_TASK": 18,
    "AGENT_MAX_TOOL_ERRORS": 4,
    "AGENT_MAX_HISTORY_ITEMS": 8,
    "AGENT_SCREENSHOT_MAX_W": 1280,
    "AGENT_SCREENSHOT_MAX_H": 800,

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
