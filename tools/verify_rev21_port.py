#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
m = (ROOT / "src/main.cpp").read_text(encoding="utf-8")
mh = (ROOT / "include/main.h").read_text(encoding="utf-8")
c = (ROOT / "include/config.h").read_text(encoding="utf-8")
a = (ROOT / "lib/LibAPRS_ESP32S3/AFSK.cpp").read_text(encoding="utf-8")
ah = (ROOT / "lib/LibAPRS_ESP32S3/AFSK.h").read_text(encoding="utf-8")
pio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
board = (ROOT / "boards/LilyGo-T-TWR-Plus.json").read_text(encoding="utf-8")

checks = []
def expect(name, condition):
    checks.append((name, bool(condition)))

def no_active(pattern, text):
    return re.search(pattern, text, flags=re.MULTILINE) is None

# Rev2.1 fixed pin/profile invariants.
expect("runtime hardware profile", "applyTwrRev21HardwareProfile()" in m)
expect("UART TX39 RX48", "config.rf_tx_gpio = 39;" in m and "config.rf_rx_gpio = 48;" in m)
expect("SQL GPIO2 active LOW", "config.rf_sql_gpio = 2;" in m and "config.rf_sql_active = LOW;" in m)
expect("PTT GPIO41 active LOW", "config.rf_ptt_gpio = 41;" in m and "config.rf_ptt_active = LOW;" in m)
expect("factory PTT active LOW", "config.rf_ptt_active = 0;" in m and "config.rf_ptt_active = 1;" not in m)
expect("PD GPIO40 active HIGH", "config.rf_pd_gpio = 40;" in m and "config.rf_pd_active = HIGH;" in m)
expect("GPIO38 RF selector disabled", "config.rf_pwr_gpio = -1;" in m and "rf_pwr_gpio = -1" in c)
expect("APRS ADC GPIO1", "config.adc_gpio = 1;" in m)
expect("APRS DAC GPIO18", "config.dac_gpio = 18;" in m)
expect("audio select GPIO17", "config.dac_sel_gpio = 17;" in m)
expect("I2C GPIO8/9 400kHz", "config.i2c_sda_pin = 8;" in m and "config.i2c_sck_pin = 9;" in m and "config.i2c_freq = 400000;" in m)
expect("extra Rev2.1 pins", all(x in mh for x in ["#define ESP32_PWM_TONE (45)", "#define ESP_MIC_ADC (15)", "#define SA868_SQL (2)", "#define AUDIO_SELECT_PIN (17)"]))

# Radio electrical behavior.
expect("MIC_CTRL normal runtime push-pull OUTPUT", "pinMode(SA868_MIC_SEL, OUTPUT); // Rev2.1 normal-runtime MIC_CTRL routing" in m)
expect("MIC_CTRL normal route LOW", "digitalWrite(SA868_MIC_SEL, LOW); // normal microphone/radio path" in m)
expect("AFSK TX audio route HIGH", "digitalWrite(17, HIGH);" in a)
expect("AFSK RX audio route LOW", "digitalWrite(17, LOW);" in a)
expect("boot PTT HIGH idle", "digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 idle/RX; PTT is active LOW" in m)
expect("AFSK PTT fallback active LOW", "_ptt_active = LOW" in a)
expect("AFSK PTT never open drain", "pinMode(_ptt_pin, OUTPUT_OPEN_DRAIN);" not in a)
expect("PTT TX push-pull LOW", "push-pull LOW=TX" in a)
expect("PTT idle push-pull HIGH", "push-pull HIGH=RX/idle" in a)
expect("radio sleep safe PTT", "digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 RX/idle before radio sleep" in m)
expect("radio sleep safe audio", "digitalWrite(SA868_MIC_SEL, LOW);  // normal microphone/radio audio route" in m)
expect("radio recovery safe PTT", "digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 RX/idle before recovery cycle" in m)
expect("radio recovery safe audio", "digitalWrite(SA868_MIC_SEL, LOW);  // normal microphone/radio audio route" in m)

# SA868S power semantics and legacy GPIO38 removal.
expect("SA868S power bit HIGH0 LOW1", "return highPower ? 0 : 1;" in m)
expect("DMOSETGROUP uses rf_power", "rev21Sa868PowerBit(config.rf_power), config.freq_tx, config.freq_rx" in m)
expect("no GPIO38 SA868 direct write", no_active(r"^\s*digitalWrite\(SA868_PWR_PIN,", m))
expect("no GPIO38 SA868 pinMode", no_active(r"^\s*pinMode\(SA868_PWR_PIN,", m))
expect("no legacy POWER_PIN write", no_active(r"^\s*digitalWrite\(POWER_PIN,", m))

