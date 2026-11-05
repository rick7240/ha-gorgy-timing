"""Async client for the web interface of a Gorgy Timing clock."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import re
from typing import Any

import aiohttp

from .protocol import (
    DisplayState,
    RawSettings,
    StopwatchState,
    apply_display_changes,
    build_display_payload,
    build_stopwatch_action_form,
    build_stopwatch_preset_form,
    describe_display,
    parse_features,
    parse_key_values,
    parse_stopwatch,
)

DEFAULT_USER = "admin"
DEFAULT_TIMEOUT = 8.0
FORM = "application/x-www-form-urlencoded"
_ACTION_NAME = re.compile(r"^[A-Za-z0-9_]+$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f]")


class GorgyError(Exception):
    """The clock did not do what was asked."""


class GorgyConnectionError(GorgyError):
    """The clock is not reachable or answered with an HTTP error."""


class GorgyAuthError(GorgyError):
    """The clock rejected the password."""


class GorgyStateError(GorgyError):
    """The action is not possible in the clock's current state."""


def create_session() -> aiohttp.ClientSession:
    """HTTP session suitable for the clock. The caller must close it.

    Every request needs its own TCP connection: on a reused connection the
    clock sends an extra empty response after the login, and from then on each
    answer belongs to the *previous* request (seen on GT_LEDI 120.1.8.5).
    Home Assistant's shared session keeps connections alive, so it cannot be used.
    """
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(force_close=True, limit=1),
        # the token travels in a hand-made "Cookie" header, a cookie jar would only interfere
        cookie_jar=aiohttp.DummyCookieJar(),
    )


def password_supported(password: str) -> bool:
    """The login format cannot express "/" or "=" - the original UI has the same limitation."""
    return "/" not in password and "=" not in password


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """Device info from the home page (no login needed)."""

    device_name: str
    serial_number: str
    firmware: str | None
    hardware: str | None
    description: str | None
    ip: str | None
    mac: str | None
    utc_time: str | None
    local_time: str | None
    uptime: str | None
    ntp_server: str | None
    last_correction: str | None
    synchronized: bool
    sync_status: int | None


def _text(raw: RawSettings, key: str) -> str | None:
    value = raw.get(key)
    if isinstance(value, list):
        # e.g. "temperature=--.-/°C" is split at the slash
        return "/".join(value)
    return value


def _is_login_page(text: str) -> bool:
    """Protected pages answer with the login page (HTTP 200) when the token is missing or stale."""
    return 'id="password"' in text


