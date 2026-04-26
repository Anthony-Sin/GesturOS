import os 
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_FONT_DPI"] = "96"
os.environ["QT_DPI_ADJUSTMENT_POLICY"] = "AdjustDpi"
import queue
import time
import signal
import sys
import threading
import argparse
import logging
import traceback
import logging.handlers
from pynput import keyboard
import speech_recognition as sr
import pyaudio as _pyaudio
_pyaudio.PyAudio.terminate = lambda self: None
# Setup global logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(module)s] — %(message)s')

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# Rotating file handler
file_handler = logging.handlers.RotatingFileHandler('gesturos.log', maxBytes=5*1024*1024, backupCount=2)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

from tools.vision_pipeline.pipeline import VisionPipeline
from tools.cursor_engine.engine import CursorEngine
from tools.action_dispatcher.dispatcher import ActionDispatcher
from tools.ui_engine.overlay import UIOverlay
from tools.voice_engine.transcriber import VoiceTranscriber
from tools.cursor_engine.magnetism import TargetMagnetism
from tools.agent_engine.gemini_agent import GeminiDesktopAgent
from tools.audio_engine.player import AudioPlayer
from config import default_config

def init_dependencies():
    config = default_config.copy()
    shared_state = {
        "voice_status": "Listening for Wake Word...",
        "dictation_active": False,
        "currently_doing": "AWAITING COMMAND",
        "clicks_saved": 0,
        "voice_commands": 0,
        "cursor_distance": 0
    }
    logger.info("Initializing Dependencies...")
    try:
        audio_player = AudioPlayer()
        logger.info("AudioPlayer initialized successfully.")
    except Exception as e:
        logger.error(f"AudioPlayer init error: {e}")
        audio_player = None
    logger.info("Config and Shared State initialized.")
    return config, shared_state, audio_player

def launch_app():
    logger.info("""
=========================================================
                 A C C E S S I B O T
         Hands-Free Controller & Assistive Agent
=========================================================
 Booting systems...
 Press [Alt + Q] at any time to force quit.
=========================================================
""")
    config, shared_state, audio_player = init_dependencies()
    shared_mic = None
    try:
        shared_mic = sr.Microphone()
    except Exception as e:
        logger.warning(f"Could not open microphone: {e}")
    cursor_queue = queue.Queue(maxsize=5)
    action_queue = queue.Queue(maxsize=5)
    ui_queue = queue.Queue(maxsize=5)
    master_queue = queue.Queue(maxsize=5)

    pipeline = VisionPipeline(master_queue, config, shared_state)
    cursor_engine = CursorEngine(cursor_queue, config, shared_state, audio_player)
    action_dispatcher = ActionDispatcher(action_queue, config, shared_state, audio_player)
    ui_overlay = UIOverlay(ui_queue, config, shared_state, audio_player)
    target_magnetism = TargetMagnetism(cursor_engine, config)

    # Gemini Agent for complex tasks via Voice
    agent = GeminiDesktopAgent(config, shared_state, audio_player)

    # Voice Transcriber for dictation and simple keyboard controls
    try:
        voice_transcriber = VoiceTranscriber(config, shared_state, audio_player)
    except Exception as e:
        logger.warning(f"Could not initialize Voice Transcriber: {e}")
        voice_transcriber = None

    running = True

    def shutdown():
        nonlocal running
        logger.info('Shutting down gracefully...')
        running = False
        pipeline.stop()
        cursor_engine.stop()
        action_dispatcher.stop()
        target_magnetism.stop()
        agent.stop()
        if voice_transcriber:
            voice_transcriber.stop()
        ui_overlay.stop()

    def signal_handler(sig, frame):
        shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    def on_activate_exit():
        logger.info("\n[!] Global hotkey Alt+Q pressed. Force Exiting...")
        shutdown()
        os._exit(0)

    hotkey_listener = keyboard.GlobalHotKeys({
        '<alt>+q': on_activate_exit
    })
    hotkey_listener.start()

    def broadcaster():
        while running:
            try:
                payload = master_queue.get(timeout=0.1)
                try: cursor_queue.put_nowait(payload)
                except queue.Full: pass
                try: action_queue.put_nowait(payload)
                except queue.Full: pass
                try: ui_queue.put_nowait(payload)
                except queue.Full: pass
            except queue.Empty:
                pass
            except Exception as e:
                if running:
                    logger.error(f"Broadcaster error: {e}", exc_info=True)

    broadcast_thread = threading.Thread(target=broadcaster, daemon=True)
    broadcast_thread.start()


    def safe_pipeline_start():
        try:
            pipeline.start()
        except Exception as e:
            logger.exception(f"Vision pipeline thread died: {e}")

    pipeline_thread = threading.Thread(target=safe_pipeline_start, daemon=True)
    pipeline_thread.start()
    time.sleep(3)  # give camera time to init
    logger.info(f"Pipeline running state after 3s: {pipeline.running}")

    cursor_engine.start()
    action_dispatcher.start()
    target_magnetism.start()
    agent.start()
    if voice_transcriber:
        voice_transcriber.start()

    # Start UI (blocking call in main thread)
    try:
        ui_overlay.start()
    except Exception as e:
        logger.exception(f"UI encountered an error: {e}")
    finally:
        shutdown()

def main():
    try:
        logger.info("AccessiBot starting up...")
        launch_app()
        logger.info("AccessiBot shut down cleanly.")
    except Exception as e:
        logger.exception(f"Unhandled exception in AccessiBot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
