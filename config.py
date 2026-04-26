default_config = {
    # --- Vision Pipeline ---
    "TARGET_FPS": 30,
    "FRAME_DIFF_THRESHOLD": 1.0,

    # --- Cursor Engine ---
    "ACTIVE_ZONE_X_CENTER": 0.5,
    "ACTIVE_ZONE_Y_CENTER": 0.45,

    # REDUCED: Less physical neck movement required to reach screen edges.
    "ACTIVE_ZONE_WIDTH": 0.12,  
    "ACTIVE_ZONE_HEIGHT": 0.08,

    # REDUCED: More drag/smoothing applied to counteract the smaller active zone.
    "BASE_ALPHA": 0.08, 
    "PRECISION_ALPHA": 0.02,

    # INCREASED: Ignores tiny head tremors so the cursor stays still when resting.
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
    # You might want to slightly increase pull strength if you still have trouble clicking targets
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