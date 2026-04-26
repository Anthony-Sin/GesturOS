import os
import io
import time
import base64
import queue
import threading
from dotenv import load_dotenv

import mss
import pyautogui
import ast
import pyperclip
import platform
import speech_recognition as sr
from PIL import Image

from google import genai
from google.genai import types
from google.genai.types import Content, Part
from tools.interfaces import BaseBlindAgent
from tools.agent_engine.intent_router import IntentRouter

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

        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.8

        self.sct = mss.mss()
        self.screen_width, self.screen_height = pyautogui.size()

        self.running = False
        self.conversation_history = []
        self.intent_router = IntentRouter(self)

    def speak(self, text):
        if self.audio_player:
            self.audio_player.speak(text)
        else:
            print(f"[Agent Says]: {text}")

    def start(self):
        self.running = True

        if self.microphone:
            print("Adjusting microphone for ambient noise...")
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=2)
            except Exception as e:
                print(f"Mic init error: {e}")

        self.speak("AI Agent ready. Say 'Agent' followed by a command to begin.")

        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self.running = False

    def _capture_screen_bytes(self) -> bytes:
        sct_img = self.sct.grab(self.sct.monitors[1])
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
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
                    command = text.replace("agent", "").strip()

                    if len(command) > 2:
                        self._route_intent(command)
                    else:
                        self.speak("I am listening. Please give a command.")
                        with self.microphone as source:
                            audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)
                        command = self.recognizer.recognize_google(audio).lower()
                        self._route_intent(command)

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"Speech Service error: {e}")
            except Exception as e:
                print(f"Agent Loop error: {e}")

    def _route_intent(self, command):
        print(f"[Intent Router] Processing: '{command}'")

        if self.intent_router.process(command):
            return

        if self.client:
            flash_prompt = f"""
You are a voice command translator. The user said: "{command}"
If this command is a simple OS action (like scrolling, pressing a key, typing, going back), output ONLY literal Python code using the `pyautogui` library to execute it. Do not include markdown formatting, backticks, or explanations. Just the raw Python code.
If the command requires seeing the screen to know where to click or what to interact with (e.g., "click the login button", "find my email", "open google chrome"), you MUST output exactly the word "FALLBACK" and nothing else.
"""
            try:
                flash_model = self.config.get("LLM_FLASH_MODEL", "gemini-1.5-flash")
                response = self.client.models.generate_content(
                    model=flash_model,
                    contents=flash_prompt
                )
                output = response.text.strip()

                if output != "FALLBACK" and "pyautogui." in output:
                    print(f"[Intent Router] Attempting to securely execute Flash Code: {output}")
                    try:
                        tree = ast.parse(output)
                        for node in tree.body:
                            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                                func = node.value.func
                                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == 'pyautogui':
                                    method_name = func.attr
                                    args = []
                                    for arg in node.value.args:
                                        if isinstance(arg, ast.Constant):
                                            args.append(arg.value)
                                        elif isinstance(arg, ast.Str):
                                            args.append(arg.s)
                                        elif isinstance(arg, ast.Num):
                                            args.append(arg.n)
                                        else:
                                            raise ValueError("Unsupported argument type generated by LLM.")

                                    if hasattr(pyautogui, method_name):
                                        print(f" -> Executing: pyautogui.{method_name}({args})")
                                        getattr(pyautogui, method_name)(*args)
                                    else:
                                        print(f" -> Denied: {method_name} is not a valid pyautogui function.")
                                else:
                                     print(" -> Denied: Only pyautogui calls are allowed.")
                        return
                    except Exception as e:
                        print(f"Failed to securely execute Flash code: {e}. Falling back.")
                else:
                    print(f"[Intent Router] Flash returned FALLBACK for command: '{command}'")
            except Exception as e:
                print(f"Flash Routing Error: {e}. Falling back.")

        print("[Intent Router] Routing to Full Gemini 2.5 Agent...")
        self._handle_agent_loop(command)

    def _denormalize_x(self, x: int) -> int:
        return int(x / 1000 * self.screen_width)

    def _denormalize_y(self, y: int) -> int:
        return int(y / 1000 * self.screen_height)

    def _wait_for_cancellation(self, duration=1.5):
        """Waits for cancellation signal. Returns True if cancelled, False otherwise."""
        start_time = time.time()
        self.shared_state["cancel_action"] = False
        while time.time() - start_time < duration:
            if self.shared_state.get("cancel_action"):
                return True
            time.sleep(0.05)
        return False

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
                if fname in ["click", "type"]:
                    actual_x = self._denormalize_x(args["x"])
                    actual_y = self._denormalize_y(args["y"])

                    # Draw Red Bounding Box on Target (40x40 box centered at click)
                    box_size = 40
                    bbox_x = max(0, actual_x - box_size // 2)
                    bbox_y = max(0, actual_y - box_size // 2)
                    self.shared_state["agent_target_bbox"] = (bbox_x, bbox_y, box_size, box_size)

                    self.shared_state["currently_doing"] = f"TARGETING {fname.upper()} IN 1.5s..."

                    # Wait for 1.5 seconds to allow voice cancellation
                    if self._wait_for_cancellation(1.5):
                        print("Action cancelled by user!")
                        self.shared_state["currently_doing"] = "ACTION CANCELLED"
                        self.shared_state["agent_target_bbox"] = None
                        action_result = {"error": "User cancelled the action."}
                        results.append((fname, action_result))
                        continue # Skip execution

                    # Clear box just before action
                    self.shared_state["agent_target_bbox"] = None

                    if fname == "click":
                        self.shared_state["currently_doing"] = f"CLICKING AT {actual_x}, {actual_y}"
                        pyautogui.click(actual_x, actual_y)
                    elif fname == "type":
                        self.shared_state["currently_doing"] = f"TYPING: {args.get('text', '')[:10]}..."
                        text = args["text"]
                        press_enter = args.get("press_enter", False)
                        pyautogui.click(actual_x, actual_y)
                        time.sleep(0.1)
                        pyautogui.write(text, interval=0.01)
                        if press_enter:
                            pyautogui.press('enter')

                elif fname == "scroll":
                    self.shared_state["currently_doing"] = f"SCROLLING {args.get('direction', 'down').upper()}"
                    amount = args.get("amount", 1)
                    direction = args.get("direction", "down")
                    if direction == "down":
                        pyautogui.scroll(-300 * amount)
                    else:
                        pyautogui.scroll(300 * amount)
                else:
                    self.shared_state["currently_doing"] = f"EXECUTING {fname.upper()}"
                    print(f"Warning: Unimplemented function {fname}")
                    action_result = {"error": f"Function {fname} not supported by this OS layer yet."}

                time.sleep(1.5)
            except Exception as e:
                print(f"Error executing {fname}: {e}")
                action_result = {"error": str(e)}

            results.append((fname, action_result))

        return results

    def _get_function_responses(self, results):
        function_responses = []
        for name, result in results:
            response_data = {}
            response_data.update(result)
            function_responses.append(
                types.FunctionResponse(
                    name=name,
                    response=response_data
                )
            )
        return function_responses

    def _handle_agent_loop(self, user_command):
        self.speak(f"Okay, taking over. I will try to: {user_command}")
        self.shared_state["currently_doing"] = "PLANNING AGENT ACTIONS..."

        if not self.client:
            self.speak("API key missing.")
            self.shared_state["currently_doing"] = "ERROR: API KEY MISSING"
            return

        config = types.GenerateContentConfig(
            system_instruction="You are a helpful, autonomous UI agent. Use the screen context to execute the user's tasks. Do not output require_confirmation unless executing a highly destructive action (like deleting a file or sending an email). Keep text output extremely brief.",
            tools=[types.Tool(computer_use=types.ComputerUse(
                environment=types.Environment.ENVIRONMENT_MAC
            ))],
        )

        initial_screenshot = self._capture_screen_bytes()
        contents = [
            Content(role="user", parts=[
                Part(text=user_command),
                Part.from_bytes(data=initial_screenshot, mime_type='image/png')
            ])
        ]

        turn_limit = 10
        for i in range(turn_limit):
            print(f"\n--- Agent Turn {i+1} ---")

            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=0.5, phrase_time_limit=2)
                text = self.recognizer.recognize_google(audio).lower()
                if "agent stop" in text or "stop agent" in text or "cancel" in text:
                    self.speak("Stopping the agent.")
                    self.shared_state["currently_doing"] = "AGENT STOPPED BY USER"
                    break
            except Exception:
                pass

            try:
                agent_model = self.config.get("LLM_AGENT_MODEL", "gemini-2.5-computer-use-preview-10-2025")
                response = self.client.models.generate_content(
                    model=agent_model,
                    contents=contents,
                    config=config,
                )

                candidate = response.candidates[0]
                contents.append(candidate.content)

                has_function_calls = any(part.function_call for part in candidate.content.parts)
                if not has_function_calls:
                    final_text = " ".join([part.text for part in candidate.content.parts if part.text])
                    print("Agent finished:", final_text)
                    self.shared_state["currently_doing"] = "TASK COMPLETE"
                    self.speak("Task complete.")
                    break

                results = self._execute_function_calls(candidate)

                new_screenshot = self._capture_screen_bytes()
                function_responses = self._get_function_responses(results)

                parts = [Part.from_function_response(name=fr.name, response=fr.response) for fr in function_responses]
                parts.append(Part.from_bytes(data=new_screenshot, mime_type='image/png'))

                contents.append(Content(role="user", parts=parts))
            except Exception as e:
                print(f"Agent turn failed: {e}")
                self.speak("I encountered an issue while trying to complete the task.")
                self.shared_state["currently_doing"] = "ERROR: TURN FAILED"
                break
        else:
             self.speak("Turn limit reached.")
             self.shared_state["currently_doing"] = "ERROR: TURN LIMIT REACHED"
