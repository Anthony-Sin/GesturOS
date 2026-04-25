import speech_recognition as sr
import threading
import pyautogui
from shared_state import state
from tools.audio_engine.player import AudioPlayer

class VoiceTranscriber:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.running = False

        # Configure recognizer for better responsiveness
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300 # Lower threshold to catch quieter speech
        self.recognizer.pause_threshold = 0.8  # Shorter pause to end phrase quickly

        # Adjust for ambient noise on startup
        with self.microphone as source:
            print("Adjusting microphone for ambient noise...")
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
            print(f"Microphone ready. Energy threshold: {self.recognizer.energy_threshold}")

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        print("Voice Transcriber started. Listening for 'transcript now'...")
        return thread

    def stop(self):
        self.running = False

    def _run_loop(self):
        # A list of phonetic variations to handle accents and misinterpretations
        wake_words = [
            "transcribe me", "transcript me", "transcribe ne",
            "subscribe me", "transcribe", "start dictation"
        ]

        while self.running:
            try:
                state["voice_status"] = "Listening for 'transcribe me'..."
                with self.microphone as source:
                    # Listen without strict timeout so we don't abort mid-speech
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=10)

                state["voice_status"] = "Processing..."
                # Use Google Web Speech API (free, doesn't require API key for light usage)
                text = self.recognizer.recognize_google(audio).lower()
                print(f"[Voice Heard]: {text}")

                # Check for trigger phrase using fuzzy matching / phonetic variations
                if any(word in text for word in wake_words):
                    print("--> Trigger activated! Entering continuous dictation mode...")
                    self._dictate()

            except sr.WaitTimeoutError:
                # No speech detected within timeout, just continue loop
                pass
            except sr.UnknownValueError:
                # Speech was unintelligible
                pass
            except sr.RequestError as e:
                print(f"Could not request results from Speech Recognition service; {e}")
            except Exception as e:
                # Catch-all for unexpected errors (e.g. mic disconnect)
                print(f"Voice Transcriber error: {e}")

    def _dictate(self):
        # We are now in dictation mode.
        state["dictation_active"] = True
        AudioPlayer().play('dictation_start')
        print("Dictation mode active. Tracking paused. Say 'transcribe done' to exit.")
        state["voice_status"] = "DICTATING (Say 'transcribe done' to stop)"

        exit_words = ["transcribe done", "transcript done", "stop dictation", "stop transcribing"]

        while self.running and state["dictation_active"]:
            try:
                with self.microphone as source:
                    # Listen continuously until silence
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=15)

                text = self.recognizer.recognize_google(audio).lower()
                print(f"Dictated Chunk: {text}")

                # Check if any exit word is in the text
                exit_found = False
                for e_word in exit_words:
                    if e_word in text:
                        # Write everything before the exit phrase
                        final_text = text.replace(e_word, "").strip()
                        if final_text:
                            pyautogui.write(final_text + " ", interval=0.01)

                        print("--> Exit phrase detected. Ending dictation...")
                        state["dictation_active"] = False
                        AudioPlayer().play('dictation_stop')
                        exit_found = True
                        break

                if exit_found:
                    break
                else:
                    # Write the chunk immediately
                    pyautogui.write(text + " ", interval=0.01)
                    state["voice_status"] = f"TYPED: {text[:15]}..."

            except sr.WaitTimeoutError:
                pass # Just keep listening if they are silent
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"Service error during dictation: {e}")
                state["dictation_active"] = False
                break

        state["dictation_active"] = False
        state["voice_status"] = "Listening for 'transcribe me'..."
