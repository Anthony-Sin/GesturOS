# Configuration parameters for easy tweaking during hackathon demos

class Config:
    # --- Vision Pipeline ---
    TARGET_FPS = 30
    LOCK_DURATION_THRESHOLD = 5.0    # seconds required holding still to lock/drag
    LOCK_MOVEMENT_THRESHOLD = 0.025  # increased: easier to hold still without resetting timer
    LOCK_BREAKOUT_THRESHOLD = 0.12   # increased: requires significant movement to break out/drop item

    # --- Cursor Engine ---
    ACTIVE_ZONE_X_CENTER = 0.5
    ACTIVE_ZONE_Y_CENTER = 0.6       # shifted down so the user doesn't have to tilt their head up as high
    ACTIVE_ZONE_WIDTH = 0.18         # slightly wider to require more left/right movement
    ACTIVE_ZONE_HEIGHT = 0.06        # decreased so up/down requires less physical neck movement

    BASE_ALPHA = 0.2                 # lowered from 0.3 to make general movement slightly slower/smoother
    PRECISION_ALPHA = 0.05           # EMA smoothing for slow movement (precision mode)
    VELOCITY_THRESHOLD = 0.005       # threshold to enter precision mode
    DEADZONE_VELOCITY = 0.003        # increased deadzone: completely ignore microscopic jitter

    # --- Action Dispatcher (Blendshapes) ---
    BLINK_THRESHOLD = 0.45           # Score required for eyes to be considered "closed"
    BLINK_DURATION_THRESHOLD = 0.4   # seconds eyes must remain closed to trigger click
    BLINK_COOLDOWN = 0.8             # cooldown after a successful click
    SMILE_THRESHOLD = 0.60           # Score required to trigger 'Enter'
    SMILE_COOLDOWN = 1.0
    JAW_THRESHOLD = 0.60             # Score required to trigger Scroll
    JAW_COOLDOWN = 0.1

    # --- System Navigator (Head Pose) ---
    YAW_THRESHOLD = 30.0             # Degrees
    PITCH_THRESHOLD = 20.0           # Degrees
    NAVIGATOR_COOLDOWN = 1.5

    # --- UI Overlay ---
    UI_WIDTH = 320
    UI_HEIGHT = 240
    HUD_COLOR_MAIN = (0, 255, 255)   # Cyan
    HUD_COLOR_WARN = (0, 0, 255)     # Red
    HUD_COLOR_GOOD = (0, 255, 0)     # Green
