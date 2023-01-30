"""Transition of a LED."""
import time
import threading
from light import PwmSimpleLed


class Transition:
    """Represents a transition of a LED."""
    _led: PwmSimpleLed

    def __init__(self, led: PwmSimpleLed, duration, from_brightness, to_brightness):
        """
        Initialize the transition.
        :param led: The led to control.
        :param duration: The duration.
        :param from_brightness: The source state of the led.
        :param to_brightness: The target state of the led.
        """
        self._led = led
        self._duration = duration
        self._from_brightness = from_brightness
        self._to_brightness = to_brightness

        self._cancelled = False
        self._finish_event = threading.Event()
        self._start_time = time.perf_counter()

    @property
    def duration(self):
        """
        Duration property.
        :return: The duration of the transition.
        """
        return self._duration

    @property
    def progress(self):
        """
        Progress property.
        :return: The progress of the transition (0.0-1.0).
        """
        if self._duration == 0:
            return 1

        run_time = time.perf_counter() - self._start_time
        return max(0, min(1, run_time / self._duration))

    @property
    def finished(self):
        """
        Finshed property.
        :return: True, if transition has finished. False otherwise.
        """
        return self._finish_event.is_set()

    @property
    def cancelled(self):
        """
        Cancelled property.
        :return: True, if transition was cancelled. False otherwise.
        """
        return self._cancelled

    def step(self):
        """Apply the current stage of the transition based on current time."""
        if self.cancelled or self.finished:
            return

        if self.progress == 1:
            self._finish()
            return

        state = {}
        src_is_on = self._from_brightness == 0
        dest_is_on = self._to_brightness == 0

        src_brightness = self._from_brightness
        dest_brightness = self._to_brightness
        if src_is_on is False:
            if dest_brightness is None:
                dest_brightness = src_brightness
            src_brightness = 0
        if dest_is_on is False:
            dest_brightness = 0
        if src_brightness is not None and dest_brightness is not None:
            self._led.set_brightness(self._interpolate(
                src_brightness,
                dest_brightness,
            ))

    def _interpolate(self, start, end):
        """
        Interpolate a value from start to end at the current progress.
        :param start: The start value.
        :param end: The end value.
        :return: The interpolated value at the current progress.
        """
        diff = end - start
        return start + self.progress * diff

    def _finish(self):
        """Complete transition and mark it as finished."""
        state = self._to_brightness
        self._led.set_brightness(state)

        self._finish_event.set()

    def wait(self, timeout=None):
        """
        Wait for transition to be finished.
        :param timeout: Timeout of the operation in seconds.
        """
        self._finish_event.wait(timeout=timeout)

    def cancel(self):
        """Cancel the transition."""
        self._cancelled = True
        self._finish_event.set()
