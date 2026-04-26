import threading
import pyaudio

_lock     = threading.Lock()
_instance = None

def get_pyaudio() -> pyaudio.PyAudio:
    global _instance
    with _lock:
        if _instance is None:
            _instance = pyaudio.PyAudio()
        return _instance