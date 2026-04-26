import os
import io
import time
import threading
import logging
import platform
from dotenv import load_dotenv

import mss
import pyautogui
import speech_recognition as sr
from PIL import Image

from google import genai
from google.genai import types
from google.genai.types import Content, Part
from tools.interfaces import BaseBlindAgent

load_dotenv()

logger = logging.getLogger(__name__)

class GeminiDesktopAgent(BaseBlindAgent):
    def __init__(self, config: dict, shared_state: dict, audio_player, microphone=None):
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not found in .env. Agent will not work.")
            self.client = None
        else:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.exception(f"Failed to init Gemini Client: {e}")
                self.client = None

        self.recognizer = sr.Recognizer()
        try:
            if microphone is not None:
                self.microphone = microphone
            else:
                try:
                    self.microphone = sr.Microphone()
                except OSError:
                    logger.warning("No microphone found. Agent cannot hear commands.")
                    self.microphone = None

        except OSError:
            logger.warning("No microphone found. Agent cannot hear commands.")
            self.microphone = None

        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.8

        self.screen_width, self.screen_height = pyautogui.size()
        self.router_max_output_tokens = int(self.config.get("LLM_ROUTER_MAX_OUTPUT_TOKENS", 96))
        self.agent_max_output_tokens = int(self.config.get("AGENT_MAX_OUTPUT_TOKENS", 256))
        self.agent_max_turns = max(1, int(self.config.get("AGENT_MAX_TURNS", 6)))
        self.agent_max_actions_per_task = max(1, int(self.config.get("AGENT_MAX_ACTIONS_PER_TASK", 18)))
        self.agent_max_tool_errors = max(1, int(self.config.get("AGENT_MAX_TOOL_ERRORS", 4)))
        self.agent_max_history_items = max(3, int(self.config.get("AGENT_MAX_HISTORY_ITEMS", 8)))
        self.agent_screenshot_max_w = max(640, int(self.config.get("AGENT_SCREENSHOT_MAX_W", 1280)))
        self.agent_screenshot_max_h = max(360, int(self.config.get("AGENT_SCREENSHOT_MAX_H", 800)))

        self.running = False
        self.conversation_history = []

    def speak(self, text):
        if self.audio_player:
            self.audio_player.speak(text)
        else:
            logger.info(f"[Agent Says]: {text}")

    def start(self):
        self.running = True

        if self.microphone:
            logger.info("Adjusting microphone for ambient noise...")
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=2)
            except Exception as e:
                logger.error(f"Mic init error: {e}")

        self.speak("AI Agent ready. Say 'Agent' followed by a command to begin.")

        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self.running = False

    def _capture_screen_bytes(self) -> bytes:
        # Create mss in the same thread that captures to avoid thread-context issues.
        with mss.mss() as sct:
            monitor_index = 1 if len(sct.monitors) > 1 else 0
            sct_img = sct.grab(sct.monitors[monitor_index])

        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        img.thumbnail((self.agent_screenshot_max_w, self.agent_screenshot_max_h), Image.Resampling.LANCZOS)
        byte_stream = io.BytesIO()
        img.save(byte_stream, format='PNG')
        return byte_stream.getvalue()

    def _resolve_computer_use_environment(self):
        os_name = platform.system().lower()
        env_windows = getattr(types.Environment, "ENVIRONMENT_WINDOWS", None)
        env_mac = getattr(types.Environment, "ENVIRONMENT_MAC", None)
        env_linux = getattr(types.Environment, "ENVIRONMENT_LINUX", None)
        fallback_env = env_windows or env_mac or env_linux
        if fallback_env is None:
            raise RuntimeError("No supported computer-use environment enum found in google.genai.types.Environment.")

        if "windows" in os_name:
            return env_windows or fallback_env
        if "darwin" in os_name or "mac" in os_name:
            return env_mac or fallback_env
        return env_linux or fallback_env

    def _extract_function_calls(self, candidate):
        if not candidate or not getattr(candidate, "content", None):
            return []
        parts = getattr(candidate.content, "parts", None) or []
        return [part.function_call for part in parts if getattr(part, "function_call", None)]


    def _run_loop(self):
        if not self.microphone:
            return

        while self.running:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=10)

                text = self.recognizer.recognize_google(audio).lower()
                logger.info(f"[Heard]: {text}")

                # Strict keyword gateway
                if "agent" in text:
                    # Strip wake word to get the actual command
                    command = text.split("agent", 1)[-1].strip()

                    if len(command) > 2:
                        self._route_intent(command)
                    else:
                        self.speak("I am listening. Please give a command.")
                        with self.microphone as source:
                            audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)
                        command = self.recognizer.recognize_google(audio).lower()
                        if command:
                            self._route_intent(command)
                else:
                    # Silently drop non-addressed speech
                    pass

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                logger.error(f"Speech Service error: {e}")
            except Exception as e:
                logger.error(f"Agent Loop error: {e}")


    def _route_intent(self, command):
        logger.info(f"[Tier 2 Router] Processing: '{command}'")

        if not self.client:
            logger.warning("No Gemini client available.")
            return

        flash_prompt = f"""
You are the rapid-response router for an accessibility tool.
Your job is to map the user's voice command to one of your available tools.
Do not attempt to write code.
- If a task requires complex visual navigation or multiple steps (e.g., clicking specific icons, finding text on screen), use `escalate_to_agent`.
- Even though the user said the wake word 'Agent', if the rest of the command is just chatting or ambiguous, use `ignore_non_command_speech`.

User command: "{command}"
"""

        flash_model = self.config.get("LLM_FLASH_MODEL", "gemini-2.5-flash-lite")

        # Define the tools
        tool_shortcut = types.FunctionDeclaration(
            name="execute_keyboard_shortcut",
            description="Executes a keyboard shortcut.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "keys": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="A list of keys to press together (e.g. ['ctrl', 'c'], ['enter'], ['win', 'd'])"
                    )
                },
                required=["keys"]
            )
        )

        tool_type = types.FunctionDeclaration(
            name="type_string",
            description="Types out a string of text like a keyboard.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(
                        type=types.Type.STRING,
                        description="The text to type out."
                    )
                },
                required=["text"]
            )
        )

        tool_escalate = types.FunctionDeclaration(
            name="escalate_to_agent",
            description="Escalates the task to a complex visual autonomous agent.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "task_description": types.Schema(
                        type=types.Type.STRING,
                        description="A description of the complex task to perform."
                    )
                },
                required=["task_description"]
            )
        )

        tool_ignore = types.FunctionDeclaration(
            name="ignore_non_command_speech",
            description="Ignores speech that is not a clear command.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "reason": types.Schema(
                        type=types.Type.STRING,
                        description="The reason for ignoring the speech."
                    )
                },
                required=["reason"]
            )
        )

        tool = types.Tool(function_declarations=[tool_shortcut, tool_type, tool_escalate, tool_ignore])

        try:
            response = self.client.models.generate_content(
                model=flash_model,
                contents=flash_prompt,
                config=types.GenerateContentConfig(
                    tools=[tool],
                    temperature=0.0,
                    max_output_tokens=self.router_max_output_tokens,
                )
            )

            # Find the first function call in any returned part.
            if response.candidates and response.candidates[0].content.parts:
                part_with_call = next(
                    (
                        p
                        for p in response.candidates[0].content.parts
                        if getattr(p, "function_call", None) is not None
                    ),
                    None,
                )
                if part_with_call and part_with_call.function_call:
                    func_name = part_with_call.function_call.name
                    args = dict(part_with_call.function_call.args or {})

                    if func_name == "execute_keyboard_shortcut":
                        keys = args.get("keys", [])
                        if isinstance(keys, list) and keys:
                            self._tool_execute_keyboard_shortcut(keys)
                        else:
                            self._tool_ignore_non_command_speech("Router returned invalid shortcut args.")
                    elif func_name == "type_string":
                        text_to_type = str(args.get("text", "")).strip()
                        if text_to_type:
                            self._tool_type_string(text_to_type)
                        else:
                            self._tool_ignore_non_command_speech("Router returned empty text for typing.")
                    elif func_name == "escalate_to_agent":
                        task_description = str(args.get("task_description", "")).strip()
                        if task_description:
                            self._tool_escalate_to_agent(task_description)
                        else:
                            self._tool_ignore_non_command_speech("Router returned empty task description.")
                    elif func_name == "ignore_non_command_speech":
                        self._tool_ignore_non_command_speech(str(args.get("reason", "No reason provided.")))
                    else:
                        logger.warning(f"Unknown tool called by Flash: {func_name}")
                        self._tool_ignore_non_command_speech("Router called an unsupported tool.")
                else:
                    # Flash output raw text instead of a tool
                    first_part_text = response.candidates[0].content.parts[0].text
                    logger.warning(f"[Tier 2 Router] Flash ignored tools and output text: {first_part_text}")
                    self._tool_ignore_non_command_speech("LLM returned raw text instead of tool call.")
            else:
                 logger.error("[Tier 2 Router] Error: Empty response from Flash.")

        except Exception as e:
            logger.error(f"Flash Routing Error: {e}")

    def _denormalize_x(self, x: int) -> int:
        try:
            x_val = float(x)
        except Exception:
            x_val = 500.0
        actual = int(x_val / 1000.0 * self.screen_width)
        return max(0, min(self.screen_width - 1, actual))

    def _denormalize_y(self, y: int) -> int:
        try:
            y_val = float(y)
        except Exception:
            y_val = 500.0
        actual = int(y_val / 1000.0 * self.screen_height)
        return max(0, min(self.screen_height - 1, actual))

    def _wait_for_cancellation(self, duration=1.5):
        """Waits for cancellation signal. Returns True if cancelled, False otherwise."""
        start_time = time.time()
        self.shared_state["cancel_action"] = False
        while time.time() - start_time < duration:
            if self.shared_state.get("cancel_action"):
                return True
            time.sleep(0.05)
        return False

    def _execute_function_calls(self, function_calls) -> list:
        results = []

        for function_call in function_calls:
            action_result = {"ok": True}
            fname = getattr(function_call, "name", "unknown_action")
            args = dict(getattr(function_call, "args", {}) or {})
            logger.info(f"  -> Agent Executing: {fname} with args: {args}")

            try:
                if fname in ["click", "type"]:
                    if "x" not in args or "y" not in args:
                        raise ValueError(f"Missing x/y coordinates for {fname}.")

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
                        logger.info("Action cancelled by user!")
                        self.shared_state["currently_doing"] = "ACTION CANCELLED"
                        self.shared_state["agent_target_bbox"] = None
                        action_result = {"ok": False, "error": "User cancelled the action."}
                        results.append((fname, action_result))
                        continue # Skip execution

                    # Clear box just before action
                    self.shared_state["agent_target_bbox"] = None

                    if fname == "click":
                        self.shared_state["currently_doing"] = f"CLICKING AT {actual_x}, {actual_y}"
                        pyautogui.click(actual_x, actual_y)
                        self.shared_state["clicks_saved"] = self.shared_state.get("clicks_saved", 0) + 1
                    elif fname == "type":
                        text = str(args.get("text", ""))
                        if not text:
                            raise ValueError("Type action did not include text.")
                        # Keep runaway prompts from typing massive payloads by mistake.
                        text = text[:2000]
                        self.shared_state["currently_doing"] = f"TYPING: {text[:10]}..."
                        press_enter = bool(args.get("press_enter", False))
                        pyautogui.click(actual_x, actual_y)
                        self.shared_state["clicks_saved"] = self.shared_state.get("clicks_saved", 0) + 1
                        time.sleep(0.1)
                        pyautogui.write(text, interval=0.01)
                        if press_enter:
                            pyautogui.press('enter')

                elif fname == "scroll":
                    self.shared_state["currently_doing"] = f"SCROLLING {args.get('direction', 'down').upper()}"
                    try:
                        amount = int(args.get("amount", 1))
                    except Exception:
                        amount = 1
                    amount = max(1, min(8, amount))
                    direction = str(args.get("direction", "down")).lower()
                    if direction == "down":
                        pyautogui.scroll(-300 * amount)
                    else:
                        pyautogui.scroll(300 * amount)
                else:
                    self.shared_state["currently_doing"] = f"EXECUTING {fname.upper()}"
                    logger.warning(f"Unimplemented function {fname}")
                    action_result = {"ok": False, "error": f"Function {fname} not supported by this OS layer yet."}

                time.sleep(1.5)
            except Exception as e:
                logger.error(f"Error executing {fname}: {e}")
                action_result = {"ok": False, "error": str(e)}

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
            logger.warning("Agent disabled due to missing API key.")
            self.speak("API key missing.")
            self.shared_state["currently_doing"] = "ERROR: API KEY MISSING"
            return

        agent_model = self.config.get("LLM_AGENT_MODEL", "gemini-2.5-computer-use-preview-10-2025")
        agent_environment = self._resolve_computer_use_environment()
        config = types.GenerateContentConfig(
            system_instruction="You are a helpful, autonomous UI agent. Use the screen context to execute the user's tasks. Do not output require_confirmation unless executing a highly destructive action (like deleting a file or sending an email). Keep text output extremely brief.",
            tools=[types.Tool(computer_use=types.ComputerUse(
                environment=agent_environment
            ))],
            temperature=0.0,
            max_output_tokens=self.agent_max_output_tokens,
        )

        initial_screenshot = self._capture_screen_bytes()
        contents = [
            Content(role="user", parts=[
                Part(text=user_command),
                Part.from_bytes(data=initial_screenshot, mime_type='image/png')
            ])
        ]

        turn_limit = self.agent_max_turns
        total_actions = 0
        total_tool_errors = 0
        for i in range(turn_limit):
            logger.info(f"\n--- Agent Turn {i+1} ---")

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
                response = self.client.models.generate_content(
                    model=agent_model,
                    contents=contents,
                    config=config,
                )

                if not response.candidates:
                    raise RuntimeError("No candidate returned by Gemini.")
                candidate = response.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    raise RuntimeError("Candidate content was empty.")
                contents.append(candidate.content)

                function_calls = self._extract_function_calls(candidate)
                has_function_calls = bool(function_calls)
                if not has_function_calls:
                    final_text = " ".join([part.text for part in candidate.content.parts if part.text])
                    logger.info(f"Agent finished: {final_text}")
                    self.shared_state["currently_doing"] = "TASK COMPLETE"
                    self.speak("Task complete.")
                    break

                remaining_actions = self.agent_max_actions_per_task - total_actions
                if remaining_actions <= 0:
                    self.speak("Stopping to avoid excessive automation steps.")
                    self.shared_state["currently_doing"] = "STOPPED: ACTION BUDGET REACHED"
                    break

                if len(function_calls) > remaining_actions:
                    logger.warning(
                        f"Agent requested {len(function_calls)} actions but only {remaining_actions} are allowed."
                    )
                    function_calls = function_calls[:remaining_actions]

                results = self._execute_function_calls(function_calls)
                total_actions += len(results)
                total_tool_errors += sum(1 for _, result in results if result.get("error"))
                if total_tool_errors >= self.agent_max_tool_errors:
                    self.speak("Stopping because too many tool errors occurred.")
                    self.shared_state["currently_doing"] = "STOPPED: TOO MANY TOOL ERRORS"
                    break

                new_screenshot = self._capture_screen_bytes()
                function_responses = self._get_function_responses(results)

                parts = [Part.from_function_response(name=fr.name, response=fr.response) for fr in function_responses]
                parts.append(Part.from_bytes(data=new_screenshot, mime_type='image/png'))

                contents.append(Content(role="user", parts=parts))
                if len(contents) > self.agent_max_history_items:
                    contents = [contents[0]] + contents[-(self.agent_max_history_items - 1):]
            except Exception as e:
                logger.error(f"Agent turn failed: {e}")
                self.speak("I encountered an issue while trying to complete the task.")
                self.shared_state["currently_doing"] = "ERROR: TURN FAILED"
                break
        else:
             self.speak("Turn limit reached.")
             self.shared_state["currently_doing"] = "ERROR: TURN LIMIT REACHED"

    # --- Local Tools (Verbs) ---
    def _tool_execute_keyboard_shortcut(self, keys: list):
        logger.info(f"[Tool] Executing shortcut: {keys}")
        try:
            normalized_keys = [str(k).strip().lower() for k in keys if str(k).strip()]
            if not normalized_keys:
                return
            pyautogui.hotkey(*normalized_keys[:4])
        except Exception as e:
            logger.error(f"Shortcut error: {e}")

    def _tool_type_string(self, text: str):
        logger.info(f"[Tool] Typing string: {text}")
        try:
            safe_text = str(text)[:500]
            if not safe_text:
                return
            pyautogui.write(safe_text, interval=0.01)
        except Exception as e:
            logger.error(f"Typing error: {e}")

    def _tool_escalate_to_agent(self, task_description: str):
        logger.info(f"[Tool] Escalating to Full Agent: {task_description}")
        self._handle_agent_loop(task_description)

    def _tool_ignore_non_command_speech(self, reason: str):
        logger.info(f"[Tool] Ignoring speech. Reason: {reason}")
