import queue
import time
import signal
import sys
import threading
from pynput import keyboard

from tools.vision_pipeline.pipeline import VisionPipeline
from tools.cursor_engine.engine import CursorEngine
from tools.action_dispatcher.dispatcher import ActionDispatcher
from tools.system_navigator.navigator import SystemNavigator
from tools.ui_engine.overlay import UIOverlay
from tools.voice_engine.transcriber import VoiceTranscriber

def main():
    # We use multiple queues to broadcast the data stream to all worker threads
    # This decouples the vision processing loop from OS-execution commands.
    cursor_queue = queue.Queue(maxsize=5)
    action_queue = queue.Queue(maxsize=5)
    navigator_queue = queue.Queue(maxsize=5)
    ui_queue = queue.Queue(maxsize=5)

    # A single master queue that the vision pipeline writes to.
    # A broadcaster thread will read from this and duplicate to the workers.
    master_queue = queue.Queue(maxsize=5)

    pipeline = VisionPipeline(master_queue, target_fps=30)
    cursor_engine = CursorEngine(cursor_queue)
    action_dispatcher = ActionDispatcher(action_queue)
    system_navigator = SystemNavigator(navigator_queue)
    ui_overlay = UIOverlay(ui_queue)

    # Optional Voice Transcriber
    voice_transcriber = None
    try:
        voice_transcriber = VoiceTranscriber()
    except Exception as e:
        print(f"Warning: Could not initialize Voice Transcriber. Skipping. Error: {e}")

    running = True

    def shutdown():
        nonlocal running
        print('Shutting down gracefully...')
        running = False
        pipeline.stop()
        cursor_engine.stop()
        action_dispatcher.stop()
        system_navigator.stop()
        if voice_transcriber:
            voice_transcriber.stop()
        ui_overlay.stop()

    def signal_handler(sig, frame):
        shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    def on_activate_exit():
        print("Global hotkey Alt+Q pressed. Exiting...")
        shutdown()
        # Tkinter mainloop is blocking the main thread, so we must exit aggressively or use root.quit()
        # But we don't have direct access to root here easily, so we use sys.exit or let shutdown do its job
        # os._exit is safe for forcefully killing multithreaded apps when Tkinter is involved.
        import os
        os._exit(0)

    hotkey_listener = keyboard.GlobalHotKeys({
        '<alt>+q': on_activate_exit
    })
    hotkey_listener.start()

    def broadcaster():
        while running:
            try:
                payload = master_queue.get(timeout=0.1)

                # Broadcast payload to workers
                # Use put_nowait to avoid blocking if a worker is slow
                try: cursor_queue.put_nowait(payload)
                except queue.Full: pass

                try: action_queue.put_nowait(payload)
                except queue.Full: pass

                try: navigator_queue.put_nowait(payload)
                except queue.Full: pass

                try: ui_queue.put_nowait(payload)
                except queue.Full: pass

            except queue.Empty:
                pass
            except Exception as e:
                if running:
                    print(f"Broadcaster error: {e}")

    # Start the broadcaster thread
    broadcast_thread = threading.Thread(target=broadcaster, daemon=True)
    broadcast_thread.start()

    # Start vision pipeline in a background thread
    pipeline_thread = threading.Thread(target=pipeline.start, daemon=True)
    pipeline_thread.start()

    # Start worker threads
    cursor_engine.start()
    action_dispatcher.start()
    system_navigator.start()
    if voice_transcriber:
        voice_transcriber.start()

    # Start UI (blocking call in main thread)
    try:
        ui_overlay.start()
    except Exception as e:
        print(f"UI encountered an error: {e}")
    finally:
        shutdown()

    print("Application exited.")

if __name__ == '__main__':
    main()
