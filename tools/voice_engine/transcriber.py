import speech_recognition as sr
import threading
import pyautogui
from shared_state import state

class VoiceTranscriber:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.running = False

        # Adjust for ambient noise on startup
        with self.microphone as source:
            print("Adjusting microphone for ambient noise...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            print("Microphone ready.")

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        print("Voice Transcriber started. Listening for 'transcript now'...")
        return thread

    def stop(self):
        self.running = False

    def _run_loop(self):
        while self.running:
            try:
                state["voice_status"] = "Listening for 'transcribe me'..."
                with self.microphone as source:
                    # Listen in short chunks
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=5)

                # Use Google Web Speech API (free, doesn't require API key for light usage)
                text = self.recognizer.recognize_google(audio).lower()
                print(f"[Voice Heard]: {text}")

                # Check for trigger phrase
                if "transcribe me" in text:
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
        print("Dictation mode active. Tracking paused. Say 'transcribe done' to exit.")
        state["voice_status"] = "DICTATING (Say 'transcribe done' to stop)"

        while self.running and state["dictation_active"]:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=10)

                text = self.recognizer.recognize_google(audio).lower()
                print(f"Dictated Chunk: {text}")

                if "transcribe done" in text:
                    # Write everything before the exit phrase
                    final_text = text.replace("transcribe done", "").strip()
                    if final_text:
                        pyautogui.write(final_text + " ", interval=0.01)

                    print("--> Exit phrase detected. Ending dictation...")
                    state["dictation_active"] = False
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
