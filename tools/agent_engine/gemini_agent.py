import os
import io
import time
import threading
import logging
import platform
import re
import webbrowser
from dotenv import load_dotenv

import mss
import pyautogui
import speech_recognition as sr
from PIL import Image
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

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
        self.agent_startup_tts = bool(self.config.get("AGENT_STARTUP_TTS", False))
        self.router_max_output_tokens = int(self.config.get("LLM_ROUTER_MAX_OUTPUT_TOKENS", 96))
        self.agent_max_output_tokens = int(self.config.get("AGENT_MAX_OUTPUT_TOKENS", 256))
        self.agent_max_turns = max(1, int(self.config.get("AGENT_MAX_TURNS", 6)))
        self.agent_max_actions_per_task = max(1, int(self.config.get("AGENT_MAX_ACTIONS_PER_TASK", 18)))
        self.agent_max_tool_errors = max(1, int(self.config.get("AGENT_MAX_TOOL_ERRORS", 4)))
        self.agent_max_history_items = max(3, int(self.config.get("AGENT_MAX_HISTORY_ITEMS", 8)))
        self.agent_screenshot_max_w = max(640, int(self.config.get("AGENT_SCREENSHOT_MAX_W", 1280)))
        self.agent_screenshot_max_h = max(360, int(self.config.get("AGENT_SCREENSHOT_MAX_H", 800)))
        self.agent_max_api_calls_per_task = max(
            1, int(self.config.get("AGENT_MAX_API_CALLS_PER_TASK", self.agent_max_turns))
        )
        self.agent_max_runtime_seconds = max(
            10.0, float(self.config.get("AGENT_MAX_RUNTIME_SECONDS", 75.0))
        )
        self.agent_min_seconds_between_runs = max(
            0.0, float(self.config.get("AGENT_MIN_SECONDS_BETWEEN_RUNS", 10.0))
        )
        self.agent_session_run_limit = max(
            1, int(self.config.get("AGENT_SESSION_RUN_LIMIT", 8))
        )
        self.agent_browser_backend = str(
            self.config.get("AGENT_BROWSER_BACKEND", "playwright")
        ).strip().lower()
        self.playwright_user_data_dir = str(
            self.config.get(
                "PLAYWRIGHT_USER_DATA_DIR",
                r"C:\Users\antho\AppData\Local\Microsoft\Edge\User Data",
            )
        ).strip()
        self.playwright_browser_channel = "msedge"
        self.playwright_viewport_w = 1440
        self.playwright_viewport_h = 900

        self.running = False
        self.conversation_history = []
        self._last_agent_start_ts = 0.0
        self._session_agent_runs = 0
        self._browser_current_url = "about:blank"
        self._use_playwright_backend_for_task = False
        self._playwright = None
        self._pw_context = None
        self._pw_page = None

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

        if self.agent_startup_tts:
            self.speak("AI Agent ready. Say 'Agent' followed by a command to begin.")
        else:
            logger.info("AI Agent ready (startup TTS disabled). Say 'Agent' followed by a command to begin.")

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

    def _is_captcha_or_human_verification(self, text: str) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return False
        flags = (
            "captcha",
            "not a robot",
            "i am not a robot",
            "i'm not a robot",
            "human verification",
            "verify you are human",
            "security check",
            "challenge",
        )
        return any(flag in normalized for flag in flags)

    def _set_browser_current_url(self, url_value):
        text = str(url_value or "").strip()
        if text:
            self._browser_current_url = text[:2048]

    def _get_browser_current_url(self) -> str:
        if self._pw_page is not None:
            try:
                self._set_browser_current_url(self._pw_page.url)
            except Exception:
                pass
        return self._browser_current_url or "about:blank"

    def _ensure_playwright_page(self) -> bool:
        if self._pw_page is not None:
            try:
                if not self._pw_page.is_closed():
                    return True
            except Exception:
                return True
        if self._pw_context is not None:
            try:
                if hasattr(self._pw_context, "pages"):
                    existing_pages = self._pw_context.pages or []
                    self._pw_page = existing_pages[0] if existing_pages else self._pw_context.new_page()
                    return True
            except Exception:
                pass
        if self._playwright is not None and self._pw_context is None:
            self._close_playwright_session()

        if not self.playwright_user_data_dir:
            logger.error("Playwright persistent context requires a valid PLAYWRIGHT_USER_DATA_DIR.")
            return False
        if not os.path.isdir(self.playwright_user_data_dir):
            logger.error(
                "Edge user data directory does not exist: %s",
                self.playwright_user_data_dir,
            )
            return False

        if sync_playwright is None:
            logger.warning("Playwright is not installed; falling back to desktop browser control.")
            return False

        try:
            self._playwright = sync_playwright().start()
            self._pw_context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=self.playwright_user_data_dir,
                channel=self.playwright_browser_channel,
                headless=False,
                viewport={"width": self.playwright_viewport_w, "height": self.playwright_viewport_h},
            )
            self._pw_page = self._pw_context.pages[0] if self._pw_context.pages else self._pw_context.new_page()
            self._set_browser_current_url(self._pw_page.url or "about:blank")
            logger.info(
                "Playwright persistent context ready (channel=%s, profile=%s, viewport=%sx%s).",
                self.playwright_browser_channel,
                self.playwright_user_data_dir,
                self.playwright_viewport_w,
                self.playwright_viewport_h,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Playwright browser session: {e}")
            self._close_playwright_session()
            return False

    def _close_playwright_session(self):
        try:
            if self._pw_context is not None:
                self._pw_context.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass

        self._pw_page = None
        self._pw_context = None
        self._playwright = None

    def _capture_agent_screenshot_bytes(self) -> bytes:
        if self._use_playwright_backend_for_task and self._pw_page is not None:
            try:
                screenshot = self._pw_page.screenshot(type="png")
                self._set_browser_current_url(self._pw_page.url)
                return screenshot
            except Exception as e:
                logger.warning(f"Playwright screenshot failed; using desktop capture instead: {e}")
        return self._capture_screen_bytes()

    def _playwright_denormalize(self, x: int, y: int):
        viewport = None
        if self._pw_page is not None:
            try:
                viewport = self._pw_page.viewport_size
            except Exception:
                viewport = None
        width = int((viewport or {}).get("width", self.playwright_viewport_w))
        height = int((viewport or {}).get("height", self.playwright_viewport_h))

        x_val = max(0.0, min(999.0, float(x)))
        y_val = max(0.0, min(999.0, float(y)))
        px = int((x_val / 1000.0) * width)
        py = int((y_val / 1000.0) * height)
        px = max(0, min(width - 1, px))
        py = max(0, min(height - 1, py))
        return px, py

    def _playwright_wait_for_page_ready(self, timeout_ms=5000):
        if self._pw_page is None:
            return
        try:
            self._pw_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass

    def _playwright_key_name(self, key: str) -> str:
        token = str(key or "").strip().lower()
        key_map = {
            "ctrl": "Control",
            "control": "Control",
            "alt": "Alt",
            "shift": "Shift",
            "command": "Meta",
            "cmd": "Meta",
            "win": "Meta",
            "enter": "Enter",
            "return": "Enter",
            "esc": "Escape",
            "tab": "Tab",
            "space": "Space",
            "backspace": "Backspace",
            "delete": "Delete",
            "left": "ArrowLeft",
            "right": "ArrowRight",
            "up": "ArrowUp",
            "down": "ArrowDown",
            "pageup": "PageUp",
            "pagedown": "PageDown",
            "home": "Home",
            "end": "End",
        }
        if token in key_map:
            return key_map[token]
        if len(token) == 1 and token.isalpha():
            return token.upper()
        return token

    def _playwright_press_keys(self, keys):
        if self._pw_page is None:
            raise RuntimeError("Playwright page is not initialized.")
        mapped = [self._playwright_key_name(k) for k in keys if str(k).strip()]
        if not mapped:
            raise ValueError("No keys to press.")
        if len(mapped) == 1:
            self._pw_page.keyboard.press(mapped[0])
            return
        combo = "+".join(mapped)
        self._pw_page.keyboard.press(combo)

    def _resolve_computer_use_environment(self):
        # SDKs may expose different environment enums across versions.
        env_browser = getattr(types.Environment, "ENVIRONMENT_BROWSER", None)
        if env_browser is not None:
            return env_browser

        os_name = platform.system().lower()
        env_windows = getattr(types.Environment, "ENVIRONMENT_WINDOWS", None)
        env_mac = getattr(types.Environment, "ENVIRONMENT_MAC", None)
        env_linux = getattr(types.Environment, "ENVIRONMENT_LINUX", None)
        fallback_env = env_windows or env_mac or env_linux
        if fallback_env is not None:
            if "windows" in os_name:
                return env_windows or fallback_env
            if "darwin" in os_name or "mac" in os_name:
                return env_mac or fallback_env
            return env_linux or fallback_env

        logger.warning("No known environment enum found; falling back to browser string.")
        return "browser"

    def _extract_function_calls(self, candidate):
        if not candidate or not getattr(candidate, "content", None):
            return []
        parts = getattr(candidate.content, "parts", None) or []
        return [part.function_call for part in parts if getattr(part, "function_call", None)]

    def _extract_agent_command(self, text: str):
        phrase = str(text or "").strip().lower()
        if not phrase:
            return None

        match = re.match(r"^(?:hey|okay|ok)?\s*agent[\s,:-]*(.*)$", phrase)
        if not match:
            return None

        command = (match.group(1) or "").strip()
        return command if len(command) > 2 else ""


    def _run_loop(self):
        if not self.microphone:
            return

        while self.running:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=10)

                text = self.recognizer.recognize_google(audio).lower()
                logger.info(f"[Heard]: {text}")

                # Strict wake-word gateway: only respond when phrase starts with agent wake.
                command = self._extract_agent_command(text)
                if command is not None:
                    if command:
                        self._route_intent(command)
                    else:
                        self.speak("I am listening. Please give a command.")
                        with self.microphone as source:
                            audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)
                        follow_up = self.recognizer.recognize_google(audio).lower()
                        if follow_up:
                            self._route_intent(follow_up)
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

    def _extract_safety_decision(self, args: dict):
        if not isinstance(args, dict):
            return None
        decision = args.get("safety_decision")
        if isinstance(decision, dict):
            return decision
        return None

    def _requires_confirmation(self, args: dict) -> bool:
        decision = self._extract_safety_decision(args)
        if not decision:
            return False
        decision_value = str(decision.get("decision", "")).strip().lower()
        return decision_value == "require_confirmation"

    def _normalize_key_token(self, token: str) -> str:
        token = str(token or "").strip().lower()
        key_map = {
            "control": "ctrl",
            "cmd": "command",
            "return": "enter",
            "esc": "esc",
            "spacebar": "space",
            "pageup": "pageup",
            "pagedown": "pagedown",
        }
        return key_map.get(token, token)

    def _parse_key_combo(self, keys_value):
        if isinstance(keys_value, list):
            raw = [str(k) for k in keys_value]
        else:
            raw = re.split(r"[+\s,]+", str(keys_value or ""))
        normalized = [self._normalize_key_token(k) for k in raw if str(k).strip()]
        return normalized[:4]

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
        use_playwright = self._use_playwright_backend_for_task and self._pw_page is not None

        for function_call in function_calls:
            action_result = {"ok": True}
            fname = str(getattr(function_call, "name", "unknown_action") or "unknown_action")
            fname_l = fname.strip().lower()
            args = dict(getattr(function_call, "args", {}) or {})
            logger.info(f"  -> Agent Executing: {fname} with args: {args}")

            try:
                if self._requires_confirmation(args):
                    explanation = self._extract_safety_decision(args).get("explanation", "")
                    full_reason = f"{fname} {explanation}"
                    if self._is_captcha_or_human_verification(full_reason):
                        self.shared_state["currently_doing"] = "CAPTCHA REQUIRES USER ACTION"
                        logger.warning(f"Blocked CAPTCHA/human verification action: {fname}. {explanation}")
                        self.speak(
                            "I hit a CAPTCHA or human verification step. I cannot solve that safely. "
                            "Please complete it manually, then tell me to continue."
                        )
                        action_result = {
                            "ok": False,
                            "error": "Blocked: CAPTCHA or human verification requires manual completion.",
                            "blocked_reason": "captcha_requires_manual_step",
                        }
                    else:
                        self.shared_state["currently_doing"] = "AGENT ACTION BLOCKED (CONFIRMATION REQUIRED)"
                        logger.warning(f"Blocked action requiring confirmation: {fname}. {explanation}")
                        action_result = {
                            "ok": False,
                            "error": "Blocked: model requested user confirmation for this action.",
                            "blocked_reason": "requires_confirmation",
                        }
                    current_url = self._get_browser_current_url()
                    action_result["current_url"] = current_url
                    action_result["url"] = current_url
                    results.append((fname, action_result))
                    continue

                if fname_l in ["open_web_browser", "open_browser", "search"]:
                    target_url = "https://www.google.com"
                    if fname_l == "open_web_browser":
                        target_url = str(args.get("url", "https://www.google.com")).strip() or "https://www.google.com"
                    self.shared_state["currently_doing"] = "OPENING BROWSER"
                    if use_playwright:
                        self._pw_page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                        self._playwright_wait_for_page_ready()
                        self._set_browser_current_url(self._pw_page.url or target_url)
                    else:
                        webbrowser.open(target_url)
                        self._set_browser_current_url(target_url)

                elif fname_l == "navigate":
                    url = str(args.get("url", "")).strip()
                    if not url:
                        raise ValueError("navigate action missing url.")
                    self.shared_state["currently_doing"] = f"NAVIGATING TO {url[:40]}"
                    if use_playwright:
                        self._pw_page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        self._playwright_wait_for_page_ready()
                        self._set_browser_current_url(self._pw_page.url or url)
                    else:
                        webbrowser.open(url)
                        self._set_browser_current_url(url)

                elif fname_l in ["go_back", "back"]:
                    self.shared_state["currently_doing"] = "BROWSER BACK"
                    if use_playwright:
                        self._pw_page.go_back(wait_until="domcontentloaded", timeout=10000)
                        self._playwright_wait_for_page_ready()
                    else:
                        pyautogui.hotkey("alt", "left")
                    self._get_browser_current_url()

                elif fname_l in ["go_forward", "forward"]:
                    self.shared_state["currently_doing"] = "BROWSER FORWARD"
                    if use_playwright:
                        self._pw_page.go_forward(wait_until="domcontentloaded", timeout=10000)
                        self._playwright_wait_for_page_ready()
                    else:
                        pyautogui.hotkey("alt", "right")
                    self._get_browser_current_url()

                elif fname_l == "wait_5_seconds":
                    self.shared_state["currently_doing"] = "WAITING 5s"
                    time.sleep(5.0)

                elif fname_l in ["click", "click_at", "hover_at", "type", "type_text_at"]:
                    if "x" not in args or "y" not in args:
                        raise ValueError(f"Missing x/y coordinates for {fname}.")

                    if use_playwright:
                        actual_x, actual_y = self._playwright_denormalize(args["x"], args["y"])
                    else:
                        actual_x = self._denormalize_x(args["x"])
                        actual_y = self._denormalize_y(args["y"])

                    # Draw Red Bounding Box on Target (40x40 box centered at click)
                    box_size = 40
                    bbox_x = max(0, actual_x - box_size // 2)
                    bbox_y = max(0, actual_y - box_size // 2)
                    if use_playwright:
                        self.shared_state["agent_target_bbox"] = None
                    else:
                        self.shared_state["agent_target_bbox"] = (bbox_x, bbox_y, box_size, box_size)

                    self.shared_state["currently_doing"] = f"TARGETING {fname.upper()} IN 1.5s..."

                    # Wait for 1.5 seconds to allow voice cancellation
                    if self._wait_for_cancellation(1.5):
                        logger.info("Action cancelled by user!")
                        self.shared_state["currently_doing"] = "ACTION CANCELLED"
                        self.shared_state["agent_target_bbox"] = None
                        action_result = {"ok": False, "error": "User cancelled the action."}
                        current_url = self._get_browser_current_url()
                        action_result["current_url"] = current_url
                        action_result["url"] = current_url
                        results.append((fname, action_result))
                        continue  # Skip execution

                    # Clear box just before action
                    self.shared_state["agent_target_bbox"] = None

                    if fname_l in ["click", "click_at"]:
                        self.shared_state["currently_doing"] = f"CLICKING AT {actual_x}, {actual_y}"
                        if use_playwright:
                            self._pw_page.mouse.click(actual_x, actual_y)
                        else:
                            pyautogui.click(actual_x, actual_y)
                        self.shared_state["clicks_saved"] = self.shared_state.get("clicks_saved", 0) + 1
                    elif fname_l == "hover_at":
                        self.shared_state["currently_doing"] = f"HOVERING AT {actual_x}, {actual_y}"
                        if use_playwright:
                            self._pw_page.mouse.move(actual_x, actual_y)
                        else:
                            pyautogui.moveTo(actual_x, actual_y)
                    elif fname_l in ["type", "type_text_at"]:
                        text = str(args.get("text", ""))
                        if not text:
                            raise ValueError("Type action did not include text.")
                        # Keep runaway prompts from typing massive payloads by mistake.
                        text = text[:2000]
                        self.shared_state["currently_doing"] = f"TYPING: {text[:10]}..."
                        clear_before_typing = bool(args.get("clear_before_typing", fname_l == "type_text_at"))
                        press_enter = bool(args.get("press_enter", fname_l == "type_text_at"))
                        if use_playwright:
                            self._pw_page.mouse.click(actual_x, actual_y)
                        else:
                            pyautogui.click(actual_x, actual_y)
                        self.shared_state["clicks_saved"] = self.shared_state.get("clicks_saved", 0) + 1
                        time.sleep(0.1)
                        if clear_before_typing:
                            if use_playwright:
                                self._pw_page.keyboard.press("Control+A")
                                self._pw_page.keyboard.press("Backspace")
                            else:
                                pyautogui.hotkey("ctrl", "a")
                                pyautogui.press("backspace")
                        if use_playwright:
                            self._pw_page.keyboard.type(text, delay=10)
                        else:
                            pyautogui.write(text, interval=0.01)
                        if press_enter:
                            if use_playwright:
                                self._pw_page.keyboard.press("Enter")
                            else:
                                pyautogui.press('enter')

                elif fname_l in ["key_combination", "execute_keyboard_shortcut"]:
                    keys = self._parse_key_combo(args.get("keys", ""))
                    if not keys:
                        raise ValueError("key_combination action missing keys.")
                    self.shared_state["currently_doing"] = f"KEY COMBO {'+'.join(keys)}"
                    if use_playwright:
                        self._playwright_press_keys(keys)
                    else:
                        if len(keys) == 1:
                            pyautogui.press(keys[0])
                        else:
                            pyautogui.hotkey(*keys)

                elif fname_l in ["scroll", "scroll_document", "scroll_at"]:
                    self.shared_state["currently_doing"] = f"SCROLLING {str(args.get('direction', 'down')).upper()}"
                    try:
                        amount = int(args.get("amount", 1))
                    except Exception:
                        amount = 1
                    amount = max(1, min(8, amount))
                    direction = str(args.get("direction", "down")).lower()

                    if fname_l == "scroll_at" and "x" in args and "y" in args:
                        if use_playwright:
                            sx, sy = self._playwright_denormalize(args["x"], args["y"])
                            self._pw_page.mouse.move(sx, sy)
                        else:
                            sx = self._denormalize_x(args["x"])
                            sy = self._denormalize_y(args["y"])
                            pyautogui.moveTo(sx, sy)
                            pyautogui.click(sx, sy)
                        try:
                            magnitude = int(args.get("magnitude", 800))
                            amount = max(1, min(8, magnitude // 120))
                        except Exception:
                            pass

                    if direction == "down":
                        if use_playwright:
                            self._pw_page.mouse.wheel(0, 450 * amount)
                        else:
                            pyautogui.scroll(-300 * amount)
                    elif direction == "up":
                        if use_playwright:
                            self._pw_page.mouse.wheel(0, -450 * amount)
                        else:
                            pyautogui.scroll(300 * amount)
                    elif direction == "left":
                        if use_playwright:
                            self._pw_page.mouse.wheel(-220 * amount, 0)
                        else:
                            pyautogui.hscroll(-80 * amount)
                    elif direction == "right":
                        if use_playwright:
                            self._pw_page.mouse.wheel(220 * amount, 0)
                        else:
                            pyautogui.hscroll(80 * amount)

                elif fname_l == "drag_and_drop":
                    required = ("x", "y", "destination_x", "destination_y")
                    if not all(k in args for k in required):
                        raise ValueError("drag_and_drop action missing coordinates.")
                    if use_playwright:
                        x1, y1 = self._playwright_denormalize(args["x"], args["y"])
                        x2, y2 = self._playwright_denormalize(args["destination_x"], args["destination_y"])
                    else:
                        x1 = self._denormalize_x(args["x"])
                        y1 = self._denormalize_y(args["y"])
                        x2 = self._denormalize_x(args["destination_x"])
                        y2 = self._denormalize_y(args["destination_y"])
                    self.shared_state["currently_doing"] = "DRAGGING ITEM"
                    if use_playwright:
                        self._pw_page.mouse.move(x1, y1)
                        self._pw_page.mouse.down()
                        self._pw_page.mouse.move(x2, y2, steps=12)
                        self._pw_page.mouse.up()
                    else:
                        pyautogui.moveTo(x1, y1)
                        pyautogui.dragTo(x2, y2, duration=0.25, button="left")

                else:
                    self.shared_state["currently_doing"] = f"EXECUTING {fname.upper()}"
                    logger.warning(f"Unimplemented function {fname}")
                    action_result = {"ok": False, "error": f"Function {fname} not supported by this OS layer yet."}

                if use_playwright:
                    self._playwright_wait_for_page_ready(timeout_ms=2500)

                if fname_l != "wait_5_seconds":
                    time.sleep(0.6 if use_playwright else 1.2)
            except Exception as e:
                logger.error(f"Error executing {fname}: {e}")
                action_result = {"ok": False, "error": str(e)}

            current_url = self._get_browser_current_url()
            action_result["current_url"] = current_url
            action_result["url"] = current_url
            results.append((fname, action_result))

        return results

    def _get_function_responses(self, results):
        function_responses = []
        for name, result in results:
            response_data = dict(result or {})
            known_url = str(
                response_data.get("current_url")
                or response_data.get("url")
                or self._get_browser_current_url()
                or "about:blank"
            ).strip() or "about:blank"
            response_data["current_url"] = known_url
            response_data["url"] = known_url
            function_responses.append(
                types.FunctionResponse(
                    name=name,
                    response=response_data
                )
            )
        return function_responses

    def _handle_agent_loop(self, user_command):
        now = time.time()
        since_last_start = now - self._last_agent_start_ts
        if since_last_start < self.agent_min_seconds_between_runs:
            wait_secs = self.agent_min_seconds_between_runs - since_last_start
            self.shared_state["currently_doing"] = "AGENT COOLDOWN ACTIVE"
            self.speak(f"Please wait {wait_secs:.1f} seconds before starting another agent task.")
            return

        if self._session_agent_runs >= self.agent_session_run_limit:
            self.shared_state["currently_doing"] = "AGENT SESSION LIMIT REACHED"
            self.speak("Session safety limit reached for agent tasks. Restart app to run more.")
            return

        self._last_agent_start_ts = now
        self._session_agent_runs += 1
        self.shared_state["agent_session_runs"] = self._session_agent_runs

        prev_tracking_paused = bool(self.shared_state.get("tracking_paused", False))
        prev_sniper_mode = bool(self.shared_state.get("sniper_mode_active", False))
        prev_dictation_active = bool(self.shared_state.get("dictation_active", False))
        self.shared_state["agent_active"] = True
        self.shared_state["tracking_paused"] = True
        self.shared_state["dictation_active"] = False
        self.shared_state["continuous_scroll_active"] = None
        self.shared_state["sniper_mode_active"] = False
        self.shared_state["magnet_snap_target"] = None
        self.shared_state["magnet_target_bbox"] = None
        self._use_playwright_backend_for_task = False

        try:
            if self.agent_browser_backend == "playwright":
                self._use_playwright_backend_for_task = self._ensure_playwright_page()
                if not self._use_playwright_backend_for_task:
                    logger.warning("Playwright backend unavailable; falling back to desktop browser control.")
            self.speak(f"Okay, taking over. I will try to: {user_command}")
            self.shared_state["currently_doing"] = "PLANNING AGENT ACTIONS..."

            if not self.client:
                logger.warning("Agent disabled due to missing API key.")
                self.speak("API key missing.")
                self.shared_state["currently_doing"] = "ERROR: API KEY MISSING"
                return

            agent_model = self.config.get("LLM_AGENT_MODEL", "gemini-2.5-computer-use-preview-10-2025")
            agent_environment = self._resolve_computer_use_environment()
            computer_use_tool = None
            try:
                computer_use_tool = types.Tool(
                    computer_use=types.ComputerUse(environment=agent_environment)
                )
            except Exception as e:
                logger.warning(f"ComputerUse environment injection failed, retrying without explicit environment: {e}")
                computer_use_tool = types.Tool(computer_use=types.ComputerUse())

            config = types.GenerateContentConfig(
                system_instruction=(
                    "You are a helpful, autonomous UI agent. Use the screen context to execute the user's tasks. "
                    "Do not output require_confirmation unless executing a high-risk action. "
                    "Never attempt to solve CAPTCHA or human verification challenges; stop and report that manual user action is required. "
                    "Keep text output extremely brief."
                ),
                tools=[computer_use_tool],
                temperature=0.0,
                max_output_tokens=self.agent_max_output_tokens,
            )

            initial_screenshot = self._capture_agent_screenshot_bytes()
            contents = [
                Content(role="user", parts=[
                    Part(text=user_command),
                    Part.from_bytes(data=initial_screenshot, mime_type='image/png')
                ])
            ]

            turn_limit = self.agent_max_turns
            total_actions = 0
            total_tool_errors = 0
            api_calls_made = 0
            task_started_at = time.time()
            for i in range(turn_limit):
                logger.info(f"\n--- Agent Turn {i+1} ---")

                elapsed = time.time() - task_started_at
                if elapsed >= self.agent_max_runtime_seconds:
                    self.speak("Stopping to avoid a long-running task.")
                    self.shared_state["currently_doing"] = "STOPPED: RUNTIME LIMIT"
                    break

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
                    if api_calls_made >= self.agent_max_api_calls_per_task:
                        self.speak("Stopping to avoid too many model calls.")
                        self.shared_state["currently_doing"] = "STOPPED: API CALL LIMIT"
                        break

                    response = self.client.models.generate_content(
                        model=agent_model,
                        contents=contents,
                        config=config,
                    )
                    api_calls_made += 1

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

                    elapsed = time.time() - task_started_at
                    if elapsed >= self.agent_max_runtime_seconds:
                        self.speak("Stopping to avoid a long-running task.")
                        self.shared_state["currently_doing"] = "STOPPED: RUNTIME LIMIT"
                        break

                    new_screenshot = self._capture_agent_screenshot_bytes()
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
        finally:
            self._close_playwright_session()
            self._use_playwright_backend_for_task = False
            self.shared_state["agent_active"] = False
            self.shared_state["dictation_active"] = False
            self.shared_state["tracking_paused"] = bool(self.shared_state.get("dictation_active", False)) or prev_tracking_paused
            self.shared_state["sniper_mode_active"] = prev_sniper_mode
            self.shared_state["magnet_snap_target"] = None
            self.shared_state["magnet_target_bbox"] = None
            self.shared_state["agent_target_bbox"] = None
            if prev_dictation_active:
                self.shared_state["voice_status"] = "DICTATION STOPPED (AGENT TOOK CONTROL)"

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
