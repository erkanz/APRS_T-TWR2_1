#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
files = {
    "main": (ROOT / "src/main.cpp").read_text(encoding="utf-8"),
    "config": (ROOT / "include/config.h").read_text(encoding="utf-8"),
    "afsk_cpp": (ROOT / "lib/LibAPRS_ESP32S3/AFSK.cpp").read_text(encoding="utf-8"),
    "afsk_h": (ROOT / "lib/LibAPRS_ESP32S3/AFSK.h").read_text(encoding="utf-8"),
    "pio": (ROOT / "platformio.ini").read_text(encoding="utf-8"),
}

checks = []
def expect(name, cond):
    checks.append((name, bool(cond)))

def no_active(pattern, text):
    return re.search(pattern, text, flags=re.MULTILINE) is None

m = files["main"]
c = files["config"]
a = files["afsk_cpp"]
ah = files["afsk_h"]
pio = files["pio"]

expect("runtime Rev2.1 profile present", "applyTwrRev21HardwareProfile()" in m)
expect("Rev2.1 SQL GPIO2 forced", "config.rf_sql_gpio = 2;" in m)
expect("Rev2.1 RF power GPIO disabled", "config.rf_pwr_gpio = -1;" in m)
expect("audio ADC GPIO1 forced", "config.adc_gpio = 1;" in m)
expect("audio DAC GPIO18 forced", "config.dac_gpio = 18;" in m)
expect("audio mux GPIO17 forced", "config.dac_sel_gpio = 17;" in m)
expect("BLDO1 follows LilyGO 2.0V init", "PMU.setBLDO1Voltage(2000)" in m)
expect("DC3 has no active enable", no_active(r"^\s*PMU\.enableDC3\(\);", m))
expect("DC3 has no active disable", no_active(r"^\s*PMU\.disableDC3\(\);", m))
expect("DC3 has no active voltage set", no_active(r"^\s*PMU\.setDC3Voltage\(", m))
expect("GPIO38 direct writes removed", no_active(r"^\s*digitalWrite\(SA868_PWR_PIN,", m))
expect("GPIO38 direct pinMode removed", no_active(r"^\s*pinMode\(SA868_PWR_PIN,", m))
expect("legacy POWER_PIN writes removed", no_active(r"^\s*digitalWrite\(POWER_PIN,", m))

framework_managed_wdt = "[REV2.1] TWDT framework-managed" in m
legacy_safe_wdt = ".idle_core_mask = 0" in m and "esp_task_wdt_reconfigure(&twdt_config)" in m
expect("TWDT policy is safe during migration", framework_managed_wdt or legacy_safe_wdt)
if framework_managed_wdt:
    expect("no active application TWDT reset", no_active(r"^\s*esp_task_wdt_reset\(\);", m))
    expect("no active TWDT reconfigure", no_active(r"^\s*esp_task_wdt_reconfigure\(", m))
    expect("no active TWDT init", no_active(r"^\s*esp_task_wdt_init\(", m))
else:
    expect("legacy transition TWDT uses idle mask zero", ".idle_core_mask = 0" in m)
    expect("legacy transition TWDT reconfigure present", "esp_task_wdt_reconfigure(&twdt_config)" in m)

expect("charge-current table access is guarded during migration",
       "Charge current enum %u is outside legacy display table" in m or
       'log_d("Setting Charge Target Current : %d", currTable[val]);' in m)
expect("NeoPixel pinned to ESP32-S3-compatible 1.12.3", "adafruit/Adafruit NeoPixel@1.12.3" in pio)
expect("config defaults TX39/RX48", "rf_tx_gpio = 39" in c and "rf_rx_gpio = 48" in c)
expect("config defaults SQL2", "rf_sql_gpio = 2" in c)
expect("config defaults no GPIO38 power", "rf_pwr_gpio = -1" in c)
expect("AFSK has no Rev2.0 SQL default", "int8_t _sql_pin = -1" in a)
expect("AFSK getReceive uses SQL state", "return ((digitalRead(_sql_pin) ^ _sql_active) == 0);" in a)
expect("GPIO2 not declared as RX LED", "#define LED_RX_PIN (-1)" in ah)
expect("GPIO4 not declared as TX LED", "#define LED_TX_PIN (-1)" in ah)
expect("AFSK IRQ macro does not drive GPIO4 alias", "digitalWrite(LED_TX_PIN" not in ah)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + "  " + name)

print(f"\n{len(checks)-len(failed)}/{len(checks)} checks passed")
if failed:
    print("FAILED checks:", file=sys.stderr)
    for x in failed:
        print(" - " + x, file=sys.stderr)
    raise SystemExit(1)
