import queue
import threading
from tools.interfaces import BaseSystemNavigator

class SystemNavigator(BaseSystemNavigator):
    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict):
        self.data_queue = data_queue
        self.config = config
        self.shared_state = shared_state
        self.running = False

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run)
        thread.start()
        print("System Navigator started.")
        return thread

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                # Simply drain the queue to prevent memory leaks, but perform no actions.
                # Head-pose tracking has been explicitly disabled.
                self.data_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in SystemNavigator: {e}")
