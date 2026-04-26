import os
import io
import time
import base64
import queue
import threading
from dotenv import load_dotenv

import mss
import pyautogui
import pyttsx3
import speech_recognition as sr
from PIL import Image

from google import genai
from google.genai import types
from google.genai.types import Content, Part
from tools.interfaces import BaseBlindAgent

load_dotenv()

class GeminiDesktopAgent(BaseBlindAgent):
    def __init__(self, config: dict, shared_state: dict, audio_player):
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            print("WARNING: GEMINI_API_KEY not found in .env. Agent will not work.")

        try:
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"Failed to init Gemini Client: {e}")
            self.client = None

        self.recognizer = sr.Recognizer()
        try:
            self.microphone = sr.Microphone()
        except OSError:
            print("WARNING: No microphone found. Agent cannot hear commands.")
            self.microphone = None

        # Configure recognizer for responsiveness
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.8

        # Init Text-to-Speech
        try:
            self.tts = pyttsx3.init()
            self.tts.setProperty('rate', 150) # Speaking speed
        except Exception as e:
            print(f"Failed to init TTS: {e}")
            self.tts = None

        self.sct = mss.mss()
        self.screen_width, self.screen_height = pyautogui.size()

        self.running = False
        self.conversation_history = []

    def speak(self, text):
        print(f"[Agent Says]: {text}")
        if self.tts:
            self.tts.say(text)
            self.tts.runAndWait()

    def start(self):
        self.running = True

        # Adjust mic
        if self.microphone:
            print("Adjusting microphone for ambient noise...")
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=2)
            except Exception as e:
                print(f"Mic init error: {e}")

        self.speak("Blind Accessibility Mode activated. Say 'Agent' to give a command, or say 'Agent describe my screen'.")

        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self.running = False

    def _capture_screen_bytes(self) -> bytes:
        # Capture full screen
        sct_img = self.sct.grab(self.sct.monitors[1])
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        # Gemini works best around 1440x900. Let's resize if massive.
        img.thumbnail((1440, 900), Image.Resampling.LANCZOS)

        byte_stream = io.BytesIO()
        img.save(byte_stream, format='PNG')
        return byte_stream.getvalue()

    def _run_loop(self):
        if not self.microphone:
            return

        while self.running:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=10)

                text = self.recognizer.recognize_google(audio).lower()
                print(f"[Heard]: {text}")

                if "agent" in text:
                    # Strip wake word
                    command = text.replace("agent", "").strip()

                    if "describe" in command and ("screen" in command or "page" in command):
                        self._handle_describe()
                    elif len(command) > 2:
                        self._handle_agent_loop(command)
                    else:
                        self.speak("I am listening. Please give a command.")
                        # Listen again immediately for the actual command
                        with self.microphone as source:
                            audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)
                        command = self.recognizer.recognize_google(audio).lower()
                        self._handle_agent_loop(command)

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"Speech Service error: {e}")
            except Exception as e:
                print(f"Agent Loop error: {e}")

    def _handle_describe(self):
        self.speak("Taking a look...")
        if not self.client:
            self.speak("API key missing. Cannot process image.")
            return

        screenshot_bytes = self._capture_screen_bytes()

        prompt = "Describe what is currently on the computer screen. Read out any important text, tell me what applications are open, and describe the general layout so a blind person can understand the context. Keep it concise but descriptive."

        try:
            response = self.client.models.generate_content(
                model='gemini-1.5-flash',
                contents=[
                    prompt,
                    types.Part.from_bytes(data=screenshot_bytes, mime_type='image/png')
                ]
            )
            self.speak(response.text)
        except Exception as e:
            print(f"Gemini Describe Error: {e}")
            self.speak("Sorry, I encountered an error while trying to describe the screen.")

    # --- Agent Loop Translation ---
    def _denormalize_x(self, x: int) -> int:
        return int(x / 1000 * self.screen_width)

    def _denormalize_y(self, y: int) -> int:
        return int(y / 1000 * self.screen_height)

    def _execute_function_calls(self, candidate) -> list:
        results = []
        function_calls = []
        for part in candidate.content.parts:
            if part.function_call:
                function_calls.append(part.function_call)

        for function_call in function_calls:
            action_result = {}
            fname = function_call.name
            args = function_call.args
            print(f"  -> Agent Executing: {fname} with args: {args}")

            try:
                if fname == "open_web_browser":
                    # PyAutoGUI can't directly "open a browser" reliably across OSs.
                    # We can use hotkeys (Win+S, type Chrome) but it's brittle.
                    # Let's simulate a click on the taskbar if args exist, or just press Win key.
                    print("  -> Ignoring open_web_browser. Please use PyAutoGUI to navigate to the browser.")
                    action_result = {"status": "Browser command received, but agent must manually click icon."}

                elif fname == "click_at":
                    actual_x = self._denormalize_x(args["x"])
                    actual_y = self._denormalize_y(args["y"])
                    pyautogui.click(actual_x, actual_y)

                elif fname == "type_text_at":
                    actual_x = self._denormalize_x(args["x"])
                    actual_y = self._denormalize_y(args["y"])
                    text = args["text"]
                    press_enter = args.get("press_enter", False)

                    pyautogui.click(actual_x, actual_y)
                    # Clear simple (Ctrl+A, Backspace)
                    pyautogui.hotkey('ctrl', 'a')
                    pyautogui.press('backspace')
                    pyautogui.write(text, interval=0.01)
                    if press_enter:
                        pyautogui.press('enter')
                else:
                    print(f"Warning: Unimplemented function {fname}")
                    action_result = {"error": f"Function {fname} not supported by this OS layer yet."}

                time.sleep(1.5) # Wait for UI to render

            except Exception as e:
                print(f"Error executing {fname}: {e}")
                action_result = {"error": str(e)}

            results.append((fname, action_result))

        return results

    def _get_function_responses(self, results):
        screenshot_bytes = self._capture_screen_bytes()
        function_responses = []

        for name, result in results:
            # We don't have URLs in OS-level control easily, just send empty
            response_data = {"url": ""}
            response_data.update(result)
            function_responses.append(
                types.FunctionResponse(
                    name=name,
                    response=response_data,
                    parts=[types.FunctionResponsePart(
                            inline_data=types.FunctionResponseBlob(
                                mime_type="image/png",
                                data=screenshot_bytes))
                    ]
                )
            )
        return function_responses

    def _handle_agent_loop(self, user_command):
        self.speak(f"Okay, I will try to: {user_command}")
        if not self.client:
            self.speak("API key missing.")
            return

        config = types.GenerateContentConfig(
            tools=[types.Tool(computer_use=types.ComputerUse(
                environment=types.Environment.ENVIRONMENT_BROWSER
            ))],
        )

        initial_screenshot = self._capture_screen_bytes()

        # We start fresh conversation history for each major task
        contents = [
            Content(role="user", parts=[
                Part(text=user_command),
                Part.from_bytes(data=initial_screenshot, mime_type='image/png')
            ])
        ]

        turn_limit = 5
        for i in range(turn_limit):
            print(f"\n--- Agent Turn {i+1} ---")
            try:
                response = self.client.models.generate_content(
                    model='gemini-2.5-computer-use-preview-10-2025',
                    contents=contents,
                    config=config,
                )

                candidate = response.candidates[0]
                contents.append(candidate.content)

                has_function_calls = any(part.function_call for part in candidate.content.parts)
                if not has_function_calls:
                    text_response = " ".join([part.text for part in candidate.content.parts if part.text])
                    print("Agent finished:", text_response)
                    self.speak(text_response)
                    break

                # Execute actions
                results = self._execute_function_calls(candidate)

                # Capture state
                function_responses = self._get_function_responses(results)

                contents.append(
                    Content(role="user", parts=[Part(function_response=fr) for fr in function_responses])
                )
            except Exception as e:
                print(f"Agent turn failed: {e}")
                self.speak("I encountered an issue while trying to complete the task.")
                break

        self.speak("Task complete.")
