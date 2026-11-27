"""Real Lovelace/recorder smoke with an isolated synthetic HA.

The HA container has --network none. The only browser path is an ephemeral
Unix socket to the container's loopback HTTP server. All state and auth are
generated inside the fixture, never from a user's HA. No credentials logged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HA_PORT = 8123
ENTITY = "humidifier.venta_aw730"
SENSORS = {
    "sensor.venta_aw730_humidity": ("44", "46", "%"),
    "sensor.venta_aw730_temperature": ("22", "23", "°C"),
    "sensor.venta_aw730_pm25": ("11", "12", "μg/m³"),
    "sensor.venta_aw730_water_level": ("79", "80", "%"),
}
FAKE_INTEGRATION = """
async def async_setup(hass, config):
    main = "humidifier.venta_aw730"
    fan = "select.venta_aw730_fan_speed"
    led = "switch.venta_aw730_led_on"
    brightness = "select.venta_aw730_led_brightness"
    color = "select.venta_aw730_led_color"
    hass.states.async_set(main, "on", {
        "humidity": 50, "current_humidity": 44, "mode": "Manual",
        "available_modes": ["Auto", "Manual", "Sleep"],
        "min_humidity": 30, "max_humidity": 70,
    })
    hass.states.async_set(fan, "1", {"options": ["1", "2", "3", "4", "5"]})
    hass.states.async_set(led, "on")
    hass.states.async_set(brightness, "4", {"options": [str(i) for i in range(1, 9)]})
    hass.states.async_set(color, "purple", {"options": ["purple", "blue"]})

    async def command(call):
        entity = call.data.get("entity_id")
        if isinstance(entity, list):
            if len(entity) != 1:
                raise ValueError("one synthetic entity required")
            entity = entity[0]
        if entity not in (main, fan, led, brightness, color):
            raise ValueError("unknown synthetic entity")
        state = hass.states.get(entity)
        attrs = dict(state.attributes)
        value = state.state
        if call.service == "set_mode" and entity == main:
            attrs["mode"] = call.data["mode"]
        elif call.service == "set_humidity" and entity == main:
            attrs["humidity"] = call.data["humidity"]
        elif call.service == "select_option" and entity in (fan, brightness, color):
            value = call.data["option"]
            if value not in attrs["options"]:
                raise ValueError("invalid fixture option")
        elif call.service in ("turn_on", "turn_off") and entity in (main, led):
            value = "on" if call.service == "turn_on" else "off"
        else:
            raise ValueError("invalid fixture command")
        hass.states.async_set(entity, value, attrs)

    for domain, names in {
        "humidifier": ("turn_on", "turn_off", "set_mode", "set_humidity"),
        "switch": ("turn_on", "turn_off"),
        "select": ("select_option",),
    }.items():
        for name in names:
            hass.services.async_register(domain, name, command)
    return True
