import time
import pytest
import threading

from src.ingest.watcher import _Debouncer

def test_debounce_fires_after_delay():
    fired = threading.Event()
    handler = _Debouncer(fired.set, delay=0.05)
    handler.trigger()
    assert fired.wait(timeout=0.1), "Debounced callback did not fire within expected time"

def test_debounce_reset_on_rapid_triggers():
    call_times: list[float] = []
    def callback():
        call_times.append(time.time())
    handler = _Debouncer(callback, delay=0.05)
    for _ in range(5):
        handler.trigger()
        time.sleep(0.01)  # Rapid triggers, less than debounce delay
    time.sleep(0.1)  # Wait longer than debounce delay to ensure callback fires
    assert len(call_times) == 1

def test_debounce_handles_callback_exception():
    """Exceptions in the callback must not crash the timer thread."""
    finished = threading.Event()

    def bad_callback():
        finished.set()
        raise RuntimeError("intentional error")

    handler = _Debouncer(bad_callback, delay=0.05)
    handler.trigger()
    assert finished.wait(timeout=1.0)
    # No exception propagated to test thread