class GorgyClient:
    """Talks to one clock.

    The embedded web server is fragile: it handles one conversation at a time,
    so every public method holds a lock while it talks to the clock. Pass a
    session from create_session().
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        password: str,
        *,
        user: str = DEFAULT_USER,
        timeout: float = DEFAULT_TIMEOUT,
        default_on_brightness: int = 5,
    ) -> None:
        self._session = session
        self.host = host
        self._base_url = f"http://{host}"
        self._user = user
        self._password = password
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self.default_on_brightness = default_on_brightness
        # Brightness to restore on "turn on". Updated whenever the display is
        # seen switched on; the integration persists it across restarts.
        self.last_brightness: int | None = None

    async def _exclusive[T](self, fn: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            return await fn()

    async def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: str | None = None,
        content_type: str | None = None,
    ) -> tuple[str, str | None]:
        """Send one request, return (body, value of the "Cookie" response header).

        The session must not reuse connections, see create_session().
        """
        headers: dict[str, str] = {}
        # The device expects the bare token in a "Cookie" header (document.cookie = token).
        if self._token:
            headers["Cookie"] = self._token
        if content_type:
            headers["Content-Type"] = content_type
        try:
            async with self._session.request(
                method,
                self._base_url + path,
                data=data,
                headers=headers,
                allow_redirects=False,
                timeout=self._timeout,
            ) as response:
                text = await response.text(encoding="utf-8", errors="replace")
                token = response.headers.get("Cookie")
                status = response.status
        except TimeoutError as err:
            raise GorgyConnectionError(f"Clock not reachable ({method} {path}: timed out)") from err
        except aiohttp.ClientError as err:
            raise GorgyConnectionError(f"Clock not reachable ({method} {path}: {err})") from err
        if status >= 400:
            raise GorgyConnectionError(f"Clock answered {status} for {method} {path}")
        return text, token

    async def _login(self) -> None:
        if not self._password:
            raise GorgyAuthError("No password configured")
        if not password_supported(self._password):
            raise GorgyAuthError('The password must not contain "/" or "="')
        self._token = None
        # Raw body exactly as login.html builds it.
        text, token = await self._request(
            "/login/",
            method="POST",
            data=f"login/user={self._user}/pwd={self._password}",
        )
        if text != "Success":
            raise GorgyAuthError(f"Login failed: {text.strip()[:200]}")
        if not token:
            raise GorgyError("Login succeeded but no token was returned")
        # The token comes back in a non-standard *response* header named "Cookie".
        self._token = token

    async def _authed(self, path: str, **kwargs: Any) -> str:
        if not self._token:
            await self._login()
        text, _ = await self._request(path, **kwargs)
        if _is_login_page(text):
            await self._login()
            text, _ = await self._request(path, **kwargs)
            if _is_login_page(text):
                raise GorgyAuthError("Clock keeps asking for a login")
        return text

    # ---- status -----------------------------------------------------------

    async def get_status(self) -> DeviceStatus:
        """Device info, time and NTP state. Does not require a login."""

        async def run() -> DeviceStatus:
            text, _ = await self._request("/index/getdata")
            raw = parse_key_values(text)
            if not raw.get("deviceName"):
                raise GorgyError("Unexpected answer - is this a Gorgy Timing clock?")
            sync = _text(raw, "synchro")
            return DeviceStatus(
                device_name=_text(raw, "deviceName") or "",
                # the firmware appends a control character; index.html cuts it off as well
                serial_number=_CONTROL_CHARS.sub("", _text(raw, "serialNumber") or ""),
                firmware=_text(raw, "firmware"),
                hardware=_text(raw, "hardware"),
                description=_text(raw, "remarkText"),
                ip=_text(raw, "ipaddr"),
                mac=_text(raw, "mac"),
                utc_time=_text(raw, "time"),
                local_time=_text(raw, "localtime"),
                uptime=_text(raw, "runtime"),
                ntp_server=_text(raw, "ntpserver"),
                last_correction=_text(raw, "adjusttime"),
                synchronized=sync in ("3", "4", "5"),
                sync_status=int(sync) if sync and sync.isdigit() else None,
            )

        return await self._exclusive(run)

    async def get_features(self) -> set[str]:
        """Functions of the model, e.g. {"chrono"}. Does not require a login."""

        async def run() -> set[str]:
            text, _ = await self._request("/menu")
            return parse_features(text)

        return await self._exclusive(run)

    # ---- display ----------------------------------------------------------

    async def _read_display(self) -> RawSettings:
        raw = parse_key_values(await self._authed("/display/getdata"))
        self._remember(raw)
        return raw

    def _remember(self, raw: RawSettings) -> None:
        brightness = describe_display(raw).brightness
        if brightness > 0:
            self.last_brightness = brightness

    async def _write_display(self, current: RawSettings, changes: dict[str, Any]) -> DisplayState:
        """The clock only accepts the complete set: read -> modify -> write. Call with the lock held."""
        updated = apply_display_changes(current, changes)
        result = await self._authed("/display/setdata", method="POST", data=build_display_payload(updated))
        if result != "Success":
            raise GorgyError(f"Clock rejected display settings: {result.strip()[:200]}")
        return describe_display(await self._read_display())

    async def get_display(self) -> DisplayState:
        """Current display settings."""

        async def run() -> DisplayState:
            return describe_display(await self._read_display())

        return await self._exclusive(run)

    async def update_display(self, **changes: Any) -> DisplayState:
        """Change display settings, see protocol.apply_display_changes for the keys."""

        async def run() -> DisplayState:
            return await self._write_display(await self._read_display(), changes)

        return await self._exclusive(run)

    async def turn_off(self) -> DisplayState:
        """Brightness 0 switches the LED display off completely (verified on GT_LEDI)."""

        async def run() -> DisplayState:
            current = await self._read_display()
            if describe_display(current).brightness == 0:
                return describe_display(current)
            return await self._write_display(current, {"brightness": 0})

        return await self._exclusive(run)

    async def turn_on(self) -> DisplayState:
        """Restore the brightness that was active before turn_off()."""

        async def run() -> DisplayState:
            current = await self._read_display()
            display = describe_display(current)
            if display.on:
                return display
            target = self.last_brightness or self.default_on_brightness
            # The override may have been switched off meanwhile - fall back to the recommended max.
            if not display.brightness_override:
                target = min(target, display.max_recommended_brightness)
            return await self._write_display(current, {"brightness": max(target, 1)})

        return await self._exclusive(run)

    # ---- stopwatch --------------------------------------------------------

    async def _read_stopwatch(self) -> StopwatchState:
        return parse_stopwatch(await self._authed("/chrono/getdata"))

    async def get_stopwatch(self) -> StopwatchState:
        """Stopwatch state including the actions offered right now."""
        return await self._exclusive(self._read_stopwatch)

    async def run_stopwatch_action(self, action: str) -> StopwatchState:
        """Run start_up, start_down, pause, resume, reset, display, mask, ...

        Only actions the clock currently offers are accepted, so e.g. "start_up"
        can never turn into a reset because the stopwatch changed state meanwhile.
        """

        async def run() -> StopwatchState:
            before = await self._read_stopwatch()
            button = next((b for b in before.buttons if b.enabled and b.action == action), None)
            if button is None:
                raise GorgyStateError(
                    f'Stopwatch action "{action}" is not available (state: {before.state}; '
                    f"available: {', '.join(before.available_actions) or 'none'})"
                )
            if not _ACTION_NAME.match(button.action):
                raise GorgyError(f'Unexpected stopwatch action "{button.action}"')
            await self._authed(
                f"/chrono/{button.action}",
                method="POST",
                data=build_stopwatch_action_form(button),
                content_type=FORM,
            )
            return await self._read_stopwatch()

        return await self._exclusive(run)

    async def set_stopwatch_preset(self, minutes: int) -> StopwatchState:
        """Configure the count-down start value in minutes (basic mode of chrono.html)."""
        form = build_stopwatch_preset_form(minutes)

        async def run() -> StopwatchState:
            before = await self._read_stopwatch()
            if not before.configurable:
                raise GorgyStateError(f"Stopwatch can only be configured when stopped (state: {before.state})")
            await self._authed("/chrono/set_bound_times", method="POST", data=form, content_type=FORM)
            after = await self._read_stopwatch()
            if after.last_error:
                raise GorgyStateError(after.last_error)
            return after

        return await self._exclusive(run)
