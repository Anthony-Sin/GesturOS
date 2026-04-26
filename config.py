# Default configuration dictionary for easy dependency injection
default_config = {
    # --- Vision Pipeline ---
    "TARGET_FPS": 30,

    # --- Cursor Engine ---
    "ACTIVE_ZONE_X_CENTER": 0.5,
    "ACTIVE_ZONE_Y_CENTER": 0.6,
    "ACTIVE_ZONE_WIDTH": 0.18,
    "ACTIVE_ZONE_HEIGHT": 0.06,

    "BASE_ALPHA": 0.2,
    "PRECISION_ALPHA": 0.05,
    "VELOCITY_THRESHOLD": 0.005,
    "DEADZONE_VELOCITY": 0.003,

    # --- Action Dispatcher (Blendshapes) ---
    "BLINK_THRESHOLD": 0.35,
    "BLINK_DURATION_THRESHOLD": 0.15,
    "BLINK_COOLDOWN": 0.8,
    "SMILE_THRESHOLD": 0.60,
    "SMILE_COOLDOWN": 1.0,
    "JAW_THRESHOLD": 0.60,
    "JAW_COOLDOWN": 0.1,

    # --- System Navigator (Head Pose) ---
    "YAW_THRESHOLD": 30.0,
    "PITCH_THRESHOLD": 20.0,
    "NAVIGATOR_COOLDOWN": 1.5,

    # --- UI Overlay ---
    "UI_WIDTH": 320,
    "UI_HEIGHT": 240,
    "HUD_COLOR_MAIN": (0, 255, 255),
    "HUD_COLOR_WARN": (0, 0, 255),
    "HUD_COLOR_GOOD": (0, 255, 0),

    # --- Target Magnetism ---
    "MAGNETISM_SEARCH_RADIUS": 150,
    "MAGNETISM_PULL_STRENGTH": 0.6,
    "MAGNETISM_TRIGGER_DISTANCE": 40,
}
