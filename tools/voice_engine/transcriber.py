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
                state["voice_status"] = "Listening for 'transcript now'..."
                with self.microphone as source:
                    # Listen in short chunks
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=5)

                # Use Google Web Speech API (free, doesn't require API key for light usage)
                text = self.recognizer.recognize_google(audio).lower()
                print(f"[Voice Heard]: {text}")

                # Check for trigger phrase
                if "transcript now" in text or "transcribe now" in text:
                    print("--> Trigger activated! Entering dictation mode...")
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
        # We are now in dictation mode. Listen for one long phrase and type it out.
        print("Dictation mode active. Please speak...")
        state["voice_status"] = "DICTATING... (Speak Now)"
        try:
            with self.microphone as source:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)

            state["voice_status"] = "Processing Audio..."
            text = self.recognizer.recognize_google(audio)
            print(f"Dictated: {text}")

            state["voice_status"] = "Typing Text..."
            # Type it out via PyAutoGUI where the cursor currently is
            pyautogui.write(text, interval=0.01)

            print("Dictation finished. Returning to background listening.")

        except sr.WaitTimeoutError:
            print("Dictation timed out (no speech detected).")
        except sr.UnknownValueError:
            print("Could not understand dictation.")
        except sr.RequestError as e:
            print(f"Service error during dictation: {e}")
        finally:
            state["voice_status"] = "Listening for 'transcript now'..."
