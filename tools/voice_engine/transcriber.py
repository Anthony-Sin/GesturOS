import speech_recognition as sr
import threading
import pyautogui
from tools.interfaces import BaseVoiceEngine

class VoiceTranscriber(BaseVoiceEngine):
    def __init__(self, config: dict, shared_state: dict, audio_player):
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player
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
                self.shared_state["voice_status"] = "Listening for 'transcribe me'..."
                with self.microphone as source:
                    # Listen without strict timeout so we don't abort mid-speech
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=10)

                self.shared_state["voice_status"] = "Processing..."
                # Use Google Web Speech API (free, doesn't require API key for light usage)
                text = self.recognizer.recognize_google(audio).lower()
                print(f"[Voice Heard]: {text}")

                # Check for trigger phrase using fuzzy matching / phonetic variations
                if any(word in text for word in wake_words):
                    print("--> Trigger activated! Entering continuous dictation mode...")
                    self._dictate()
                elif text.startswith("press "):
                    self._handle_keyboard_command(text)

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
        self.shared_state["dictation_active"] = True
        if self.audio_player:
            self.audio_player.play('dictation_start')
        print("Dictation mode active. Tracking paused. Say 'transcribe done' to exit.")
        self.shared_state["voice_status"] = "DICTATING (Say 'transcribe done' to stop)"

        exit_words = ["transcribe done", "transcript done", "stop dictation", "stop transcribing"]

        while self.running and self.shared_state["dictation_active"]:
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
                        self.shared_state["dictation_active"] = False
                        if self.audio_player:
                            self.audio_player.play('dictation_stop')
                        exit_found = True
                        break

                if exit_found:
                    break
                else:
                    # Write the chunk immediately
                    pyautogui.write(text + " ", interval=0.01)
                    self.shared_state["voice_status"] = f"TYPED: {text[:15]}..."

            except sr.WaitTimeoutError:
                pass # Just keep listening if they are silent
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"Service error during dictation: {e}")
                self.shared_state["dictation_active"] = False
                break

        self.shared_state["dictation_active"] = False
        self.shared_state["voice_status"] = "Listening for 'transcribe me'..."

    def _handle_keyboard_command(self, text):
        key = text.replace("press ", "").strip()
        print(f"--> Keyboard command detected: press '{key}'")
        self.shared_state["voice_status"] = f"Pressed: {key}"

        # Mapping spoken words to pyautogui keys
        key_map = {
            "enter": "enter",
            "return": "enter",
            "tab": "tab",
            "space": "space",
            "spacebar": "space",
            "escape": "esc",
            "escape key": "esc",
            "backspace": "backspace",
            "delete": "delete",
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
            "windows": "win",
            "super": "win",
            "command": "command",
            "option": "option",
            "alt": "alt",
            "control": "ctrl",
            "shift": "shift"
        }

        target_key = key_map.get(key, key)
        try:
            pyautogui.press(target_key)
        except Exception as e:
            print(f"Could not press key '{target_key}': {e}")
