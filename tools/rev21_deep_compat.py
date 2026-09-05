#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"
WEB = ROOT / "src/webservice.cpp"
PIO = ROOT / "platformio.ini"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"ERROR: {label}: expected source pattern not found")
    return text.replace(old, new, 1)


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    # Rev2.1 carries a 1.3-inch SH1106 128x64 OLED.  The I2C address alone
    # does not identify the controller, so use a native SH1106 driver.
    text = replace_once(
        text,
        '#include "Adafruit_SSD1306.h"',
        '#include <Adafruit_SH110X.h>',
        "SH1106 include",
    )
    text = replace_once(
        text,
        'Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);',
        'Adafruit_SH1106G display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1, 400000, 400000);',
        "SH1106 display object",
    )
    text = replace_once(
        text,
        '  // periphBegin=false prevents Adafruit_SSD1306 from calling Wire.begin() again.\n'
        '  display.begin(SSD1306_SWITCHCAPVCC, oled_addr, false, false);',
        '  // SH1106 uses the PMU-initialized shared Wire bus. Keep reset disabled because\n'
        '  // the module has no dedicated OLED reset GPIO. The constructor restores 400 kHz\n'
        '  // after transfers so the shared Rev2.1 I2C bus keeps its configured clock.\n'
        '  display.begin(oled_addr, false);',
        "SH1106 initialization",
    )

    # Mode B deletes the sensor/network tasks before light sleep.  A deleted
    # FreeRTOS task handle must never be resumed or retained as a live handle.
    old_sensor_delete = '                        vTaskDelete(taskSensorHandle);'
    new_sensor_delete = (
        '                        if (taskSensorHandle != nullptr)\n'
        '                        {\n'
        '                            vTaskDelete(taskSensorHandle);\n'
        '                            taskSensorHandle = nullptr;\n'
        '                        }'
    )
    if new_sensor_delete not in text:
        if old_sensor_delete not in text:
            raise SystemExit("ERROR: Mode B sensor delete pattern not found")
        # Only the Mode B delete site uses vTaskDelete(taskSensorHandle).
        text = text.replace(old_sensor_delete, new_sensor_delete, 1)

    old_network_delete = '                        vTaskDelete(taskNetworkHandle);'
    new_network_delete = (
        '                        if (taskNetworkHandle != nullptr)\n'
        '                        {\n'
        '                            vTaskDelete(taskNetworkHandle);\n'
        '                            taskNetworkHandle = nullptr;\n'
        '                        }'
    )
    if new_network_delete not in text:
        if old_network_delete not in text:
            raise SystemExit("ERROR: Mode B network delete pattern not found")
        text = text.replace(old_network_delete, new_network_delete, 1)

    mode_b_marker = 'log_d("System to light sleep Mode B %d Sec", config.pwr_sleep_interval);'
    marker = text.find(mode_b_marker)
    if marker < 0:
        raise SystemExit("ERROR: Mode B sleep marker not found")
    stale_resume = '                        vTaskResume(taskSensorHandle);'
    stale = text.find(stale_resume, marker)
    if stale >= 0:
        replacement = (
            '                        // Mode B deleted taskSensor before light sleep; it is recreated below.\n'
            '                        // Never resume a deleted/stale FreeRTOS task handle.'
        )
        text = text[:stale] + replacement + text[stale + len(stale_resume):]

    # Leave the valid Mode A suspend/resume pair intact.
    if text.count('vTaskResume(taskSensorHandle);') != 1:
        raise SystemExit("ERROR: expected exactly one valid Mode A taskSensor resume after patch")

    MAIN.write_text(text, encoding="utf-8")


def patch_web() -> None:
    text = WEB.read_text(encoding="utf-8")

    helper = '''
// T-TWR Plus Rev2.1 has a fixed radio/audio wiring topology.  The legacy
// generic MOD page still exposes GPIO fields, but those values must never be
// allowed to re-route live Rev2.1 hardware (GPIO2 is SQL, GPIO4 is PMU IRQ,
// and GPIO38 is not the Rev2.1 RF power selector).
static void enforceRev21RadioHardwareProfile()
{
    config.rf_tx_gpio = 39;
    config.rf_rx_gpio = 48;
    config.rf_sql_gpio = 2;
    config.rf_pd_gpio = 40;
    config.rf_pwr_gpio = -1;
    config.rf_ptt_gpio = 41;
    config.rf_sql_active = LOW;
    config.rf_pd_active = HIGH;
    config.rf_pwr_active = LOW;
    config.rf_ptt_active = LOW;
}
'''
    anchor = 'bool defaultSetting = false;\n'
    if 'static void enforceRev21RadioHardwareProfile()' not in text:
        if anchor not in text:
            raise SystemExit("ERROR: webservice helper insertion anchor not found")
        text = text.replace(anchor, anchor + helper, 1)

    old = '''\t\tconfig.rf_en = radioEnable;
\t\tString html = "OK";
\t\trequest->send(200, "text/html", html); // send to someones browser when asked
\t\tsaveConfiguration("/default.cfg", config);
\t\tRF_INIT = true;'''
    new = '''\t\tconfig.rf_en = radioEnable;
\t\t// Rev2.1 radio GPIOs/polarities are board wiring, not user configuration.
\t\t// Normalize before persisting and before RF_INIT can reprogram live hardware.
\t\tenforceRev21RadioHardwareProfile();
\t\tString html = "OK";
\t\trequest->send(200, "text/html", html); // send to someones browser when asked
\t\tsaveConfiguration("/default.cfg", config);
\t\tRF_INIT = true;'''
    text = replace_once(text, old, new, "web radio safety normalization")

    WEB.write_text(text, encoding="utf-8")


def patch_platformio() -> None:
    text = PIO.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'adafruit/Adafruit SSD1306@^2.5.7',
        'adafruit/Adafruit SH110X@2.1.14',
        "SH1106 PlatformIO dependency",
    )
    PIO.write_text(text, encoding="utf-8")


def main() -> None:
    patch_main()
    patch_web()
    patch_platformio()
    print("PASS Rev2.1 deep compatibility patch applied/idempotent")


if __name__ == "__main__":
    main()
