"""Support for LED lights that can be controlled using PWM."""
from __future__ import annotations

import logging
import threading
import time

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from gpiozero import PWMLED
from gpiozero.pins.pigpio import PiGPIOFactory
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    PLATFORM_SCHEMA,
    SUPPORT_BRIGHTNESS,
    SUPPORT_TRANSITION,
    LightEntity,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_NAME,
    STATE_ON,
    CONF_UNIQUE_ID
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

CONF_LEDS = "leds"
CONF_PIN = "pin"
CONF_FREQUENCY = "frequency"

DEFAULT_BRIGHTNESS = 255

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8888

SUPPORT_SIMPLE_LED = SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_LEDS): vol.All(
            cv.ensure_list,
            [
                {
                    vol.Required(CONF_NAME): cv.string,
                    vol.Required(CONF_PIN): cv.positive_int,
                    vol.Optional(CONF_FREQUENCY): cv.positive_int,
                    vol.Optional(CONF_UNIQUE_ID): cv.string,
                    vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                }
            ],
        )
    }
)


def setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the PWM LED lights."""
    leds = []
    for led_conf in config[CONF_LEDS]:
        pin = led_conf[CONF_PIN]
        opt_args = {}
        if CONF_FREQUENCY in led_conf:
            opt_args["frequency"] = led_conf[CONF_FREQUENCY]
        opt_args["pin_factory"] = PiGPIOFactory(host=led_conf[CONF_HOST], port=led_conf[CONF_PORT])
        led = PwmSimpleLed(PWMLED(pin, **opt_args), led_conf[CONF_NAME], led_conf.get(CONF_UNIQUE_ID))
        leds.append(led)

    add_entities(leds)


class PwmSimpleLed(LightEntity, RestoreEntity):
    """Representation of a simple one-color PWM LED."""

    def __init__(self, led: PWMLED, name, unique_id=None):
        """Initialize one-color PWM LED."""
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._led: PWMLED = led
        self._is_on = False
        self._brightness = _from_hass_brightness(DEFAULT_BRIGHTNESS)
        self._active_transition = None

    async def async_added_to_hass(self):
        """Handle entity about to be added to hass event."""
        await super().async_added_to_hass()
        if last_state := await self.async_get_last_state():
            self._is_on = last_state.state == STATE_ON
            self._brightness = last_state.attributes.get(
                "brightness", DEFAULT_BRIGHTNESS
            )

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._is_on

    @property
    def brightness(self):
        """Return the brightness property."""
        return self._brightness

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_SIMPLE_LED

    def turn_on(self, **kwargs):
        _LOGGER.info("TURN ON: " + self.name + " args: " + str(locals()))
        """Turn on a led."""
        self._cancel_active_transition()
        if ATTR_BRIGHTNESS in kwargs and ATTR_TRANSITION in kwargs:
            self._transition(kwargs[ATTR_TRANSITION], 0, _from_hass_brightness(kwargs[ATTR_BRIGHTNESS]))

        elif ATTR_BRIGHTNESS in kwargs:
            self.set_brightness(_from_hass_brightness(kwargs[ATTR_BRIGHTNESS]))

        self._is_on = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        _LOGGER.info("TURN OFF: " + self.name + " args: " + str(locals()))
        self._cancel_active_transition()
        """Turn off a LED."""
        if ATTR_TRANSITION in kwargs:
            self._transition(kwargs[ATTR_TRANSITION], self.brightness, 0)
        elif self.is_on:
            self._led.off()
        self._is_on = False
        self.schedule_update_ha_state()

    def set_brightness(self, value):
        _LOGGER.info("BRIGHTNESS: " + str(_to_hass_brightness(self.brightness)) + " new: " + str(_to_hass_brightness(value)))

        self._brightness = value
        self._led.value = value

        if value == 0:
            self._is_on = False
        else:
            self._is_on = True

    def _transition(self, duration, from_brightness, to_brightness):
        _LOGGER.info("TRANSITION: dur: " + str(duration) + " from: " + str(_to_hass_brightness(from_brightness)) + " to: " + str(_to_hass_brightness(to_brightness)))
        self._cancel_active_transition()
        return TransitionManager().execute(Transition(
            self,
            duration,
            from_brightness,
            to_brightness,
        ))

    def _cancel_active_transition(self):
        if self._active_transition:
            self._active_transition.cancel()
            self._active_transition = None


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
        self._led.set_brightness(from_brightness)

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
        #if src_is_on is False:
        #    if dest_brightness is None:
        #        dest_brightness = src_brightness
        #    src_brightness = 0
        # if dest_is_on is False:
        #    dest_brightness = 0
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


class SingletonMeta(type):
    """
    The Singleton class can be implemented in different ways in Python. Some
    possible methods include: base class, decorator, metaclass. We will use the
    metaclass because it is best suited for this purpose.
    """

    _instances = {}

    def __call__(cls, *args, **kwargs):
        """
        Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class TransitionManager(metaclass=SingletonMeta):
    """Represents a manager that executes transitions in a separate thread."""
    _thread: threading.Thread
    _transitions: list[Transition]

    STEP_TIME = 0.001

    def __init__(self):
        """Initialize the manager."""
        self._thread = None
        self._transitions = []

    def execute(self, transition: Transition):
        """
        Queue a transition for execution.
        :param transition: The transition
        :return: The started transition.
        """
        self._transitions.append(transition)
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._transition_loop,
                daemon=True,
            )
            self._thread.start()

        return transition

    def _transition_loop(self):
        """Execute all queued transitions step by step."""
        while self._transitions:
            for transition in self._transitions:
                transition.step()
                if transition.finished:
                    self._transitions.remove(transition)

            time.sleep(self.STEP_TIME)


def _from_hass_brightness(brightness):
    """Convert Home Assistant brightness units to percentage."""
    return brightness / 255


def _to_hass_brightness(brightness):
    """Convert Home Assistant brightness units to percentage."""
    return brightness * 255
