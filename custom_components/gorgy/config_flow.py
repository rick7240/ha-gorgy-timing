"""Config flow for the Gorgy Timing integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import DeviceStatus, GorgyAuthError, GorgyClient, GorgyError, create_session, password_supported
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


def _normalize_host(host: str) -> str:
    """Accept "http://192.168.1.20/" as well as "192.168.1.20"."""
    host = host.strip()
    for prefix in ("http://", "https://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
    return host.rstrip("/")


async def _async_validate(host: str, password: str) -> DeviceStatus:
    """Connect, log in and read the display settings once."""
    async with create_session() as session:
        client = GorgyClient(session, host, password)
        status = await client.get_status()
        await client.get_display()  # needs a valid password
    return status


async def _async_try_validate(
    host: str, password: str, errors: dict[str, str]
) -> DeviceStatus | None:
    """Validate and fill errors for the form."""
    if not password_supported(password):
        errors[CONF_PASSWORD] = "unsupported_password"
        return None
    try:
        return await _async_validate(host, password)
    except GorgyAuthError:
        errors["base"] = "invalid_auth"
    except GorgyError as err:
        _LOGGER.debug("Cannot connect to %s: %s", host, err)
        errors["base"] = "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error while connecting to %s", host)
        errors["base"] = "unknown"
    return None


class GorgyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Gorgy Timing clock."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for address and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            password = user_input[CONF_PASSWORD]
            if status := await _async_try_validate(host, password, errors):
                await self.async_set_unique_id(status.serial_number)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"Gorgy {status.device_name}",
                    data={CONF_HOST: host, CONF_PASSWORD: password},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The password was changed on the clock."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            if status := await _async_try_validate(entry.data[CONF_HOST], password, errors):
                await self.async_set_unique_id(status.serial_number)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PASSWORD: password})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change address or password, e.g. after the clock got a new IP."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            password = user_input[CONF_PASSWORD]
            if status := await _async_try_validate(host, password, errors):
                await self.async_set_unique_id(status.serial_number)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host, CONF_PASSWORD: password}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input or {CONF_HOST: entry.data[CONF_HOST]}
            ),
            errors=errors,
        )
