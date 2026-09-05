#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"
GUI_H = ROOT / "include/gui_lcd.h"
GUI_CPP = ROOT / "src/gui_lcd.cpp"
SENSOR = ROOT / "src/sensor.cpp"
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
    text = replace_once(text, '#include "Adafruit_SSD1306.h"', '#include <Adafruit_SH110X.h>', "SH1106 include")
    text = replace_once(text, 'Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);', 'Adafruit_SH1106G display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1, 400000, 400000);', "SH1106 display object")
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

    # SSD1306::dim() does not exist on Adafruit_SH1106G. Preserve the original
    # sleep/wake semantics through the controller-independent contrast API.
    text = text.replace('display.dim(true);', 'display.setContrast(0x00);')
    text = text.replace('display.dim(false);', 'display.setContrast(0xFF);')

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
    if text.count('vTaskResume(taskSensorHandle);') != 1:
        raise SystemExit("ERROR: expected exactly one valid Mode A taskSensor resume after patch")

    MAIN.write_text(text, encoding="utf-8")


def patch_gui_header() -> None:
    text = GUI_H.read_text(encoding="utf-8")
    text = replace_once(text, '#include "Adafruit_SSD1306.h"', '#include <Adafruit_SH110X.h>', "GUI SH1106 include")
    text = replace_once(text, 'extern Adafruit_SSD1306 display;', 'extern Adafruit_SH1106G display;', "GUI SH1106 display declaration")

    alias_anchor = '#include <Adafruit_SH110X.h>\n'
    alias_block = '''#include <Adafruit_SH110X.h>
#ifndef BLACK
#define BLACK SH110X_BLACK
#endif
#ifndef WHITE
#define WHITE SH110X_WHITE
#endif
'''
    if alias_block not in text:
        if alias_anchor not in text:
            raise SystemExit("ERROR: SH1106 include anchor missing for color aliases")
        text = text.replace(alias_anchor, alias_block, 1)

    GUI_H.write_text(text, encoding="utf-8")


def patch_gui_cpp() -> None:
    text = GUI_CPP.read_text(encoding="utf-8")

    text = text.replace('display.dim(true);', 'display.setContrast(0x00);')
    text = text.replace('display.dim(false);', 'display.setContrast(0xFF);')
    text = text.replace('display.ssd1306_command(SSD1306_SETCONTRAST);', 'display.setContrast((uint8_t)config.contrast);')
    text = text.replace('display.ssd1306_command(config.contrast);', '')

    # 0xE4 is not a defined SH1106 command. The legacy code sent it immediately
    # before clearing/redrawing the monitor screen, so omit the undefined command.
    text = text.replace('display.ssd1306_command(0xE4);', '')
    text = text.replace('display.oled_command(0xE4);', '')

    text = text.replace('// display.ssd1306_command(SSD1306_SETPRECHARGE);                  // 0xd9', '// SH1106 contrast is handled with display.setContrast()')
    text = text.replace('// display.ssd1306_command(SSD1306_SETVCOMDETECT);                 // 0xDB', '')

    had_final_newline = text.endswith('\n')
    text = '\n'.join(line.rstrip() for line in text.splitlines())
    if had_final_newline:
        text += '\n'

    active_lines = [line for line in text.splitlines() if not line.lstrip().startswith('//')]
    active = '\n'.join(active_lines)
    if ('display.dim(' in active or 'display.ssd1306_command(' in active or
            'SSD1306_SETCONTRAST' in active or 'oled_command(0xE4)' in active):
        raise SystemExit("ERROR: SSD1306/undefined SH1106 GUI API remains after migration")

    GUI_CPP.write_text(text, encoding="utf-8")


def patch_sensor() -> None:
    text = SENSOR.read_text(encoding="utf-8")
    old = '        Wire.begin(config.i2c_sda_pin, config.i2c_sck_pin, config.i2c_freq);'
    new = (
        '        // Rev2.1 Wire is the shared AXP2101/SH1106 system bus and is already\n'
        '        // initialized by PMU.begin(). Do not restart/re-route it from sensor init.\n'
        '        Wire.setClock(400000);'
    )
    text = replace_once(text, old, new, "sensor shared-I2C reuse")
    SENSOR.write_text(text, encoding="utf-8")


