"""Fixtures: a fake Gorgy clock that speaks the real wire protocol over HTTP."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from unittest.mock import patch

from aiohttp import web
import pytest

from custom_components.gorgy.const import DOMAIN
from custom_components.gorgy.protocol import parse_key_values, split_chrono_fields
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Captured from a real GT_LEDI, firmware 120.1.8.5 (serial and MAC replaced)
DISPLAY_GETDATA = "timeAlternationDuration=12/dateAlternationDuration=0/tempAlternationDuration=0/color=0/vaguecolor=0/brightness=5/maxbrightness=7/brightnessoverride=0/offsethour=1/offsetminute=0/langue=1/dstPolicy=1/dstBegin=00/00/00/00/dstEnd=00/00/00/00/bleublanc=0/calendardisplayed=0/temperatureSpan=0/syncdots=1/behavdots=0/tenthTemperature=0/brightnessoverride=0/"
CHRONO_GETDATA = "0/2026-11-03 16:02:29//00/00/00/0/00/00/00/0///hidden/////hidden/////////Stopped/Arreté/0 day 00:00:00 will be used as the default value/Valeur par défaut: 0 jour 00:00:00 utilisée/////0/1/1/Count up/Chronomètre/start_up/1/Count down/Décompte/start_down/1/Pause/Pause/pause/0////Stopwatch is currently not displayed on the product. Click here to display it./Chronomètre non affiché sur le produit. Cliquez ici pour l'afficher./Display stopwatch on clock(s)/Afficher le Chronomètre/display/7/3/4//selected//////selected///selected///selected/////selected//////selected///selected///selected/////selected//////selected///selected///selected/////selected//////selected///selected///selected/////selected//////selected///selected///selected/////selected//////selected///selected///selected/////selected//////selected///selected///selected////Red/Rouge/Amber/Jaune/Green/Vert"
INDEX_GETDATA = "connect=nologin/deviceName=GT_LEDI/serialNumber=123456\x03/firmware=120.1.8.5/hardware=125/remarkText=GORGY TIMING NTP Clock/ipaddr=127.0.0.1/mac=00:11:22:33:44:55/time=2026-11-05  6:32:28/synchro=5/ntpserver=0.de.pool.ntp.org (212.132.108.186)/adjusttime=0 s -1 ms -271 us/temperature=--.-/°C/temperatureLine=0/runtime=0d:17:59:59/localtime=2026-11-05  7:32:28/remoteCtrled=0/remoteCtrlStatus=0/"
MENU = "name=GT_LEDI_123456/version=120.1.8.5/chrono=1/temperature=0/ledihandi=0/wifiethernet=0/output=0"
LOGIN_PAGE = '<html><body><input id="password" type="password"/></body></html>'

PASSWORD = "secret"
SERIAL = "123456"


class FakeClock:
    """Minimal emulation of the clock's web server."""

    def __init__(self) -> None:
        self.host = ""
        self.password = PASSWORD
        self.token = "0123456789abcdef0123456789abcdef"
        self.reachable = True
        self.display = parse_key_values(DISPLAY_GETDATA)
        self.chrono = split_chrono_fields(CHRONO_GETDATA)
        self.display_posts: list[str] = []
        self.chrono_posts: list[tuple[str, str]] = []
        self.logins = 0

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self._reachable])
        app.router.add_get("/index/getdata", self._text(INDEX_GETDATA))
        app.router.add_get("/menu", self._text(MENU))
        app.router.add_post("/login/", self._login)
        app.router.add_get("/display/getdata", self._protected(self._get_display))
        app.router.add_post("/display/setdata", self._protected(self._set_display))
        app.router.add_get("/chrono/getdata", self._protected(self._get_chrono))
        app.router.add_post("/chrono/{action}", self._protected(self._chrono_action))
        return app

    @staticmethod
    def _text(text: str):
        async def handler(_: web.Request) -> web.Response:
            return web.Response(text=text)

        return handler

    @web.middleware
    async def _reachable(self, request: web.Request, handler):
        if not self.reachable:
            raise web.HTTPServiceUnavailable
        return await handler(request)

    async def _login(self, request: web.Request) -> web.Response:
        self.logins += 1
        if await request.text() != f"login/user=admin/pwd={self.password}":
            return web.Response(text="Invalid password")
        return web.Response(text="Success", headers={"Cookie": self.token})

    def _protected(self, handler):
        async def wrapper(request: web.Request) -> web.Response:
            if request.headers.get("Cookie") != self.token:
                return web.Response(text=LOGIN_PAGE)  # HTTP 200, like the real clock
            return await handler(request)

        return wrapper

    async def _get_display(self, _: web.Request) -> web.Response:
        parts = [f"{key}={'/'.join(value) if isinstance(value, list) else value}" for key, value in self.display.items()]
        return web.Response(text="/".join(parts) + "/")

    async def _set_display(self, request: web.Request) -> web.Response:
        body = await request.text()
        self.display_posts.append(body)
        posted = parse_key_values(body.removeprefix("display/"))
        for key in ("timeAlternationDuration", "dateAlternationDuration", "color", "brightness",
                    "syncdots", "behavdots", "brightnessoverride"):
            self.display[key] = posted[key]
        return web.Response(text="Success")

    async def _get_chrono(self, _: web.Request) -> web.Response:
        return web.Response(text="/".join(field.replace("/", "\\/") for field in self.chrono))

    async def _chrono_action(self, request: web.Request) -> web.Response:
        action = request.match_info["action"]
        form = await request.text()
        self.chrono_posts.append((action, form))
        f = self.chrono
        if action == "start_up":
            f[27], f[37] = "Counting up", "0"
            f[38], f[40], f[41] = "Reset", "reset", "1"
            f[45] = "0"
            f[46], f[48], f[49] = "Pause", "pause", "1"
        elif action == "pause":
            f[27] = "Paused"
            f[46], f[48] = "Resume", "resume"
        elif action == "reset":
            self.chrono = split_chrono_fields(CHRONO_GETDATA)
        elif action == "set_bound_times":
            minutes = dict(pair.split("=") for pair in form.split("&"))["startMinSet"]
            f[13], f[14], f[15], f[16] = "", "0", "00", minutes.zfill(2)
        return web.Response(text="OK")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Iterator[None]:
    """Load custom_components/gorgy."""
    yield


@pytest.fixture
async def fake_clock(socket_enabled: None) -> AsyncIterator[FakeClock]:
    """A fake clock listening on 127.0.0.1."""
    clock = FakeClock()
    runner = web.AppRunner(clock.app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    clock.host = f"127.0.0.1:{port}"
    yield clock
    await runner.cleanup()


@pytest.fixture
def mock_entry(fake_clock: FakeClock) -> MockConfigEntry:
    """Config entry pointing at the fake clock."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Gorgy GT_LEDI",
        unique_id=SERIAL,
        data={CONF_HOST: fake_clock.host, CONF_PASSWORD: PASSWORD},
    )


@pytest.fixture
async def setup_entry(hass: HomeAssistant, mock_entry: MockConfigEntry) -> MockConfigEntry:
    """Set up the integration against the fake clock."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    return mock_entry


@pytest.fixture
def no_setup() -> Iterator[None]:
    """Config flow tests: don't set up the entry after the flow."""
    with patch("custom_components.gorgy.async_setup_entry", return_value=True):
        yield
