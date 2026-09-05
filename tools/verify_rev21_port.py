#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
files = {
    "main": (ROOT / "src/main.cpp").read_text(encoding="utf-8"),
    "main_h": (ROOT / "include/main.h").read_text(encoding="utf-8"),
    "config": (ROOT / "include/config.h").read_text(encoding="utf-8"),
    "afsk_cpp": (ROOT / "lib/LibAPRS_ESP32S3/AFSK.cpp").read_text(encoding="utf-8"),
    "afsk_h": (ROOT / "lib/LibAPRS_ESP32S3/AFSK.h").read_text(encoding="utf-8"),
    "pio": (ROOT / "platformio.ini").read_text(encoding="utf-8"),
    "board": (ROOT / "boards/LilyGo-T-TWR-Plus.json").read_text(encoding="utf-8"),
}

checks = []
def expect(name, cond):
    checks.append((name, bool(cond)))

def no_active(pattern, text):
    return re.search(pattern, text, flags=re.MULTILINE) is None

m = files["main"]
mh = files["main_h"]
c = files["config"]
a = files["afsk_cpp"]
ah = files["afsk_h"]
pio = files["pio"]
board = files["board"]

# Fixed Rev2.1 hardware invariants.
expect("runtime Rev2.1 profile present", "applyTwrRev21HardwareProfile()" in m)
expect("Rev2.1 SQL GPIO2 forced", "config.rf_sql_gpio = 2;" in m)
expect("Rev2.1 PTT GPIO41 forced", "config.rf_ptt_gpio = 41;" in m)
expect("Rev2.1 PTT active LOW forced", "config.rf_ptt_active = LOW;" in m)
expect("factory-default PTT polarity is not active HIGH", "config.rf_ptt_active = 1;" not in m)
expect("factory-default PTT polarity active LOW", "config.rf_ptt_active = 0;" in m)
expect("Rev2.1 RF power GPIO disabled", "config.rf_pwr_gpio = -1;" in m)
expect("audio ADC GPIO1 forced", "config.adc_gpio = 1;" in m)
expect("audio DAC GPIO18 forced", "config.dac_gpio = 18;" in m)
expect("audio mux GPIO17 forced", "config.dac_sel_gpio = 17;" in m)
expect("I2C SDA/SCL forced to GPIO8/GPIO9", "config.i2c_sda_pin = 8;" in m and "config.i2c_sck_pin = 9;" in m)
expect("I2C target frequency forced to 400kHz", "config.i2c_freq = 400000;" in m)
expect("official Rev2.1 extra pins defined",
       "#define ESP32_PWM_TONE (45)" in mh and
       "#define ESP_MIC_ADC (15)" in mh and
       "#define SA868_SQL (2)" in mh and
       "#define AUDIO_SELECT_PIN (17)" in mh)

# Audio/PTT direction and electrical mode.
expect("AFSK TX selects ESP-to-radio audio path", "digitalWrite(17, HIGH);" in a)
expect("AFSK RX restores normal radio audio path", "digitalWrite(17, LOW);" in a)
expect("MIC_CTRL uses official Rev2.1 open-drain routing", "pinMode(SA868_MIC_SEL, OUTPUT_OPEN_DRAIN);" in m)
expect("SA868 boot holds PTT HIGH idle", "digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 idle/RX; PTT is active LOW" in m)
expect("AFSK fallback PTT polarity active LOW", "_ptt_active = LOW" in a)
expect("Rev2.1 PTT no longer depends on open-drain pull-up", "pinMode(_ptt_pin, OUTPUT_OPEN_DRAIN);" not in a)
expect("Rev2.1 active-low TX uses push-pull LOW", "push-pull LOW=TX" in a)
expect("Rev2.1 idle uses push-pull HIGH", "push-pull HIGH=RX/idle" in a)

# Generic radio sleep/recovery ordering must deassert PTT, restore normal audio,
# then assert PD. These are separate from Mode-C deep-sleep ordering below.
expect("RF_MODULE_SLEEP deasserts PTT before PD", "digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 RX/idle before radio sleep" in m)
expect("RF_MODULE_SLEEP restores normal audio before PD", "digitalWrite(SA868_MIC_SEL, LOW);  // normal microphone/radio audio route" in m)
expect("RF recovery deasserts PTT before PD cycle", "digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 RX/idle before recovery cycle" in m)
expect("RF recovery restores normal audio before PD cycle", "digitalWrite(SA868_MIC_SEL, LOW);  // normal microphone/radio audio route" in m)

# Rev2.1 SA868S RF power is encoded in DMOSETGROUP (0=HIGH, 1=LOW), not GPIO38.
expect("Rev2.1 SA868S power-bit helper present", "return highPower ? 0 : 1;" in m)
expect("SA868 DMOSETGROUP uses rf_power mapping",
       "rev21Sa868PowerBit(config.rf_power), config.freq_tx, config.freq_rx" in m)
expect("GPIO38 direct writes removed", no_active(r"^\s*digitalWrite\(SA868_PWR_PIN,", m))
expect("GPIO38 direct pinMode removed", no_active(r"^\s*pinMode\(SA868_PWR_PIN,", m))
expect("legacy POWER_PIN writes removed", no_active(r"^\s*digitalWrite\(POWER_PIN,", m))