# AXP2101 Rev2.1 rail model.
expect("BLDO1 2.0V official init", "PMU.setBLDO1Voltage(2000)" in m)
expect("DC3 not configured/enabled", no_active(r"^\s*PMU\.setDC3Voltage\(", m) and no_active(r"^\s*PMU\.enableDC3\(\);", m))
expect("DC3 explicitly off", "PMU.disableDC3();" in m)
expect("unused DC5 ALDO1 off", "PMU.disableDC5();" in m and "PMU.disableALDO1();" in m)
expect("ALDO3 radio-to-amp default off", "PMU.disableALDO3();" in m)
expect("unused BLDO2 DLDO1 off", "PMU.disableBLDO2();" in m and "PMU.disableDLDO1();" in m)
expect("SD GNSS MIC rails on", "PMU.enableALDO2();" in m and "PMU.enableALDO4();" in m and "PMU.enableBLDO1();" in m)
expect("truthful PMU diagnostics", 'log_d("PMU is not online...")' not in m and "PMU init failed, retry" in m)

# Sleep/wake power safety.
expect("Mode A/B wake rails normalized", m.count("PMU.disableALDO3(); // Rev2.1 Radio -> onboard amplifier") == 2)
expect("Mode A/B wake SD GNSS MIC", m.count("PMU.enableALDO2();  // SD") == 2 and m.count("PMU.enableALDO4();  // GNSS") == 2 and m.count("PMU.enableBLDO1();  // Microphone") == 2)
expect("deep sleep PTT idle first", "digitalWrite(config.rf_ptt_gpio, HIGH); // Rev2.1 PTT idle/RX" in m)
expect("deep sleep audio normal first", "digitalWrite(config.dac_sel_gpio, LOW); // normal radio/mic audio route" in m)
expect("deep sleep PD asserted", "digitalWrite(config.rf_pd_gpio, LOW);   // SA868 power-down" in m)
expect("no active unsupported ALL_LOW ext1", no_active(r"^\s*esp_sleep_enable_ext1_wakeup\([^;\n]*ESP_EXT1_WAKEUP_ALL_LOW", m))
expect("no active zero-mask ext1", no_active(r"^\s*esp_sleep_enable_ext1_wakeup\(0x0", m))
expect("Mode C timer wake retained", "esp_sleep_enable_timer_wakeup((uint64_t)config.pwr_sleep_interval * uS_TO_S_FACTOR);" in m)
expect("Mode C timer-only documented", "ESP32-S3 Rev2.1 Mode C is timer-wake only" in m)

# Native Rev2.1 SH1106 OLED on the PMU-initialized shared I2C bus.
expect("native Rev2.1 SH1106 OLED", "Adafruit_SH1106G display(" in m and "display.begin(oled_addr, false);" in m)
expect("OLED shared bus stays 400kHz", "Adafruit_SH1106G display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1, 400000, 400000);" in m)
expect("legacy SSD1306 driver removed", '#include "Adafruit_SSD1306.h"' not in m and "display.begin(SSD1306_SWITCHCAPVCC" not in "\n".join(line for line in m.splitlines() if not line.lstrip().startswith("//")))

# Runtime stability and diagnostics.
expect("TWDT framework managed", "[REV2.1] TWDT framework-managed" in m)
expect("no app TWDT reset", no_active(r"^\s*esp_task_wdt_reset\(\);", m))
expect("no app TWDT reconfigure", no_active(r"^\s*esp_task_wdt_reconfigure\(", m))
expect("no app TWDT init", no_active(r"^\s*esp_task_wdt_init\(", m))
expect("charge current guarded once", m.count("Charge current enum %u is outside legacy display table") == 1)
expect("charge voltage guarded", "Charge voltage enum %u is outside legacy display table" in m)

# Official LilyGO PlatformIO hardware model, retaining project OTA layout.
expect("local board directory", "boards_dir = boards" in pio)
expect("LilyGo T-TWR Plus board", "board = LilyGo-T-TWR-Plus" in pio)
expect("QIO flash", "board_build.flash_mode = qio" in pio and '"flash_mode": "qio"' in board)
expect("QIO OPI memory", "board_build.arduino.memory_type = qio_opi" in pio and '"memory_type": "qio_opi"' in board)
expect("16MB flash profile", '"flash_size": "16MB"' in board)
expect("OTA partitions retained", "board_build.partitions = partitions.csv" in pio)
expect("NeoPixel 1.12.3 pinned", "adafruit/Adafruit NeoPixel@1.12.3" in pio)
expect("SH1106 dependency pinned", "adafruit/Adafruit SH110X@2.1.14" in pio)

# Static library/default safety.
expect("config TX39 RX48", "rf_tx_gpio = 39" in c and "rf_rx_gpio = 48" in c)
expect("config SQL2", "rf_sql_gpio = 2" in c)
expect("config PTT41 active LOW", "rf_ptt_gpio = 41" in c and "rf_ptt_active = 0" in c)
expect("AFSK no Rev2.0 SQL default", "int8_t _sql_pin = -1" in a)
expect("AFSK getReceive uses SQL", "return ((digitalRead(_sql_pin) ^ _sql_active) == 0);" in a)
expect("GPIO2 not RX LED", "#define LED_RX_PIN (-1)" in ah)
expect("GPIO4 not TX LED", "#define LED_TX_PIN (-1)" in ah)
expect("AFSK IRQ no GPIO4 LED write", "digitalWrite(LED_TX_PIN" not in ah)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + "  " + name)
print(f"\n{len(checks)-len(failed)}/{len(checks)} checks passed")
if failed:
    print("FAILED checks:")
    for name in failed:
        print(" - " + name)
    raise SystemExit(1)
