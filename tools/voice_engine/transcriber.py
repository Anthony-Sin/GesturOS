import logging
logger = logging.getLogger(__name__)

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

        try:
            self.microphone = sr.Microphone()
        except Exception:
            self.microphone = None
            logger.warning("No mic found for transcriber.")

        self.running = False

        if self.microphone:
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.energy_threshold = 300
            self.recognizer.pause_threshold = 0.8

            with self.microphone as source:
                logger.info("Adjusting microphone for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=2)
                logger.info(f"Microphone ready. Energy threshold: {self.recognizer.energy_threshold}")

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        logger.info("Voice Transcriber started. Listening for 'transcript now'...")
        return thread

    def stop(self):
        self.running = False

    def _run_loop(self):
        if not self.microphone:
            return

        wake_words = [
            "transcribe me", "transcript me", "transcribe ne",
            "subscribe me", "transcribe", "start dictation"
        ]

        cancel_words = ["stop", "cancel", "abort"]

        while self.running:
            try:
                self.shared_state["voice_status"] = "Listening for 'transcribe me'..."
                with self.microphone as source:
                    # To prevent blocking for cancellation, listen timeout is reduced to 2s
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=10)

                self.shared_state["voice_status"] = "Processing..."
                text = self.recognizer.recognize_google(audio).lower()
                logger.info(f"[Voice Heard]: {text}")

                # Check for cancellation of agent action
                if any(word in text for word in cancel_words):
                    logger.info("--> Cancel voice command detected!")
                    self.shared_state["cancel_action"] = True
                    with self.shared_state["lock"]:
                        self.shared_state["voice_commands_executed"] = self.shared_state.get("voice_commands_executed", 0) + 1

                # Check for trigger phrase
                if any(word in text for word in wake_words):
                    logger.info("--> Trigger activated! Entering continuous dictation mode...")
                    with self.shared_state["lock"]:
                        self.shared_state["voice_commands_executed"] = self.shared_state.get("voice_commands_executed", 0) + 1
                    self._dictate()
                elif text.startswith("press "):
                    self._handle_keyboard_command(text)

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                logger.error(f"Could not request results from Speech Recognition service; {e}")
            except Exception as e:
                pass

    def _dictate(self):
        self.shared_state["dictation_active"] = True
        if self.audio_player:
            self.audio_player.play('dictation_start')
        logger.info("Dictation mode active. Tracking paused. Say 'transcribe done' to exit.")
        self.shared_state["voice_status"] = "DICTATING (Say 'transcribe done' to stop)"

        exit_words = ["transcribe done", "transcript done", "stop dictation", "stop transcribing"]

        while self.running and self.shared_state["dictation_active"]:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=15)

                text = self.recognizer.recognize_google(audio).lower()
                logger.info(f"Dictated Chunk: {text}")

                exit_found = False
                for e_word in exit_words:
                    if e_word in text:
                        final_text = text.replace(e_word, "").strip()
                        if final_text:
                            pyautogui.write(final_text + " ", interval=0.01)

                        logger.info("--> Exit phrase detected. Ending dictation...")
                        self.shared_state["dictation_active"] = False
                        if self.audio_player:
                            self.audio_player.play('dictation_stop')
                        exit_found = True
                        break

                if exit_found:
                    break
                else:
                    pyautogui.write(text + " ", interval=0.01)
                    self.shared_state["voice_status"] = f"TYPED: {text[:15]}..."

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                logger.error(f"Service error during dictation: {e}")
                self.shared_state["dictation_active"] = False
                break

        self.shared_state["dictation_active"] = False
        self.shared_state["voice_status"] = "Listening for 'transcribe me'..."

    def _handle_keyboard_command(self, text):
        key = text.replace("press ", "").strip()
        logger.info(f"--> Keyboard command detected: press '{key}'")
        self.shared_state["voice_status"] = f"Pressed: {key}"
        with self.shared_state["lock"]:
            self.shared_state["voice_commands_executed"] = self.shared_state.get("voice_commands_executed", 0) + 1

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
            logger.error(f"Could not press key '{target_key}': {e}")
