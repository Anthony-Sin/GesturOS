import os
import io
import pygame
import numpy as np
import pyttsx3
import threading
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

load_dotenv()

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
                # Initialize pygame mixer with standard settings (44100 Hz, 16 bit, 2 channels)
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

                # Initialize pyttsx3 fallback
                try:
                    self.tts = pyttsx3.init()
                    self.tts.setProperty('rate', 150)
                except Exception as e:
                    print(f"Failed to init pyttsx3 fallback: {e}")
                    self.tts = None

                # Initialize ElevenLabs
                self.elevenlabs_client = None
                api_key = os.getenv("ELEVENLABS_API_KEY")
                if api_key:
                    try:
                        self.elevenlabs_client = ElevenLabs(api_key=api_key)
                    except Exception as e:
                        print(f"Failed to init ElevenLabs client: {e}")

                # Pre-generate sounds procedurally to avoid file dependencies
                self.sounds = {
                    'click': self._generate_beep(600, 0.05, 'sine'),
                    'lock_progress': self._generate_beep(800, 0.03, 'sine', volume=0.2),
                    'lock_engage': self._generate_chime([440, 554, 659], 0.2), # A major chord
                    'lock_release': self._generate_chime([659, 554, 440], 0.2), # Descending
                    'dictation_start': self._generate_chime([523, 659], 0.15),
                    'dictation_stop': self._generate_chime([659, 523], 0.15)
                }
                AudioPlayer._initialized = True
                print("Audio Engine initialized successfully.")
            except Exception as e:
                print(f"Failed to initialize audio engine: {e}")
                AudioPlayer._initialized = False

    def _generate_beep(self, frequency, duration, wave_type='sine', volume=0.5):
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration), False)

        if wave_type == 'sine':
            wave = np.sin(frequency * t * 2 * np.pi)
        elif wave_type == 'square':
            wave = np.sign(np.sin(frequency * t * 2 * np.pi))
        else:
            wave = np.sin(frequency * t * 2 * np.pi)

        # Apply simple envelope to avoid clicks at start/end
        fade_samples = int(sample_rate * 0.01)
        if len(wave) > fade_samples * 2:
            envelope = np.ones_like(wave)
            envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
            envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
            wave = wave * envelope

        # Convert to 16-bit PCM stereo array
        wave = wave * volume * 32767
        wave = wave.astype(np.int16)
        stereo_wave = np.column_stack((wave, wave))

        return pygame.sndarray.make_sound(stereo_wave)

    def _generate_chime(self, frequencies, duration_per_note, volume=0.5):
        sample_rate = 44100
        total_duration = len(frequencies) * duration_per_note
        t = np.linspace(0, total_duration, int(sample_rate * total_duration), False)

        full_wave = np.zeros_like(t)
        samples_per_note = int(sample_rate * duration_per_note)

        for i, freq in enumerate(frequencies):
            start_idx = i * samples_per_note
            end_idx = start_idx + samples_per_note

            note_t = np.linspace(0, duration_per_note, samples_per_note, False)
            wave = np.sin(freq * note_t * 2 * np.pi)

            # envelope
            fade = int(sample_rate * 0.01)
            envelope = np.ones_like(wave)
            envelope[:fade] = np.linspace(0, 1, fade)
            envelope[-fade:] = np.linspace(1, 0, fade)
            wave = wave * envelope

            full_wave[start_idx:end_idx] = wave

        full_wave = full_wave * volume * 32767
        full_wave = full_wave.astype(np.int16)
        stereo_wave = np.column_stack((full_wave, full_wave))
        return pygame.sndarray.make_sound(stereo_wave)

    def play(self, sound_name):
        if not AudioPlayer._initialized:
            return
        sound = self.sounds.get(sound_name)
        if sound:
            # Play on an available channel
            sound.play()

    def speak(self, text):
        print(f"[Audio Engine Says]: {text}")
        if not text:
            return

        def _speak_thread():
            use_fallback = True

            if self.elevenlabs_client:
                try:
                    # Generate speech
                    audio_generator = self.elevenlabs_client.generate(
                        text=text,
                        voice="Rachel",
                        model="eleven_multilingual_v2"
                    )

                    # Accumulate bytes
                    audio_data = b""
                    for chunk in audio_generator:
                        if chunk:
                            audio_data += chunk

                    # Play via pygame using an in-memory file
                    if audio_data:
                        audio_file = io.BytesIO(audio_data)
                        try:
                            # Use pygame to load the mp3 bytes
                            sound = pygame.mixer.Sound(audio_file)
                            sound.play()
                            # Wait for it to finish playing
                            pygame.time.wait(int(sound.get_length() * 1000))
                            use_fallback = False
                        except pygame.error as e:
                            print(f"Pygame failed to play ElevenLabs audio: {e}")
                except Exception as e:
                    print(f"ElevenLabs generation failed: {e}")

            if use_fallback and self.tts:
                try:
                    self.tts.say(text)
                    self.tts.runAndWait()
                except Exception as e:
                    print(f"pyttsx3 fallback failed: {e}")

        # Run speech in background to avoid blocking
        threading.Thread(target=_speak_thread, daemon=True).start()
