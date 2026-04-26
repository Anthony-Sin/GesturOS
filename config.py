default_config = {
    # --- Vision Pipeline ---
    "TARGET_FPS": 30,
    "FRAME_DIFF_THRESHOLD": 1.0,

    # --- Cursor Engine ---
    "ACTIVE_ZONE_X_CENTER": 0.5,
    "ACTIVE_ZONE_Y_CENTER": 0.45,

    # FURTHER REDUCED: Minimal physical head movement required.
    "ACTIVE_ZONE_WIDTH": 0.07,  
    "ACTIVE_ZONE_HEIGHT": 0.05,

    # HEAVILY REDUCED: Massive smoothing applied. Cursor will trail behind your head smoothly.
    "BASE_ALPHA": 0.03, 
    "PRECISION_ALPHA": 0.01,

    # Keeping deadzones high to prevent resting jitter.
    "VELOCITY_THRESHOLD": 0.005, 
    "DEADZONE_VELOCITY": 0.003,

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
    "MAGNETISM_PULL_STRENGTH": 0.7, 
    "MAGNETISM_TRIGGER_DISTANCE": 40,

    # --- AI Models ---
    "LLM_FLASH_MODEL": "gemini-1.5-flash",
    "LLM_AGENT_MODEL": "gemini-2.5-computer-use-preview-10-2025",

    # --- Scrolling Settings ---
    "SCROLL_BROW_THRESHOLD": 0.4,
    "SCROLL_HOLD_DURATION": 5.0,

    # --- Look Away Auto-Pause Settings ---
    "LOOK_AWAY_PITCH_THRESHOLD": 35.0,
    "LOOK_AWAY_YAW_THRESHOLD": 35.0
}