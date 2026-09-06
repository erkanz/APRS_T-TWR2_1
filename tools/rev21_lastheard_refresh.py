#!/usr/bin/env python3
"""Fix the Last Heard dashboard/SSE refresh race.

The main page loads /dashboard asynchronously.  The old server emitted the
Last Heard SSE event while the dashboard response was still being inserted,
so a browser refresh could miss the event and show an empty table until the
next packet arrived.  Request a fresh event only after jQuery has installed
the dashboard DOM.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src/webservice.cpp"

CLIENT_MARKER = "fetch('/lastHeardRefresh',{cache:'no-store'})"
ROUTE_MARKER = 'async_server.on("/lastHeardRefresh", HTTP_GET'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label}: expected exactly one source match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = WEB.read_text(encoding="utf-8")

    if CLIENT_MARKER not in text:
        old = 'webString += "$(\\\"#contentmain\\\").load(\\\"/dashboard\\\");\\n";'
        new = 'webString += "$(\\\"#contentmain\\\").load(\\\"/dashboard\\\", function(){fetch(\'/lastHeardRefresh\',{cache:\'no-store\'});});\\n";'
        text = replace_once(text, old, new, "dashboard post-load refresh")

    if ROUTE_MARKER not in text:
        anchor = '''\tasync_server.on("/dashboard", HTTP_GET, [](AsyncWebServerRequest *request)\n\t\t\t\t\t{ handle_dashboard(request); });\n'''
        route = anchor + '''\tasync_server.on("/lastHeardRefresh", HTTP_GET, [](AsyncWebServerRequest *request)\n\t\t\t\t\t{\n\t\t\t\t\t\trequest->send(204);\n\t\t\t\t\t\tevent_lastHeard();\n\t\t\t\t\t});\n'''
        text = replace_once(text, anchor, route, "Last Heard refresh route")

    required = [CLIENT_MARKER, ROUTE_MARKER, "event_lastHeard();"]
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit("ERROR: Last Heard refresh invariants missing: " + ", ".join(missing))

    WEB.write_text(text, encoding="utf-8")
    print("PASS Dashboard requests Last Heard only after dashboard DOM load")
    print("PASS /lastHeardRefresh emits current in-memory/restored Last Heard table")


if __name__ == "__main__":
    main()
