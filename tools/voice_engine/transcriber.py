import speech_recognition as sr
import threading
import pyautogui
import logging
import difflib
import re
from tools.interfaces import BaseVoiceEngine
from tools.audio_engine.pyaudio_singleton import get_pyaudio

logger = logging.getLogger(__name__)

class VoiceTranscriber(BaseVoiceEngine):
    def __init__(self, config: dict, shared_state: dict, audio_player, microphone=None):
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player
        self.recognizer = sr.Recognizer()

        try:
            if microphone is not None:
                self.microphone = microphone
            else:
                try:
                    self.microphone = sr.Microphone()
                except Exception:
                    self.microphone = None
                    logger.warning("No mic found for transcriber.")
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
        logger.info("Voice Transcriber started. Listening for dictation wake words...")
        return thread

    def stop(self):
        self.running = False

    def _run_loop(self):
        if not self.microphone:
            return

        wake_words = [
            "transcribe me", "transcript me", "transcribe ne",
            "subscribe me", "transcribe", "start dictation",
            "record me", "start recording", "record"
        ]

        cancel_words = ["stop", "cancel", "abort"]

        while self.running:
            try:
                if self.shared_state.get("agent_active", False):
                    self.shared_state["voice_status"] = "AGENT ACTIVE (say stop/cancel to interrupt)"
                else:
                    self.shared_state["voice_status"] = "Listening for voice commands..."
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
                    self.shared_state["voice_commands"] = self.shared_state.get("voice_commands", 0) + 1

                # While the desktop agent is active, only allow cancellation phrases.
                if self.shared_state.get("agent_active", False):
                    continue

                if self._handle_sniper_command(text):
                    self.shared_state["voice_commands"] = self.shared_state.get("voice_commands", 0) + 1
                    continue

                # Check for trigger phrase
                if any(word in text for word in wake_words):
                    logger.info("--> Trigger activated! Entering continuous dictation mode...")
                    self.shared_state["voice_commands"] = self.shared_state.get("voice_commands", 0) + 1
                    self._dictate()
                elif self._extract_keyboard_key(text):
                    self.shared_state["voice_commands"] = self.shared_state.get("voice_commands", 0) + 1
                    self._handle_keyboard_command(text)
                elif self._is_click_command(text):
                    self.shared_state["voice_commands"] = self.shared_state.get("voice_commands", 0) + 1
                    self._handle_click_command()

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                logger.error(f"Could not request results from Speech Recognition service; {e}")
            except Exception as e:
                pass

    def _dictate(self):
        prev_tracking_paused = bool(self.shared_state.get("tracking_paused", False))
        self.shared_state["dictation_active"] = True
        self.shared_state["tracking_paused"] = True
        self.shared_state["continuous_scroll_active"] = None
        if self.audio_player:
            self.audio_player.play('dictation_start')
        logger.info("Dictation mode active. Tracking paused. Say 'transcribe done' or 'record done' to exit.")
        self.shared_state["voice_status"] = "DICTATING (Say 'transcribe done' or 'record done' to stop)"

        while self.running and self.shared_state["dictation_active"]:
            try:
                if self.shared_state.get("agent_active", False):
                    logger.info("Agent became active while dictating. Exiting dictation mode.")
                    self.shared_state["dictation_active"] = False
                    self.shared_state["voice_status"] = "DICTATION PAUSED (AGENT ACTIVE)"
                    if self.audio_player:
                        self.audio_player.play('dictation_stop')
                    break

                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=15)

                text = self.recognizer.recognize_google(audio).lower()
                logger.info(f"Dictated Chunk: {text}")

                if self._is_dictation_exit_phrase(text):
                    self.shared_state["voice_commands"] = self.shared_state.get("voice_commands", 0) + 1
                    final_text = self._strip_dictation_exit_phrase(text)
                    if final_text:
                        pyautogui.write(final_text + " ", interval=0.01)

                    logger.info("--> Exit phrase detected. Ending dictation...")
                    self.shared_state["dictation_active"] = False
                    self.shared_state["voice_status"] = "TRANSCRIBE DONE"
                    if self.audio_player:
                        self.audio_player.play('dictation_stop')
                    break

                if self._extract_keyboard_key(text):
                    self.shared_state["voice_commands"] = self.shared_state.get("voice_commands", 0) + 1
                    self._handle_keyboard_command(text)
                    continue

                if self._is_click_command(text):
                    self.shared_state["voice_commands"] = self.shared_state.get("voice_commands", 0) + 1
                    self._handle_click_command()
                    continue

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
        self.shared_state["tracking_paused"] = bool(self.shared_state.get("agent_active", False)) or prev_tracking_paused
        self.shared_state["voice_status"] = "Listening for voice commands..."

    def _normalize_phrase(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
        return " ".join(normalized.split())

    def _is_similar_word(self, word: str, targets) -> bool:
        for target in targets:
            if word == target:
                return True
            if difflib.SequenceMatcher(None, word, target).ratio() >= 0.75:
                return True
        return False

    def _is_dictation_exit_phrase(self, text: str) -> bool:
        normalized = self._normalize_phrase(text)
        if not normalized:
            return False

        strict_phrase = self._detect_dictation_exit_phrase(normalized)
        if strict_phrase:
            return True

        words = normalized.split()
        if len(words) > 4:
            return False

        transcribe_targets = {
            "transcribe",
            "transcript",
            "transcription",
            "dictation",
            "scribe",
            "record",
            "recording",
        }
        finish_words = {"done", "stop", "end", "finish", "off", "down", "dont"}

        has_transcribe_word = any(self._is_similar_word(word, transcribe_targets) for word in words)
        has_finish_word = any(word in finish_words for word in words)
        return has_transcribe_word and has_finish_word

    def _strip_dictation_exit_phrase(self, text: str) -> str:
        normalized = self._normalize_phrase(text)
        strict_phrase = self._detect_dictation_exit_phrase(normalized)
        if not strict_phrase:
            return ""
        if normalized == strict_phrase:
            return ""
        if normalized.startswith(f"{strict_phrase} "):
            return normalized[len(strict_phrase):].strip()
        if normalized.endswith(f" {strict_phrase}"):
            return normalized[: -len(strict_phrase)].strip()
        return ""

    def _detect_dictation_exit_phrase(self, normalized: str):
        words = normalized.split()
        # Avoid accidental self-trigger from long spoken prompts (e.g. TTS).
        if len(words) > 6:
            return None
        strict_phrases = [
            "transcribe done",
            "transcript done",
            "stop dictation",
            "stop transcribing",
            "record done",
            "stop recording",
            "done recording",
            "dictation done",
            "done dictation",
            "done transcribing",
            "transcription done",
            "stop transcription",
            "stop transcribe",
            "transcribe stop",
        ]
        for phrase in strict_phrases:
            if normalized == phrase:
                return phrase
            # Allow short forms like "please transcribe done" or "record done now".
            if len(words) <= 4 and (
                normalized.startswith(f"{phrase} ")
                or normalized.endswith(f" {phrase}")
            ):
                return phrase
        return None

    def _extract_keyboard_key(self, text: str):
        phrase = self._normalize_phrase(text)
        if not phrase:
            return None

        command_prefixes = ("press ", "hit ", "tap ")
        key_phrase = None
        for prefix in command_prefixes:
            if phrase.startswith(prefix):
                key_phrase = phrase[len(prefix):].strip()
                break
        if not key_phrase:
            return None

        if key_phrase.startswith("the "):
            key_phrase = key_phrase[4:].strip()
        if key_phrase.endswith(" key"):
            key_phrase = key_phrase[:-4].strip()
        for suffix in (" please", " now", " for me"):
            if key_phrase.endswith(suffix):
                key_phrase = key_phrase[: -len(suffix)].strip()
        return key_phrase or None

    def _is_click_command(self, text: str) -> bool:
        phrase = self._normalize_phrase(text)
        click_phrases = {
            "click now",
            "click it",
            "click this",
            "left click",
            "open it",
            "open this",
            "open that",
            "select this",
            "select it",
        }
        return phrase in click_phrases

    def _handle_click_command(self):
        target = self.shared_state.get("magnet_snap_target")
        clicked = False
        try:
            if target:
                tx, ty = int(target[0]), int(target[1])
                pyautogui.click(tx, ty)
                self.shared_state["currently_doing"] = f"VOICE CLICK AT {tx}, {ty}"
                clicked = True
            else:
                pyautogui.click()
                self.shared_state["currently_doing"] = "VOICE CLICK"
                clicked = True
        except Exception as e:
            logger.error(f"Could not click via voice command: {e}")

        if clicked:
            self.shared_state["clicks_saved"] = self.shared_state.get("clicks_saved", 0) + 1
            self.shared_state["voice_status"] = "Clicked target"
            if self.audio_player:
                self.audio_player.play('click')

    def _handle_sniper_command(self, text: str) -> bool:
        phrase = (text or "").strip().lower()
        if not phrase:
            return False

        on_phrases = [
            "sniper mode on",
            "enable sniper mode",
            "sniper on",
            "precision mode on",
            "precision on",
            "focus mode on",
            "focus on"
        ]
        off_phrases = [
            "sniper mode off",
            "disable sniper mode",
            "sniper off",
            "precision mode off",
            "precision off",
            "focus mode off",
            "focus off"
        ]
        toggle_phrases = [
            "sniper mode",
            "precision mode",
            "focus mode",
        ]

        enable = None
        if any(p in phrase for p in on_phrases):
            enable = True
        elif any(p in phrase for p in off_phrases):
            enable = False
        elif any(p in phrase for p in toggle_phrases):
            enable = not bool(self.shared_state.get("sniper_mode_active", False))
        else:
            return False

        self.shared_state["sniper_mode_active"] = enable
        self.shared_state["magnet_snap_target"] = None
        self.shared_state["magnet_target_bbox"] = None
        self.shared_state["sniper_candidate_index"] = 0
        self.shared_state["sniper_candidate_count"] = 0

        if enable:
            self.shared_state["currently_doing"] = "SNIPER MODE ACTIVE"
            self.shared_state["voice_status"] = "SNIPER MODE ON"
            if self.audio_player:
                self.audio_player.play('lock_engage')
        else:
            self.shared_state["currently_doing"] = "AWAITING COMMAND"
            self.shared_state["voice_status"] = "SNIPER MODE OFF"
            if self.audio_player:
                self.audio_player.play('lock_release')
        return True

    def _handle_keyboard_command(self, text):
        key = self._extract_keyboard_key(text)
        if not key:
            return
        logger.info(f"--> Keyboard command detected: press '{key}'")
        self.shared_state["voice_status"] = f"Pressed: {key}"

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
            "page up": "pageup",
            "page down": "pagedown",
            "home": "home",
            "end": "end",
            "insert": "insert",
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
