import threading
import unittest
from inference_scheduler import InferenceScheduler


class TestInferenceScheduler(unittest.TestCase):
    def test_foreground_passes_waiting_background_work(self):
        scheduler = InferenceScheduler()
        active, release = threading.Event(), threading.Event()
        order = []

        def current_background():
            with scheduler.slot(background=True):
                active.set()
                release.wait(3)

        def next_background():
            with scheduler.slot(background=True):
                order.append('background')

        def foreground():
            with scheduler.slot():
                order.append('foreground')

        first = threading.Thread(target=current_background)
        queued = threading.Thread(target=next_background)
        message = threading.Thread(target=foreground)
        first.start()
        self.assertTrue(active.wait(2))
        queued.start()
        message.start()
        try:
            with scheduler._condition:
                self.assertTrue(scheduler._condition.wait_for(
                    lambda: scheduler._foreground_waiters == 1, timeout=2
                ))
            release.set()
        finally:
            release.set()
            for worker in (first, queued, message):
                worker.join(3)
                self.assertFalse(worker.is_alive())
        self.assertEqual(order, ['foreground', 'background'])

    def test_nested_foreground_calls_release_slot_after_error(self):
        scheduler = InferenceScheduler()
        with self.assertRaises(ValueError):
            with scheduler.slot():
                with scheduler.slot():
                    raise ValueError('model failed')
        entered = threading.Event()

        def work():
            with scheduler.slot(background=True):
                entered.set()

        worker = threading.Thread(target=work)
        worker.start()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(entered.is_set())


if __name__ == '__main__':
    unittest.main()
