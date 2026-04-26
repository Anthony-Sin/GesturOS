# Default configuration dictionary for easy dependency injection
default_config = {
    # --- Vision Pipeline ---
    "TARGET_FPS": 30,
    # Threshold for skipping MediaPipe processing on near-identical frames. Higher = more skips.
    "FRAME_DIFF_THRESHOLD": 1.0,

    # --- Cursor Engine ---
    # Raising active zone centers moves the start point to track head positioning.
    "ACTIVE_ZONE_X_CENTER": 0.5,
    "ACTIVE_ZONE_Y_CENTER": 0.45,

    # Enlarging width/height makes the cursor move less distance per degree of head movement.
    # We enlarge these to drastically decrease sensitivity, forcing larger physical head movements.
    "ACTIVE_ZONE_WIDTH": 0.25,
    "ACTIVE_ZONE_HEIGHT": 0.15,

    # Lowering alpha increases smoothing so the cursor glides rather than snapping around.
    "BASE_ALPHA": 0.15,
    "PRECISION_ALPHA": 0.05,

    # Raising velocity thresholds prevents micro-head movements (wobbles) from moving the cursor.
    "VELOCITY_THRESHOLD": 0.003,
    "DEADZONE_VELOCITY": 0.002,

    # --- Action Dispatcher (Blendshapes) ---
    # Raising the blink threshold requires a harder/more closed eye blink to register.
    "BLINK_THRESHOLD": 0.26,

    # Raising the duration threshold forces the user to deliberately hold their eyes shut,
    # preventing reflex blinks from triggering clicks.
    "BLINK_DURATION_THRESHOLD": 0.25,

    # Raising cooldown makes it physically impossible to double-fire a blink action unintentionally.
    "BLINK_COOLDOWN": 2.0,

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

    # --- AI Models ---
    # Fast path OS command translation
    "LLM_FLASH_MODEL": "gemini-1.5-flash",
    # Complex autonomous computer use tasks
    "LLM_AGENT_MODEL": "gemini-2.5-computer-use-preview-10-2025"
}
