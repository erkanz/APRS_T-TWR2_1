#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / "src/main.cpp").read_text(encoding="utf-8")
web = (ROOT / "src/webservice.cpp").read_text(encoding="utf-8")
pio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
workflow = (ROOT / ".github/workflows/rev21-build.yml").read_text(encoding="utf-8")

checks = []

def expect(name, cond):
    checks.append((name, bool(cond)))

# Official Rev2.1 OLED controller, not merely I2C-address detection.
expect("SH1106 header", "#include <Adafruit_SH110X.h>" in main)
expect("SH1106 object", "Adafruit_SH1106G display(" in main)
expect("SH1106 begin", "display.begin(oled_addr, false);" in main)
expect("SSD1306 active include removed", '#include "Adafruit_SSD1306.h"' not in main)
expect("SSD1306 active begin removed", "display.begin(SSD1306_SWITCHCAPVCC" not in "\n".join(
    line for line in main.splitlines() if not line.lstrip().startswith("//")
))
expect("SH1106 dependency pinned", "adafruit/Adafruit SH110X@2.1.14" in pio)

# Mode A legitimately suspends/resumes taskSensor. Mode B deletes/recreates it.
expect("only one taskSensor resume remains", main.count("vTaskResume(taskSensorHandle);") == 1)
expect("Mode B sensor handle nulled after delete", "vTaskDelete(taskSensorHandle);\n                            taskSensorHandle = nullptr;" in main)
expect("Mode B network handle nulled after delete", "vTaskDelete(taskNetworkHandle);\n                            taskNetworkHandle = nullptr;" in main)
mode_b = main.find('log_d("System to light sleep Mode B %d Sec", config.pwr_sleep_interval);')
expect("Mode B marker present", mode_b >= 0)
if mode_b >= 0:
    tail = main[mode_b:]
    first_recreate = tail.find("xTaskCreatePinnedToCore(")
    before_recreate = tail[:first_recreate] if first_recreate >= 0 else tail
    expect("no stale Mode B sensor resume", "vTaskResume(taskSensorHandle);" not in before_recreate)

# Generic web pages may parse legacy values, but backend must normalize fixed Rev2.1
# radio wiring and system I2C topology before save/re-init.
expect("web Rev2.1 hardware helper", "static void enforceRev21RadioHardwareProfile()" in web)
for token in (
    "config.rf_tx_gpio = 39;",
    "config.rf_rx_gpio = 48;",
    "config.rf_sql_gpio = 2;",
    "config.rf_pd_gpio = 40;",
    "config.rf_pwr_gpio = -1;",
    "config.rf_ptt_gpio = 41;",
    "config.rf_sql_active = LOW;",
    "config.rf_pd_active = HIGH;",
    "config.rf_ptt_active = LOW;",
    "config.i2c_sda_pin = 8;",
    "config.i2c_sck_pin = 9;",
    "config.i2c_freq = 400000;",
):
    expect(f"web hardware lock: {token}", token in web)

norm = web.find("enforceRev21RadioHardwareProfile();")
save = web.find('saveConfiguration("/default.cfg", config);', norm if norm >= 0 else 0)
rfinit = web.find("RF_INIT = true;", norm if norm >= 0 else 0)
expect("web radio normalize before save", norm >= 0 and save > norm)
expect("web radio normalize before RF_INIT", norm >= 0 and rfinit > norm)

i2c_commit = web.find("config.i2c_enable = En;")
i2c_norm = web.find("enforceRev21RadioHardwareProfile();", i2c_commit if i2c_commit >= 0 else 0)
i2c_save = web.find('saveConfiguration("/default.cfg", config);', i2c_commit if i2c_commit >= 0 else 0)
expect("web I2C0 normalize before save", i2c_commit >= 0 and i2c_norm > i2c_commit and i2c_save > i2c_norm)

# Serial update helper must remain valid even after web OTA switches active slot.
expect("serial update writes app0", "0x10000 TWR_APRS_Rev21_UPDATE.bin" in workflow)
expect("serial update writes app1", "0x410000 TWR_APRS_Rev21_UPDATE.bin" in workflow)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print(f"{len(checks) - len(failed)}/{len(checks)} deep compatibility checks passed")
if failed:
    raise SystemExit(1)