def patch_web() -> None:
    text = WEB.read_text(encoding="utf-8")

    helper_old = '''
// T-TWR Plus Rev2.1 has fixed radio/audio wiring and a fixed system I2C bus.
// Legacy generic setup pages may expose these GPIO fields, but user input must
// never re-route live board hardware. GPIO2 is SQL, GPIO4 is PMU IRQ, GPIO38 is
// not the Rev2.1 RF power selector, and GPIO8/9 are the shared AXP2101/SH1106 bus.
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
    config.i2c_sda_pin = 8;
    config.i2c_sck_pin = 9;
    config.i2c_freq = 400000;
}
'''
    helper_new = '''
// T-TWR Plus Rev2.1 has fixed radio/audio wiring and a fixed system I2C bus.
// Legacy generic setup pages may expose these GPIO fields, but user input must
// never re-route live board hardware. GPIO2 is SQL, GPIO4 is PMU IRQ, GPIO38 is
// not the Rev2.1 RF power selector, and GPIO8/9 are the shared AXP2101/SH1106 bus.
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
    config.i2c_enable = true;
    config.i2c_sda_pin = 8;
    config.i2c_sck_pin = 9;
    config.i2c_freq = 400000;
}
'''
    anchor = 'bool defaultSetting = false;\n'
    if helper_new not in text:
        if helper_old in text:
            text = text.replace(helper_old, helper_new, 1)
        elif 'static void enforceRev21RadioHardwareProfile()' not in text:
            if anchor not in text:
                raise SystemExit("ERROR: webservice helper insertion anchor not found")
            text = text.replace(anchor, anchor + helper_new, 1)
        else:
            raise SystemExit("ERROR: unexpected Rev2.1 hardware helper; refusing blind edit")

    old_radio = '''\t\tconfig.rf_en = radioEnable;
\t\tString html = "OK";
\t\trequest->send(200, "text/html", html); // send to someones browser when asked
\t\tsaveConfiguration("/default.cfg", config);
\t\tRF_INIT = true;'''
    new_radio = '''\t\tconfig.rf_en = radioEnable;
\t\t// Rev2.1 radio GPIOs/polarities are board wiring, not user configuration.
\t\t// Normalize before persisting and before RF_INIT can reprogram live hardware.
\t\tenforceRev21RadioHardwareProfile();
\t\tString html = "OK";
\t\trequest->send(200, "text/html", html); // send to someones browser when asked
\t\tsaveConfiguration("/default.cfg", config);
\t\tRF_INIT = true;'''
    text = replace_once(text, old_radio, new_radio, "web radio safety normalization")

    old_i2c = '''\t\tconfig.i2c_enable = En;
\t\tsaveConfiguration("/default.cfg", config);
\t\tString html = "OK";
\t\trequest->send(200, "text/html", html);'''
    new_i2c = '''\t\tconfig.i2c_enable = En;
\t\t// I2C_0 is the Rev2.1 system bus shared by AXP2101 and SH1106.
\t\t// Keep it enabled and keep its physical pins/clock fixed.
\t\tenforceRev21RadioHardwareProfile();
\t\tsaveConfiguration("/default.cfg", config);
\t\tString html = "OK";
\t\trequest->send(200, "text/html", html);'''
    text = replace_once(text, old_i2c, new_i2c, "web I2C system-bus normalization")

    WEB.write_text(text, encoding="utf-8")


def patch_platformio() -> None:
    text = PIO.read_text(encoding="utf-8")
    text = replace_once(text, 'adafruit/Adafruit SSD1306@^2.5.7', 'adafruit/Adafruit SH110X@2.1.14', "SH1106 PlatformIO dependency")

    # The repository contains a bundled Adafruit_GFX 1.5.6 used by the legacy
    # SSD1306 path. SH110X requires the current Adafruit GFX/GrayOLED stack, so
    # compiling both copies creates duplicate symbols at link time. The bundled
    # copy is renamed "Legacy Adafruit GFX Library" in its library.properties and
    # is explicitly ignored by the Rev2.1 environment.
    if 'lib_ignore = Legacy Adafruit GFX Library\n' not in text:
        anchor = 'monitor_filters = esp32_exception_decoder\n'
        if anchor not in text:
            raise SystemExit("ERROR: platformio lib_ignore insertion anchor missing")
        text = text.replace(anchor, anchor + 'lib_ignore = Legacy Adafruit GFX Library\n', 1)

    # The old standalone SSD1306 implementation lives in src/, so LDF cannot
    # ignore it. Exclude it explicitly now that all active display code is SH1106.
    if 'build_src_filter = +<*> -<Adafruit_SSD1306.cpp>\n' not in text:
        anchor = 'lib_ignore = Legacy Adafruit GFX Library\n'
        text = text.replace(anchor, anchor + 'build_src_filter = +<*> -<Adafruit_SSD1306.cpp>\n', 1)

    PIO.write_text(text, encoding="utf-8")


def main() -> None:
    patch_main()
    patch_gui_header()
    patch_gui_cpp()
    patch_sensor()
    patch_web()
    patch_platformio()
    print("PASS Rev2.1 deep compatibility patch applied/idempotent")


if __name__ == "__main__":
    main()