# LilyGO Rev2.1 PMU baseline: radio is battery-fed/PD-controlled; only SD, GNSS,
# microphone rails are enabled by the base firmware. ALDO3 OFF selects radio->amp.
expect("BLDO1 follows LilyGO 2.0V init", "PMU.setBLDO1Voltage(2000)" in m)
expect("DC3 has no active enable", no_active(r"^\s*PMU\.enableDC3\(\);", m))
expect("DC3 has no active voltage set", no_active(r"^\s*PMU\.setDC3Voltage\(", m))
expect("Rev2.1 PMU explicitly disables DC3", "PMU.disableDC3();" in m)
expect("Rev2.1 PMU disables unused DC5/ALDO1", "PMU.disableDC5();" in m and "PMU.disableALDO1();" in m)
expect("Rev2.1 radio speaker route keeps ALDO3 off", "PMU.disableALDO3();" in m)
expect("Rev2.1 PMU disables unused BLDO2/DLDO1", "PMU.disableBLDO2();" in m and "PMU.disableDLDO1();" in m)
expect("Rev2.1 SD/GNSS/MIC rails enabled", "PMU.enableALDO2();" in m and "PMU.enableALDO4();" in m and "PMU.enableBLDO1();" in m)
expect("false pre-attempt PMU offline log removed", 'log_d("PMU is not online...")' not in m)

# Sleep/wake must preserve the same Rev2.1 power-domain semantics. Two legacy wake
# paths (Mode A and Mode B) are marked with this Rev2.1 ALDO3 line after patching.
expect("Mode A/B wake rails normalized",
       m.count("PMU.disableALDO3(); // Rev2.1 Radio -> onboard amplifier") == 2)
expect("wake paths restore only SD/GNSS/MIC baseline",
       m.count("PMU.enableALDO2();  // SD") == 2 and
       m.count("PMU.enableALDO4();  // GNSS") == 2 and
       m.count("PMU.enableBLDO1();  // Microphone") == 2)
expect("deep sleep deasserts PTT before radio PD",
       "digitalWrite(config.rf_ptt_gpio, HIGH); // Rev2.1 PTT idle/RX" in m)
expect("deep sleep restores normal audio route before radio PD",
       "digitalWrite(config.dac_sel_gpio, LOW); // normal radio/mic audio route" in m)
expect("deep sleep then asserts SA868 power-down",
       "digitalWrite(config.rf_pd_gpio, LOW);   // SA868 power-down" in m)
expect("ESP32-S3 Mode C does not use unsupported ALL_LOW wake", "ESP_EXT1_WAKEUP_ALL_LOW" not in m)
expect("ESP32-S3 Mode C does not configure zero-mask EXT1 wake", "esp_sleep_enable_ext1_wakeup(0x0" not in m)
expect("Mode C retains timer wake source",
       "esp_sleep_enable_timer_wakeup((uint64_t)config.pwr_sleep_interval * uS_TO_S_FACTOR);" in m)
expect("Mode C timer-only wake is documented", "ESP32-S3 Rev2.1 Mode C is timer-wake only" in m)

# Watchdog remains framework-owned.
expect("TWDT framework-managed", "[REV2.1] TWDT framework-managed" in m)
expect("no active application TWDT reset", no_active(r"^\s*esp_task_wdt_reset\(\);", m))
expect("no active TWDT reconfigure", no_active(r"^\s*esp_task_wdt_reconfigure\(", m))
expect("no active TWDT init", no_active(r"^\s*esp_task_wdt_init\(", m))

# Diagnostics must not perform out-of-bounds table reads.
expect("charge-current table guarded", "Charge current enum %u is outside legacy display table" in m)
expect("charge-current guard normalized once", m.count("Charge current enum %u is outside legacy display table") == 1)
expect("charge-voltage table guarded", "Charge voltage enum %u is outside legacy display table" in m)

# PlatformIO hardware model follows LilyGO's official board definition while retaining
# this firmware's OTA/LittleFS partitions.csv layout.
expect("repository boards_dir enabled", "boards_dir = boards" in pio)
expect("official LilyGO board selected", "board = LilyGo-T-TWR-Plus" in pio)
expect("QIO flash selected", "board_build.flash_mode = qio" in pio and '"flash_mode": "qio"' in board)
expect("OPI PSRAM/QIO memory type selected", "board_build.arduino.memory_type = qio_opi" in pio and '"memory_type": "qio_opi"' in board)
expect("16MB flash board profile", '"flash_size": "16MB"' in board)
expect("project OTA partition table retained", "board_build.partitions = partitions.csv" in pio)
expect("NeoPixel pinned to ESP32-S3-compatible 1.12.3", "adafruit/Adafruit NeoPixel@1.12.3" in pio)

# Library/default safety.
expect("config defaults TX39/RX48", "rf_tx_gpio = 39" in c and "rf_rx_gpio = 48" in c)
expect("config defaults SQL2", "rf_sql_gpio = 2" in c)
expect("config defaults PTT41 active LOW", "rf_ptt_gpio = 41" in c and "rf_ptt_active = 0" in c)
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
