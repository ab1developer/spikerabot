"""Give foreground requests priority over book extraction on local Ollama."""
from contextlib import contextmanager
from functools import wraps
import threading


class InferenceScheduler:
    def __init__(self):
        self._condition = threading.Condition()
        self._owner = None
        self._depth = 0
        self._foreground_waiters = 0

    @contextmanager
    def slot(self, background=False):
        thread_id = threading.get_ident()
        with self._condition:
            if self._owner == thread_id:
                self._depth += 1
            else:
                if not background:
                    self._foreground_waiters += 1
                    self._condition.notify_all()
                try:
                    self._condition.wait_for(lambda: self._owner is None and (
                        not background or self._foreground_waiters == 0
                    ))
                    self._owner = thread_id
                    self._depth = 1
                finally:
                    if not background:
                        self._foreground_waiters -= 1
        try:
            yield
        finally:
            with self._condition:
                self._depth -= 1
                if self._depth == 0:
                    self._owner = None
                    self._condition.notify_all()


inference_scheduler = InferenceScheduler()


def foreground_inference(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with inference_scheduler.slot():
            return function(*args, **kwargs)
    return wrapped
