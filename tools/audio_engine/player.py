import os
os.environ["SDL_WINDOWS_DPI_AWARENESS"] = "unaware"

import base64
import binascii
import queue
import tempfile
import threading
import winsound
import logging

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class _ElevenLabsCompatAdapter:
    """
    Drop-in adapter that keeps an ElevenLabs-like interface while routing
    synthesis through the internal TTS backend.
    """

    DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"

    class _TextToSpeechProxy:
        def __init__(self, adapter):
            self._adapter = adapter

        def convert(self, voice_id, output_format, text, model_id):
            _ = voice_id
            _ = output_format
            _ = model_id
            audio_bytes = self._adapter._generate_audio_bytes(text)
            if audio_bytes:
                yield audio_bytes

    def __init__(self, api_key: str, model_name: str = "", voice_name: str = ""):
        self.api_key = (api_key or "").strip()
        self.model_name = (model_name or "").strip() or self.DEFAULT_MODEL
        self.voice_name = (voice_name or "").strip()
        self.last_mime_type = "audio/wav"
        self.text_to_speech = _ElevenLabsCompatAdapter._TextToSpeechProxy(self)

    def _generate_audio_bytes(self, text: str) -> bytes:
        safe_text = str(text or "").strip()
        if not safe_text:
            return b""
        if len(safe_text) > 600:
            safe_text = safe_text[:600]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": safe_text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"]},
        }
        if self.voice_name:
            payload["generationConfig"]["speechConfig"] = {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": self.voice_name
                    }
                }
            }

        response = requests.post(
            url,
            params={"key": self.api_key},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()

        inline_data = self._find_inline_audio(data)
        if not inline_data:
            raise ValueError("No inline audio data returned from TTS response.")

        encoded_audio = inline_data.get("data")
        if not encoded_audio:
            raise ValueError("TTS response contained inline data without payload.")

        self.last_mime_type = inline_data.get("mimeType") or inline_data.get("mime_type") or "audio/wav"
        try:
            return base64.b64decode(encoded_audio)
        except (binascii.Error, ValueError) as e:
            raise ValueError(f"Failed to decode TTS audio payload: {e}") from e

    def _find_inline_audio(self, node):
        if isinstance(node, dict):
            inline = node.get("inlineData") or node.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                return inline
            for value in node.values():
                found = self._find_inline_audio(value)
                if found:
                    return found
            return None

        if isinstance(node, list):
            for item in node:
                found = self._find_inline_audio(item)
                if found:
                    return found
            return None

        return None


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

                self.tts_queue = queue.Queue()
                self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
                self.tts_thread.start()

                api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
                if not api_key or api_key.lower().startswith("your_elevenlabs"):
                    # Use the same assistant key as the rest of the stack.
                    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()

                elevenlabs_model_name = (os.getenv("ELEVENLABS_MODEL_ID") or "").strip()
                elevenlabs_voice_name = (os.getenv("ELEVENLABS_VOICE_NAME") or "").strip()

                if api_key:
                    try:
                        self.elevenlabs_client = _ElevenLabsCompatAdapter(
                            api_key=api_key,
                            model_name=elevenlabs_model_name,
                            voice_name=elevenlabs_voice_name,
                        )
                        logger.info("ElevenLabs TTS client initialized.")
                    except Exception as e:
                        logger.warning(f"Failed to init ElevenLabs client: {e}")
                else:
                    logger.warning("No TTS API key found. Spoken output will use text fallback.")

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
            # Fire and forget on a daemon thread; never blocks anything.
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
            try:
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
                            mime_type = str(getattr(self.elevenlabs_client, "last_mime_type", "audio/wav")).lower()
                            suffix = ".wav" if "wav" in mime_type else ".bin"

                            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                                f.write(audio_data)
                                tmp_path = f.name

                            try:
                                if suffix == ".wav":
                                    winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
                                    played_audio = True
                                else:
                                    logger.warning(f"Unsupported TTS mime type for winsound playback: {mime_type}")
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
            finally:
                self.tts_queue.task_done()
