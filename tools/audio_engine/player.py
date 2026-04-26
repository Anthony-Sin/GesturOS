import os
os.environ["SDL_WINDOWS_DPI_AWARENESS"] = "unaware"

import base64
import binascii
import queue
import tempfile
import threading
import winsound
import logging
import re
import wave

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
                self.gesturos_intro_text = (
                    os.getenv("GESTUROS_INTRO_TEXT")
                    or os.getenv("JUDGE_INTRO_TEXT")
                    or (
                        "This is GesturOS, a hands free computer control system using nose tracking, blink and brow gestures, "
                        "voice commands, and a supervised AI web agent. Calibration is starting now. Move the blue marker into each "
                        "red circle and hold briefly until it advances. Keep your head relaxed and centered. To start dictation, "
                        "say transcribe me or record me."
                    )
                )
                self.audio_cache_dir = os.path.join(os.getcwd(), "cache_audio")
                # Bump filename so updated spoken prompt refreshes existing caches.
                self.gesturos_intro_path = os.path.join(self.audio_cache_dir, "gesturos_intro_v2.wav")
                # Backward-compatible aliases for any remaining callers.
                self.judge_intro_text = self.gesturos_intro_text
                self.judge_intro_path = self.gesturos_intro_path

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

    def _synthesize_tts_wav_bytes(self, text: str):
        if not self.elevenlabs_client:
            return None
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
            if not audio_data:
                return None

            mime_type = str(getattr(self.elevenlabs_client, "last_mime_type", "audio/wav")).lower()
            if "wav" in mime_type:
                return audio_data
            if "audio/l16" in mime_type or "pcm" in mime_type:
                return self._pcm_to_wav_bytes(audio_data, mime_type)
            return None
        except Exception as e:
            logger.warning(f"TTS clip synthesis failed: {e}")
            return None

    def ensure_gesturos_intro_clip(self) -> bool:
        try:
            if os.path.exists(self.gesturos_intro_path) and os.path.getsize(self.gesturos_intro_path) > 0:
                return True
            os.makedirs(self.audio_cache_dir, exist_ok=True)
            wav_bytes = self._synthesize_tts_wav_bytes(self.gesturos_intro_text)
            if not wav_bytes:
                return False
            with open(self.gesturos_intro_path, "wb") as out_file:
                out_file.write(wav_bytes)
            logger.info(f"Cached GesturOS intro clip at: {self.gesturos_intro_path}")
            return True
        except Exception as e:
            logger.warning(f"Could not cache GesturOS intro clip: {e}")
            return False

    def ensure_judge_intro_clip(self) -> bool:
        return self.ensure_gesturos_intro_clip()

    def play_gesturos_intro(self):
        if self.ensure_gesturos_intro_clip():
            print("[Audio Engine Says]: Playing cached GesturOS intro.")
            def _play_cached():
                try:
                    winsound.PlaySound(self.gesturos_intro_path, winsound.SND_FILENAME)
                except Exception as e:
                    logger.warning(f"Could not play cached GesturOS intro: {e}")
                    self.speak(self.gesturos_intro_text)
            threading.Thread(target=_play_cached, daemon=True).start()
            return
        self.speak(self.gesturos_intro_text)

    def play_judge_intro(self):
        self.play_gesturos_intro()

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
                            playable_bytes = audio_data
                            suffix = ".wav"
                            if "wav" in mime_type:
                                suffix = ".wav"
                            elif "audio/l16" in mime_type or "pcm" in mime_type:
                                playable_bytes = self._pcm_to_wav_bytes(audio_data, mime_type)
                                suffix = ".wav"
                            else:
                                suffix = ".bin"

                            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                                f.write(playable_bytes)
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

    def _pcm_to_wav_bytes(self, raw_pcm_bytes: bytes, mime_type: str) -> bytes:
        sample_rate = 24000
        channels = 1

        rate_match = re.search(r"rate=(\d+)", mime_type or "", flags=re.IGNORECASE)
        if rate_match:
            try:
                sample_rate = max(8000, int(rate_match.group(1)))
            except Exception:
                pass

        channel_match = re.search(r"channels?=(\d+)", mime_type or "", flags=re.IGNORECASE)
        if channel_match:
            try:
                channels = max(1, min(2, int(channel_match.group(1))))
            except Exception:
                pass

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            with wave.open(wav_path, "wb") as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(2)  # 16-bit PCM
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(raw_pcm_bytes)
            with open(wav_path, "rb") as wav_in:
                return wav_in.read()
        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass
