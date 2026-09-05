#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"
CONFIG = ROOT / "include/config.h"
AFSK_CPP = ROOT / "lib/LibAPRS_ESP32S3/AFSK.cpp"
AFSK_H = ROOT / "lib/LibAPRS_ESP32S3/AFSK.h"


def replace_once(path: Path, old: str, new: str, label: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"SKIP  {label} (already applied)")
        return False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 source match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"PATCH {label}")
    return True


def regex_replace(path: Path, pattern: str, repl, label: str, minimum: int = 1) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, repl, text, flags=re.MULTILINE)
    if count < minimum:
        print(f"SKIP  {label} (matches={count})")
        return 0
    path.write_text(new_text, encoding="utf-8")
    print(f"PATCH {label}: {count}")
    return count


def patch_main() -> None:
    runtime_profile = '''Configuration config;\n\n// T-TWR Plus Rev2.1 hardware profile.  Apply this after loading persistent\n// configuration so an old Rev2.0/default.cfg cannot restore unsafe GPIOs.\nstatic void applyTwrRev21HardwareProfile()\n{\n  config.rf_tx_gpio = 39;      // ESP32 -> SA868 UART\n  config.rf_rx_gpio = 48;      // SA868 -> ESP32 UART\n  config.rf_sql_gpio = 2;      // Rev2.1 hardware SQL, active LOW\n  config.rf_pd_gpio = 40;      // SA868 power-down control\n  config.rf_pwr_gpio = -1;     // GPIO38 is Rev2.0-only; never drive it on Rev2.1\n  config.rf_ptt_gpio = 41;\n  config.rf_sql_active = LOW;\n  config.rf_pd_active = HIGH;\n  config.rf_pwr_active = LOW;\n  config.adc_gpio = 1;         // SA868 audio -> ESP32 ADC\n  config.dac_gpio = 18;        // ESP32 AFSK -> SA868 audio\n  config.adc_sel_gpio = -1;\n  config.dac_sel_gpio = 17;    // audio mux\n}\n\n// Rev2.1 has no GPIO-controlled RF-power rail.  GPIO38 belongs to Rev2.0.\nstatic inline void rev21SetRfPower(bool highPower)\n{\n  (void)highPower;\n}\n'''
    replace_once(MAIN, "Configuration config;\n", runtime_profile,
                 "inject Rev2.1 runtime hardware profile")

    replace_once(
        MAIN,
        '  log_d("Start ESP32APRS_T-TWR V%s", String(VERSION).c_str());\n',
        '  applyTwrRev21HardwareProfile();\n'
        '  log_d("[REV2.1] HW profile: UART TX=39 RX=48 SQL=2 PD=40 PTT=41 ADC=1 DAC=18 MUX=17 RF_PWR=disabled");\n'
        '  log_d("Start ESP32APRS_T-TWR V%s", String(VERSION).c_str());\n',
        "force Rev2.1 profile after persistent config load",
    )

    defaults = {
        "  config.rf_sql_gpio = -1;\n": "  config.rf_sql_gpio = 2; // T-TWR Rev2.1 SQL, active LOW\n",
        "  config.rf_pwr_gpio = 38;\n": "  config.rf_pwr_gpio = -1; // GPIO38 is Rev2.0-only\n",
    }
    for old, new in defaults.items():
        replace_once(MAIN, old, new, "Rev2.1 default RF GPIO")

    replace_once(
        MAIN,
        '''void setupPowerRF(bool sts)\n{\n  // bool result = PMU.begin(Wire, AXP2101_SLAVE_ADDRESS, I2C_SDA, I2C_SCL);\n  // if (result == false) {\n  //     while (1) {\n  //         Serial.println("PMU is not online...");\n  //         delay(500);\n  //     }\n  // }\n  //! DC3 Radio Pixels VDD , Don't change\n  if(sts){\n    PMU.setDC3Voltage(3400);\n    PMU.enableDC3();\n  }else{\n    PMU.disableDC3();\n  }\n}\n''',
        '''void setupPowerRF(bool sts)\n{\n  // T-TWR Rev2.1: the SA868 rail is not on AXP2101 DC3.\n  // Radio on/off is controlled only by SA868_PD_PIN (GPIO40).\n  (void)sts;\n}\n''',
        "remove Rev2.0 DC3 radio switching",
    )

    replace_once(MAIN, "  PMU.setBLDO1Voltage(3300);\n",
                 "  PMU.setBLDO1Voltage(2000); // LilyGO Rev2.1 beginPower() reference value\n",
                 "set Rev2.1 microphone rail voltage")

    # DC3 is unused on Rev2.1.  Remove every active DC3 enable/disable/set call,
    # including low-power wake/sleep paths inherited from Rev2.0.
    regex_replace(MAIN, r"^(\s*)PMU\.setDC3Voltage\([^\n]+\);\s*$",
                  r"\1// Rev2.1: DC3 unused; do not configure it.", "remove active DC3 voltage writes", 1)
    regex_replace(MAIN, r"^(\s*)PMU\.enableDC3\(\);\s*$",
                  r"\1// Rev2.1: DC3 unused; keep disabled.", "remove active DC3 enables", 1)
    regex_replace(MAIN, r"^(\s*)PMU\.disableDC3\(\);\s*$",
                  r"\1// Rev2.1: DC3 unused; no radio control through this rail.", "remove active DC3 disables", 1)

    # GPIO38 is a Rev2.0-only RF pin.  Remove both direct and POWER_PIN aliases.
    regex_replace(MAIN, r"^(\s*)pinMode\(SA868_PWR_PIN,\s*OUTPUT\);\s*$",
                  r"\1// Rev2.1: GPIO38 is not an RF-power control.", "remove GPIO38 pinMode", 1)
    regex_replace(MAIN, r"^(\s*)digitalWrite\(SA868_PWR_PIN,\s*[^\n]+\);\s*(?://.*)?$",
                  r"\1// Rev2.1: GPIO38 write removed.", "remove direct GPIO38 writes", 1)
    regex_replace(MAIN, r"^(\s*)pinMode\(POWER_PIN,\s*[^\n]+\);\s*(?://.*)?$",
                  r"\1// Rev2.1: legacy POWER_PIN pinMode removed.", "remove legacy POWER_PIN pinMode", 0)
    regex_replace(MAIN, r"^(\s*)digitalWrite\(POWER_PIN,\s*([^\n;]+)\);(.*)$",
                  r"\1rev21SetRfPower(\2);\3", "replace legacy GPIO38 power writes", 1)

    # Avoid the legacy user-TWDT configuration watching IDLE0.  The historical
    # reboot report shows IDLE0 starved while taskAPRSPoll is on Core0.
    replace_once(
        MAIN,
        '''  esp_task_wdt_config_t twdt_config = {\n    .timeout_ms = 30000, // 30 seconds\n    .idle_core_mask = (1 << portNUM_PROCESSORS) - 1,    // Bitmask of all cores\n    .trigger_panic = false,\n  };\nesp_task_wdt_init(&twdt_config);\nprintf("TWDT initialized\\n");\nesp_task_wdt_add(NULL);\nesp_task_wdt_status(NULL);\n''',
        '''  esp_task_wdt_config_t twdt_config = {\n    .timeout_ms = 30000, // 30 seconds\n    .idle_core_mask = 0, // Do not subscribe IDLE0/IDLE1 to the user TWDT\n    .trigger_panic = false,\n  };\n  esp_err_t twdt_rc = esp_task_wdt_reconfigure(&twdt_config);\n  if (twdt_rc == ESP_ERR_INVALID_STATE)\n    twdt_rc = esp_task_wdt_init(&twdt_config);\n  printf("[REV2.1] TWDT configure rc=%d\\n", (int)twdt_rc);\n  if (esp_task_wdt_status(NULL) != ESP_OK)\n    esp_task_wdt_add(NULL);\n''',
        "make TWDT initialization idempotent and stop watching idle cores",
    )


