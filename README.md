# Gorgy Timing for Home Assistant

Home Assistant integration for **Gorgy Timing** LED clocks. It controls the display
(on/off, brightness, color, colon, display durations) and the stopwatch. The
integration talks to the clock locally through its web interface, without a cloud and
without additional Python packages.

Tested with a GT_LEDI (firmware 120.1.8.5) and Home Assistant 2026.10. Other models
with the same web interface probably work too. Feedback is welcome as an
[issue](https://github.com/rick7240/ha-gorgy-timing/issues).

## Installation

**With HACS**

1. *HACS → ⋮ → Custom repositories*: enter `https://github.com/rick7240/ha-gorgy-timing`
   as the URL and choose the type "Integration".
2. Search for "Gorgy Timing" and download it.
3. Restart Home Assistant.

**Manually**

1. Copy the folder `custom_components/gorgy` to `/config/custom_components/gorgy`,
   e.g. with the Samba or SSH add-on.
2. Restart Home Assistant.

**Setup:** *Settings → Devices & services → Add integration → "Gorgy Timing"*, then
enter the IP address and the password of the web interface. The password must not
contain `/` or `=`; the clock's login format cannot transmit them.

## Entities

One device per clock, polled every 30 s.

| Type | Name | Function |
|---|---|---|
| Light | Display | On/off and brightness. "On" restores the previous brightness. 100 % is the recommended maximum brightness as long as "Override maximum brightness" is off |
| Switch | Override maximum brightness | Allow brightness above the recommended maximum |
| Select | Digit color | Red/amber/green (or white/cyan/blue) |
| Select | Colon, Colon lights up | Blinking/fixed; when it lights up |
| Number | Time display duration, Date display duration | 0–15 s |
| Number | Stopwatch start value | Minutes, can only be changed while the stopwatch is stopped |
| Button | Stopwatch count up / count down / pause / resume / reset, Show / Hide stopwatch on clock | Actions the clock does not offer at the moment are "unavailable" |
| Sensor | Stopwatch | Stopped / Paused / Counting up / Counting down |
| Diagnostic | NTP synchronized, NTP server | |

The stopwatch entities only exist on models with a stopwatch. The integration
deliberately does not show the running counter: a sensor that changes every second
would only fill Home Assistant's database.

Entity names are translated into English and German.

## Notes

- If the password on the clock changes, Home Assistant asks for the new one. A new IP
  address can be entered with *Reconfigure*.
- The clock's web interface can only handle one request at a time. If another client
  (a browser, your own scripts) accesses it at the same moment, a single request can
  fail. The next poll catches up.
- Brightness 0 turns the display completely dark. "Off" in Home Assistant does exactly
  that.

## The clock's protocol

The clock has no official API. The integration uses the same calls as its web
interface:

- **Login:** `POST /login/` with the raw body `login/user=admin/pwd=<password>` →
  `Success`. The token comes back in the *response* header `Cookie` and is sent back as
  `Cookie: <token>`. Without a valid token, protected pages return the login page with
  HTTP 200.
- **Display:** `GET /display/getdata`, `POST /display/setdata`. The clock always expects
  the complete set in the format `key=value/key=value/…`. The integration therefore
  reads first, changes individual fields and writes everything back, byte-identical to
  the web interface.
- **Stopwatch:** `GET /chrono/getdata` is position-based (`\/` is an escaped slash). The
  buttons are form POSTs to `/chrono/<action>`. Which action a button triggers depends
  on the state, so the integration only runs an action if the clock offers it at that
  moment.
- **Do not reuse connections:** on a keep-alive connection the clock sends an extra
  empty response after the login. From then on every answer belongs to the *previous*
  request. The integration therefore opens a new connection for every request and does
  not use Home Assistant's shared HTTP session.
- `GET /menu` reveals without a login which functions the model has (`chrono=1/…`).

## Development

The tests run against a simulated clock (`tests/conftest.py`) that speaks the real HTTP
protocol. Requires Python ≥ 3.14.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

## License

[MIT](LICENSE). This is not an official Gorgy Timing product.