"""


def _pump(src, dst):
    try:
        while data := src.recv(65536):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _relay(left, right):
    with right:
        right.settimeout(None)
        left.settimeout(None)
        t = threading.Thread(target=_pump, args=(left, right), daemon=True)
        t.start()
        _pump(right, left)
        t.join(timeout=3)


class UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


class TCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True


def stage_native_browser_fixture(root: Path, capture_path: Path):
    """Replay the actual isolated registry snapshot for stock HA UI rendering.

    The live command path is tested separately by ha_entity_registry_smoke.
    These two deliberately inert stub integrations only keep captured entries
    loaded; they cannot control a device or create a HomeKit pairing.
    """
    capture = json.loads(capture_path.read_text())
    assert len(capture["entities"]) == 10
    assert {row["entry_id"] for row in capture["storage"]["core.config_entries"]["data"]["entries"]} == {
        "ci-localtuya", "ci-venta", "ci-homekit"}
    for name in ("core.device_registry", "core.entity_registry", "core.config_entries"):
        (root / ".storage" / name).write_text(json.dumps(capture["storage"][name]))
    for domain, name in (("localtuya", "Synthetic LocalTuya"), ("venta_homekit_native", "Venta AW730")):
        component = root / "custom_components" / domain
        component.mkdir(parents=True)
        (component / "manifest.json").write_text(json.dumps({
            "domain": domain, "name": name, "version": "0.0.1",
            "config_flow": True, "codeowners": [], "iot_class": "local_push",
            "integration_type": "device", "documentation": "https://example.invalid/fixture",
        }))
        (component / "__init__.py").write_text(
            "async def async_setup_entry(hass, entry):\n    return True\n")
        (component / "config_flow.py").write_text(
            "from homeassistant import config_entries\n"
            f"class FixtureFlow(config_entries.ConfigFlow, domain={domain!r}):\n    VERSION = 1\n")
    (root / "native-states.json").write_text(json.dumps(capture["states"]))


def serve(bridge: Path, source: Path, native_capture: Path | None = None):
    import yaml
    from homeassistant.const import __version__
    if __version__ != "2026.11.1":
        raise AssertionError("unexpected HA fixture version")
    with tempfile.TemporaryDirectory(prefix="venta-dashboard-ci-") as temp:
        root = Path(temp)
        storage = root / ".storage"
        storage.mkdir()
        # Only the synthetic user onboarding step is performed. Avoid
        # provisioning any unrelated cloud integrations during onboarding.
        (storage / "onboarding").write_text(json.dumps({
            "version": 4, "minor_version": 1, "key": "onboarding",
            "data": {"done": ["core_config", "analytics", "integration"]},
        }))
        if native_capture is not None:
            stage_native_browser_fixture(root, native_capture)
        www = root / "www"
        www.mkdir()
        shutil.copyfile(source / "venta-airwasher-card.js", www / "venta-airwasher-card.js")
        example = yaml.safe_load((source / "example.yaml").read_text())
        (root / "dashboard.yaml").write_text(yaml.safe_dump({
            "views": [{"title": "Venta", "path": "main", "cards": [example]}],
        }, allow_unicode=True))
        fixture = root / "custom_components" / "venta_ci_dashboard"
        fixture.mkdir(parents=True)
        (fixture / "manifest.json").write_text(json.dumps({
            "domain": "venta_ci_dashboard", "name": "Venta CI synthetic fixture",
            "version": "0.0.1", "codeowners": [], "iot_class": "local_push",
            "documentation": "https://example.invalid/fixture",
        }))
        fixture_code = FAKE_INTEGRATION
        if native_capture is not None:
            fixture_code = fixture_code.replace("    return True", """    import json
    from pathlib import Path
    def load_states():
        return json.loads(Path(hass.config.path("native-states.json")).read_text())
    for entity_id, state in (await hass.async_add_executor_job(load_states)).items():
        hass.states.async_set(entity_id, state["state"], state["attributes"])
    return True""")
        (fixture / "__init__.py").write_text(fixture_code)
        (root / "configuration.yaml").write_text(yaml.safe_dump({
            "homeassistant": {
                "name": "Venta CI", "latitude": 0, "longitude": 0,
                "elevation": 0, "unit_system": "metric", "time_zone": "UTC",
            },
            # HA 2026.11 migrates nondefault YAML HTTP settings into a
            # pending trial requiring confirmation. Use defaults instead;
            # the entire container has --network none, and the relay only
            # connects to its loopback. Never suppress the HA dialog.
            "frontend": {}, "api": {}, "recorder": {"commit_interval": 1},
            "history": {}, "venta_ci_dashboard": {},
            "lovelace": {
                "resource_mode": "yaml",
                "resources": [{"url": "/local/venta-airwasher-card.js", "type": "module"}],
                "dashboards": {"venta-ci": {
                    "mode": "yaml", "title": "Venta CI",
                    "filename": "dashboard.yaml", "show_in_sidebar": True,
                    "require_admin": False,
                }},
            },
        }, allow_unicode=True))
        log = root / "ha.log"
        with log.open("wb") as out:
            proc = subprocess.Popen([
                sys.executable, "-m", "homeassistant", "--config", str(root), "--skip-pip",
            ], stdout=out, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 100
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise AssertionError("synthetic HA exited during boot")
                    try:
                        with urlopen(f"http://127.0.0.1:{HA_PORT}/api/onboarding", timeout=2) as response:
                            if response.status == 200:
                                break
                    except (HTTPError, URLError, OSError, TimeoutError):
                        pass
                    time.sleep(1)
                else:
                    raise AssertionError("synthetic HA onboarding not ready")

                class Handler(socketserver.BaseRequestHandler):
                    def handle(self):
                        try:
                            upstream = socket.create_connection(("127.0.0.1", HA_PORT), timeout=5)
                        except OSError:
                            return
                        _relay(self.request, upstream)

                with UnixServer(str(bridge / "ha.sock"), Handler) as server:
                    print("ISOLATED_HA_FRONTEND_READY", flush=True)
                    server.serve_forever(poll_interval=0.1)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                # Never emit auth, response bodies or raw HA logs.


def request(base, path, data=None, auth=None, *, form=False):
    body = None
    headers = {}
    if data is not None:
        body = urlencode(data).encode() if form else json.dumps(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    if auth:
        headers["Authorization"] = "Bearer " + auth
    try:
        with urlopen(Request(base + path, data=body, headers=headers), timeout=15) as response:
            return json.loads(response.read())
    except HTTPError as err:
        raise AssertionError(f"fixture endpoint {path.split('?')[0]} HTTP {err.code}") from None


def check_native_device_page(page, base, capture, width):
    """Actual stock integration/device pages, captured synthetic registry."""
    from playwright.sync_api import expect

    page.goto(base + "/config/integrations/integration/venta_homekit_native",
              wait_until="domcontentloaded", timeout=45000)
    entry = page.locator('ha-config-entry-row[data-entry-id="ci-venta"]')
    expect(entry).to_be_visible(timeout=60000)
    device_id = capture["device_id"]
    row = entry.locator("ha-config-entry-device-row")
    expect(row).to_have_count(1, timeout=30000)
    expect(row).to_be_visible(timeout=30000)
    assert row.evaluate("el => el.device.id") == device_id
    row.locator('[slot="headline"]').click()
    expect(page).to_have_url(base + "/config/devices/device/" + device_id, timeout=30000)
    expect(page.locator("ha-device-info-card")).to_be_visible(timeout=60000)
    cards = page.locator("ha-device-entities-card")
    expected = set(capture["entities"].values())
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        observed = set(cards.evaluate_all(
            "(els) => els.flatMap(el => (el.entities || []).map(e => e.entity_id))"))
        if observed == expected:
            break
        page.wait_for_timeout(250)
    else:
        raise AssertionError(f"stock device card roster mismatch: {len(observed)} != {len(expected)}")
    # HA frontend 20261028.5 renders active rows as plain divs under ha-list.
    # Later builds add role=listitem. Count actual active row wrappers in
    # either markup, not unavailable placeholders or registry metadata.
    rows = cards.locator("#entities > ha-list > div:not(.divider), #entities > ha-list-base > div[role=listitem]")
    expect(rows).to_have_count(10, timeout=30000)
    for row in rows.all():
        expect(row).to_be_visible(timeout=10000)
    assert cards.evaluate_all("(els) => els.every(el => el.entities.every(e => !!el.hass.states[e.entity_id] && !['unknown','unavailable'].includes(el.hass.states[e.entity_id].state)))"), "native device state missing"
    for card in cards.all():
        bounds = card.bounding_box()
        if bounds is None or bounds["x"] < -1 or bounds["x"] + bounds["width"] > width + 1:
            raise AssertionError("stock HA device card overflows viewport")
    print(f"PASS: stock integration/device UI {width}px, 10 registry-backed entities", flush=True)


def browser_test(base, chrome, native_capture=None):
    from playwright.sync_api import sync_playwright, expect
    client_id = base + "/"
    code = request(base, "/api/onboarding/users", {
        "name": "Synthetic CI", "username": "venta-ci",
        "password": secrets.token_urlsafe(24), "client_id": client_id, "language": "en",
    })["auth_code"]
    tokens = request(base, "/auth/token", {
        "grant_type": "authorization_code", "code": code, "client_id": client_id,
    }, form=True)
    auth = tokens["access_token"]
    tokens.update(hassUrl=base, clientId=client_id, expires=int(time.time() * 1000) + tokens["expires_in"] * 1000)
    assert request(base, "/api/config", auth=auth)["version"] == "2026.11.1"
    for entity, (before, after, unit) in SENSORS.items():
        request(base, "/api/states/" + entity, {"state": before, "attributes": {"unit_of_measurement": unit}}, auth)
    time.sleep(2)
    for entity, (before, after, unit) in SENSORS.items():
        request(base, "/api/states/" + entity, {"state": after, "attributes": {"unit_of_measurement": unit}}, auth)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        history = request(base, "/api/history/period?" + urlencode({"filter_entity_id": ",".join(SENSORS)}), auth=auth)
        observed = {row[0]["entity_id"]: {state["state"] for state in row} for row in history if row}
        if all({before, after} <= observed.get(entity, set()) for entity, (before, after, _) in SENSORS.items()):
            break
        time.sleep(1)
    else:
        raise AssertionError("real recorder did not return both readings for every sensor")
    print("PASS: real local recorder history for four sensors", flush=True)
    # First establish that the synthetic service actually writes and reads back.
    for service, expected in (("turn_off", "off"), ("turn_on", "on")):
        request(base, "/api/services/humidifier/" + service, {"entity_id": ENTITY}, auth)
        if request(base, "/api/states/" + ENTITY, auth=auth)["state"] != expected:
            raise AssertionError("synthetic REST service readback failed: " + service)
    print("PASS: synthetic HA REST service readback", flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome, headless=True, args=[
            "--disable-background-networking", "--disable-component-update",
            "--disable-dev-shm-usage", "--no-first-run",
        ])
        try:
            for width, height, mobile in ((1280, 900, False), (390, 844, True)):
                context = browser.new_context(viewport={"width": width, "height": height},
                    is_mobile=mobile, has_touch=mobile, device_scale_factor=1, service_workers="block")
                try:
                    context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())
                    context.route_web_socket("**/*", lambda route: route.connect_to_server() if route.url == base.replace("http://", "ws://") + "/api/websocket" else route.close())
                    context.add_init_script("localStorage.setItem('hassTokens', " + json.dumps(json.dumps(tokens)) + ");")
                    page = context.new_page()
                    calls = {}
                    def inspect_sent(payload):
                        try:
                            msg = json.loads(payload)
                            if msg.get("type") == "call_service" and msg.get("domain") in ("humidifier", "select", "switch"):
                                calls[msg["id"]] = [msg.get("domain"), msg.get("service"), "pending"]
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                    def inspect_received(payload):
                        try:
                            msg = json.loads(payload)
                            if msg.get("type") == "result" and msg.get("id") in calls:
                                calls[msg["id"]][2] = "success" if msg.get("success") else "error"
                        except (TypeError, ValueError, AttributeError):
                            pass
                    def inspect_ws(ws):
                        ws.on("framesent", inspect_sent)
                        ws.on("framereceived", inspect_received)
                    page.on("websocket", inspect_ws)
                    page.goto(base + "/venta-ci/main", wait_until="domcontentloaded", timeout=45000)
                    card = page.locator("venta-airwasher-card")
                    expect(card).to_be_visible(timeout=60000)
                    for role, value in (("humidity", "46"), ("temperature", "23"), ("pm25", "12"), ("water", "80")):
                        expect(card.locator('[data-ui="' + role + '"]')).to_have_text(value, timeout=20000)
                    bounds = card.bounding_box()
                    if not bounds or bounds["x"] < -1 or bounds["x"] + bounds["width"] > width + 1:
                        raise AssertionError("Lovelace card overflows viewport")
                    power = card.locator('[data-action="power"]')
                    expect(power).to_be_enabled(timeout=15000)
                    expect(page.locator("dialog-http-pending-config")).not_to_be_visible(timeout=15000)
                    expect(power).to_have_attribute("aria-label", "Питание")
                    if power.bounding_box()["height"] < 44:
                        raise AssertionError("power target too small")
                    def check_power(expected, action):
                        try:
                            expect(power).to_have_attribute("aria-pressed", "true" if expected == "on" else "false", timeout=15000)
                        except AssertionError:
                            state = request(base, "/api/states/" + ENTITY, auth=auth)["state"]
                            message = card.locator('[data-ui="message"]').inner_text()
                            print(f"Power diagnostic {action}: backend={state}; card={message}; calls={list(calls.values())}", flush=True)
                            raise
                        if request(base, "/api/states/" + ENTITY, auth=auth)["state"] != expected:
                            raise AssertionError("browser power did not read back from HA")
                    power.tap() if mobile else power.click()
                    check_power("off", "pointer")
                    expect(power).to_be_enabled(timeout=15000)
                    power.tap() if mobile else power.click()
                    check_power("on", "pointer")
                    if not mobile:
                        expect(power).to_be_enabled(timeout=15000)
                        power.focus()
                        if not power.evaluate("el => el.getRootNode().activeElement === el"):
                            raise AssertionError("native button did not receive keyboard focus")
                        page.keyboard.press("Space")
                        check_power("off", "Space")
                        expect(power).to_be_enabled(timeout=15000)
                        power.focus()
                        page.keyboard.press("Enter")
                        check_power("on", "Enter")
                    auto = card.locator('[data-mode="Auto"]')
                    auto.tap() if mobile else auto.click()
                    expect(card.locator('[data-mode="Auto"]')).to_have_attribute("aria-pressed", "true", timeout=15000)
                    card.locator('[data-fan="3"]').click()
                    expect(card.locator('[data-fan="3"]')).to_have_attribute("aria-pressed", "true", timeout=15000)
                    card.locator('[data-mode="Manual"]').click()
                    expect(card.locator('[data-mode="Manual"]')).to_have_attribute("aria-pressed", "true", timeout=15000)
                    # Keep the next viewport's initial state consistent.
                    card.locator('[data-fan="1"]').click()
                    expect(card.locator('[data-fan="1"]')).to_have_attribute("aria-pressed", "true", timeout=15000)
                    graphs = page.locator("hui-history-graph-card")
                    expect(graphs).to_have_count(2, timeout=30000)
                    for index in range(2):
                        graph = graphs.nth(index)
                        graph.scroll_into_view_if_needed(timeout=15000)
                        chart = graph.locator("state-history-charts")
                        expect(chart).to_be_visible(timeout=30000)
                        expect(chart).to_have_js_property("isLoadingData", False, timeout=30000)
                        if not chart.evaluate("(el) => !!el.historyData"):
                            raise AssertionError("native history graph has no history data")
                    print(f"PASS: actual HA frontend, {width}px {'mobile emulation' if mobile else 'desktop'}", flush=True)
                    if native_capture is not None:
                        check_native_device_page(page, base, native_capture, width)
                finally:
                    context.close()
        finally:
            browser.close()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        history = request(base, "/api/history/period?filter_entity_id=select.venta_aw730_fan_speed", auth=auth)
        if {"1", "3"} <= {state["state"] for row in history for state in row}:
            break
        time.sleep(1)
    else:
        raise AssertionError("real fan state timeline did not record command readback")
    print("PASS: real local recorder fan state timeline", flush=True)
    print("REAL_LOVELACE_BROWSER_PASS", flush=True)


def client(bridge: Path, chrome: str, native_capture: Path | None = None):
    sock = bridge / "ha.sock"
    deadline = time.monotonic() + 110
    while not sock.is_socket() and time.monotonic() < deadline:
        time.sleep(1)
    if not sock.is_socket():
        raise AssertionError("isolated fixture socket not ready")

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                upstream.connect(str(sock))
                _relay(self.request, upstream)
            except OSError:
                upstream.close()

    with TCPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            browser_test(f"http://127.0.0.1:{server.server_address[1]}", chrome,
                         json.loads(native_capture.read_text()) if native_capture else None)
        finally:
            server.shutdown()
            worker.join(timeout=5)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("serve", "client"))
    ap.add_argument("--bridge", type=Path, required=True)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--chrome")
    ap.add_argument("--native-capture", type=Path)
    args = ap.parse_args()
    if args.mode == "serve":
        serve(args.bridge, args.source, args.native_capture)
    else:
        client(args.bridge, args.chrome, args.native_capture)
