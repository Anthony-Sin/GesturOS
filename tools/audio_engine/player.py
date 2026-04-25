import pygame
import numpy as np

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