def patch_config() -> None:
    replacements = {
        "\tint8_t rf_tx_gpio = 48;\n": "\tint8_t rf_tx_gpio = 39; // T-TWR Rev2.1 ESP32->SA868 UART\n",
        "\tint8_t rf_rx_gpio = 39;\n": "\tint8_t rf_rx_gpio = 48; // T-TWR Rev2.1 SA868->ESP32 UART\n",
        "\tint8_t rf_sql_gpio = 33;\n": "\tint8_t rf_sql_gpio = 2;  // T-TWR Rev2.1 SQL, active LOW\n",
        "\tint8_t rf_pwr_gpio = 38;\n": "\tint8_t rf_pwr_gpio = -1; // GPIO38 is Rev2.0-only\n",
    }
    for old, new in replacements.items():
        replace_once(CONFIG, old, new, "fix Configuration Rev2.1 defaults")


def patch_afsk() -> None:
    replace_once(AFSK_CPP,
                 "int8_t _sql_pin = 38, _ptt_pin = 41, _pwr_pin, _dac_pin = 18, _adc_pin = 1;\n",
                 "int8_t _sql_pin = -1, _ptt_pin = 41, _pwr_pin = -1, _dac_pin = 18, _adc_pin = 1;\n",
                 "remove Rev2.0 AFSK SQL/power defaults")

    replace_once(
        AFSK_CPP,
        '''bool getReceive()\n{\n  bool ret = false;\n  if ((digitalRead(_ptt_pin) ^ _ptt_active) == 0) // signal active with ptt_active\n    return false;                                 // PTT Protection receive\n  if (digitalRead(LED_RX_PIN))                    // Check RX LED receiving.\n    ret = true;\n  return ret;\n}\n''',
        '''bool getReceive()\n{\n  if (_ptt_pin > -1 && ((digitalRead(_ptt_pin) ^ _ptt_active) == 0))\n    return false; // PTT protection\n\n  // Rev2.1 exposes SA868 SQL on GPIO2.  LOW means the radio is receiving.\n  if (_sql_pin > -1)\n    return ((digitalRead(_sql_pin) ^ _sql_active) == 0);\n\n  return ModemDcdState() != 0;\n}\n''',
        "use Rev2.1 SQL for receive state",
    )

    replace_once(AFSK_CPP, "  tp->cdt_led_pin = 2;\n",
                 "  tp->cdt_led_pin = -1; // GPIO2 is Rev2.1 SQL, not an LED\n",
                 "remove GPIO2 fake DCD LED")
    replace_once(AFSK_CPP, "  tp->cdt_led_on = 2;\n",
                 "  tp->cdt_led_on = 0;\n",
                 "disable fake DCD LED state")

    replace_once(AFSK_H, "#define LED_RX_PIN 2\n#define LED_TX_PIN 4\n",
                 "#define LED_RX_PIN (-1) // Rev2.1 GPIO2 is SA868 SQL\n#define LED_TX_PIN (-1) // Rev2.1 GPIO4 is PMU IRQ\n",
                 "remove Rev2.1 SQL/PMU IRQ LED aliases")
    regex_replace(AFSK_H, r"^\s*digitalWrite\(LED_TX_PIN,(?:HIGH|LOW)\);\\\s*$", "",
                  "remove GPIO4 writes from AFSK IRQ macros", 1)


def main() -> int:
    for p in (MAIN, CONFIG, AFSK_CPP, AFSK_H):
        if not p.exists():
            print(f"ERROR missing {p.relative_to(ROOT)}", file=sys.stderr)
            return 2
    patch_main()
    patch_config()
    patch_afsk()
    print("T-TWR Rev2.1 hardware port applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
