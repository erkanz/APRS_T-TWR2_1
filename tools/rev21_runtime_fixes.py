#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"
PIO = ROOT / "platformio.ini"


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    old_wdt = '''  esp_task_wdt_config_t twdt_config = {\n    .timeout_ms = 30000, // 30 seconds\n    .idle_core_mask = 0, // Do not subscribe IDLE0/IDLE1 to the user TWDT\n    .trigger_panic = false,\n  };\n  esp_err_t twdt_rc = esp_task_wdt_reconfigure(&twdt_config);\n  if (twdt_rc == ESP_ERR_INVALID_STATE)\n    twdt_rc = esp_task_wdt_init(&twdt_config);\n  printf("[REV2.1] TWDT configure rc=%d\\n", (int)twdt_rc);\n  if (esp_task_wdt_status(NULL) != ESP_OK)\n    esp_task_wdt_add(NULL);\n'''
    new_wdt = '''  // Rev2.1: leave the global Task Watchdog under Arduino/ESP-IDF ownership.\n  // Reconfiguring it here breaks framework idle-task subscriptions and causes\n  // repeated "esp_task_wdt_reset: task not found" diagnostics.\n  printf("[REV2.1] TWDT framework-managed\\n");\n'''

    if old_wdt in text:
        text = text.replace(old_wdt, new_wdt, 1)
        print("PATCH remove custom TWDT reconfiguration")
    elif new_wdt in text:
        print("SKIP  custom TWDT already removed")
    else:
        raise RuntimeError("unexpected TWDT block; refusing blind edit")

    # These resets belonged to the removed application-owned TWDT policy.
    text, reset_count = re.subn(
        r"^(\s*)esp_task_wdt_reset\(\);\s*$",
        r"\1// Rev2.1: framework-managed TWDT; no task-local reset.",
        text,
        flags=re.MULTILINE,
    )
    if reset_count:
        print(f"PATCH remove application TWDT reset calls: {reset_count}")
    else:
        print("SKIP  application TWDT reset calls already removed")

    # XPowersLib can return enum values outside this legacy display table.  The
    # previous code indexed blindly and the Rev2.1 boot log showed val=22,
    # producing an out-of-bounds read (e.g. a bogus 15384 mA display value).
    unsafe_charge_log = '  log_d("Setting Charge Target Current : %d", currTable[val]);\n'
    safe_charge_log = '''  if (val < (sizeof(currTable) / sizeof(currTable[0])))\n    log_d("Setting Charge Target Current : %d", currTable[val]);\n  else\n    log_w("Charge current enum %u is outside legacy display table", (unsigned)val);\n'''
    if unsafe_charge_log in text:
        text = text.replace(unsafe_charge_log, safe_charge_log, 1)
        print("PATCH bound-check charge-current display table")
    elif safe_charge_log in text:
        print("SKIP  charge-current display table already guarded")
    else:
        raise RuntimeError("unexpected charge-current logging block")

    MAIN.write_text(text, encoding="utf-8")


def patch_platformio() -> None:
    text = PIO.read_text(encoding="utf-8")
    old = "\tadafruit/Adafruit NeoPixel@^1.11.0\n"
    new = "\tadafruit/Adafruit NeoPixel@1.12.3\n"
    if old in text:
        text = text.replace(old, new, 1)
        print("PATCH pin Adafruit NeoPixel to 1.12.3 for ESP32-S3 RMT compatibility")
    elif new in text:
        print("SKIP  Adafruit NeoPixel already pinned to 1.12.3")
    else:
        raise RuntimeError("unexpected Adafruit NeoPixel dependency declaration")
    PIO.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_main()
    patch_platformio()
    print("Rev2.1 runtime stability fixes applied.")
