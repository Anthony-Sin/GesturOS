import os
os.environ["SDL_WINDOWS_DPI_AWARENESS"] = "unaware"

import io
import queue
import threading
import winsound
import logging
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class AudioPlayer:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AudioPlayer, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not AudioPlayer._initialized:
            try:
                self.elevenlabs_client = None
                api_key = os.getenv("ELEVENLABS_API_KEY")
                if api_key:
                    try:
                        self.elevenlabs_client = ElevenLabs(api_key=api_key)
                    except Exception as e:
                        logger.warning(f"Failed to init ElevenLabs client: {e}")

                self.tts_queue = queue.Queue()
                self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
                self.tts_thread.start()

                # Sound definitions: (frequency_hz, duration_ms)
                self.sounds = {
                    'click':           (600,  50),
                    'lock_progress':   (800,  30),
                    'lock_engage':     (880, 200),
                    'lock_release':    (440, 200),
                    'dictation_start': (523, 150),
                    'dictation_stop':  (659, 150),
                }

                AudioPlayer._initialized = True
                print("Audio Engine initialized successfully.")

            except Exception as e:
                print(f"Failed to initialize audio engine: {e}")
                if not hasattr(self, 'tts_queue'):
                    self.tts_queue = queue.Queue()
                    self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
                    self.tts_thread.start()
                AudioPlayer._initialized = False

    def play(self, sound_name):
        if not AudioPlayer._initialized:
            return
        sound = self.sounds.get(sound_name)
        if sound:
            freq, duration = sound
            # Fire and forget on a daemon thread — never blocks anything
            threading.Thread(
                target=winsound.Beep,
                args=(freq, duration),
                daemon=True
            ).start()

    def speak(self, text):
        if not text:
            return
        print(f"[Audio Engine Says]: {text}")
        self.tts_queue.put(text)

    def _tts_worker(self):
        while True:
            text = self.tts_queue.get()
            if text is None:
                break

            played_audio = False

            if self.elevenlabs_client:
                try:
                    audio_generator = self.elevenlabs_client.text_to_speech.convert(
                        voice_id="21m00Tcm4TlvDq8ikWAM",
                        output_format="mp3_44100_128",
                        text=text,
                        model_id="eleven_multilingual_v2"
                    )

                    audio_data = b""
                    for chunk in audio_generator:
                        if chunk:
                            audio_data += chunk

                    if audio_data:
                        # Write to temp file and play with winsound — no pygame needed
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                            f.write(audio_data)
                            tmp_path = f.name
                        try:
                            winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
                            played_audio = True
                        except Exception as e:
                            logger.warning(f"winsound playback failed: {e}")
                        finally:
                            try:
                                os.remove(tmp_path)
                            except Exception:
                                pass

                except Exception as e:
                    logger.warning(f"ElevenLabs generation failed: {e}")

            if not played_audio:
                print(f"[Audio Engine Backup Print]: {text}")

            self.tts_queue.task_done()