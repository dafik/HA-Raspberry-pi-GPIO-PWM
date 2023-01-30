"""Support for LED lights that can be controlled using PWM."""
from __future__ import annotations

import logging

from gpiozero import PWMLED
from gpiozero.pins.pigpio import PiGPIOFactory

import voluptuous as vol

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
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from transition import Transition
from transition_manager import TransitionManager

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
        self._brightness = DEFAULT_BRIGHTNESS
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
        self._cancel_active_transition();
        if ATTR_BRIGHTNESS in kwargs and ATTR_TRANSITION in kwargs:
            self._transition(kwargs[ATTR_TRANSITION], 0, _from_hass_brightness(kwargs[ATTR_BRIGHTNESS]))

        elif ATTR_BRIGHTNESS in kwargs:
            self.set_brightness(_from_hass_brightness(kwargs[ATTR_BRIGHTNESS]))

        self._is_on = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        _LOGGER.info("TURN ON: " + self.name + " args: " + str(locals()))
        self._cancel_active_transition();
        """Turn off a LED."""
        if self.is_on:
            self._led.off()
        self._is_on = False
        self.schedule_update_ha_state()

    def set_brightness(self, value):
        _LOGGER.info("BRIGHTNESS: " + str(self.brightness) + " new: " + str(value))

        self._brightness = value
        self._led.value = value

        if value == 0:
            self._is_on = False

    def _transition(self, duration, from_brightness, to_brightness):
        _LOGGER.info("TRANSITION: dur: " + str(duration) + " from: " + str(from_brightness) + " to: " + str(to_brightness))
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


def _from_hass_brightness(brightness):
    """Convert Home Assistant brightness units to percentage."""
    return brightness / 255
