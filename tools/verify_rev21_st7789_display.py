#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "include/rev21_sh1106_compat.h").read_text(encoding="utf-8")
MAIN_H = (ROOT / "include/main.h").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.cpp").read_text(encoding="utf-8")
WEB = (ROOT / "src/webservice.cpp").read_text(encoding="utf-8")
PIO = (ROOT / "platformio.ini").read_text(encoding="utf-8")
CONFIG_H = (ROOT / "include/config.h").read_text(encoding="utf-8")

checks = [
    ("ST7789 uses native SPI driver without TFT package", "class Rev21ST7789" in HEADER and "#include <SPI.h>" in HEADER and "Adafruit ST7735 and ST7789 Library" not in PIO and "Adafruit_ST7789.h" not in HEADER),
    ("official T-TWR expansion SPI pins used", "_tft(44, 14, 43)" in HEADER and "SPI.begin(12, 13, 11);" in HEADER),
    ("ST7789 panel geometry is 240x320 landscape", "PANEL_WIDTH = 240" in HEADER and "PANEL_HEIGHT = 320" in HEADER and "commandData(ST7789_MADCTL, 0x60);" in HEADER),
    ("ST7789 RGB565 mode configured", "commandData(ST7789_COLMOD, 0x55);" in HEADER),
    ("legacy framebuffer mirrors to TFT at 2x", "mirrorToTFT" in HEADER and "MIRROR_W = 128 * SCALE" in HEADER and "MIRROR_H = 64 * SCALE" in HEADER),
    ("display modes include OLED TFT BOTH", "DISPLAY_OUTPUT_OLED 0" in MAIN_H and "DISPLAY_OUTPUT_TFT 1" in MAIN_H and "DISPLAY_OUTPUT_BOTH 2" in MAIN_H),
    ("display mode stored separately in NVS", 'prefs.begin("twr-display", true)' in MAIN and 'prefs.putUChar("mode", rev21DisplayOutputMode)' in MAIN),
    ("Configuration binary layout not changed for display mode", "display_output_mode" not in CONFIG_H),
    ("display mode is applied before panel init", "loadDisplayOutputMode();" in MAIN and "display.setOutputMode(getDisplayOutputMode());" in MAIN),
    ("TFT-only tolerates missing OLED", "if (getDisplayOutputMode() == DISPLAY_OUTPUT_OLED)" in MAIN and "config.oled_enable = false;" in MAIN),
    ("screen timeout service installed", "static void serviceDisplayScreenTimeout()" in MAIN and "config.oled_timeout" in MAIN and "display.setPanelSleep(true);" in MAIN),
    ("any physical UI button can wake display", "BOOT_PIN, BUTTON_PTT_PIN, ENCODER_OK_PIN, ENCODER_A_PIN, ENCODER_B_PIN" in MAIN and "display.setPanelSleep(false);" in MAIN),
    ("System Display Setting exposes OLED TFT BOTH", '<b>Display Output</b>' in WEB and 'name=\\"displayMode\\"' in WEB and "TFT (ST7789)" in WEB and "Both" in WEB),
    ("System Display Setting exposes screen timeout", "<b>Screen Timeout</b>" in WEB and 'name=\\"oled_timeout\\"' in WEB),
    ("web UI documents ST7789 interface", "MOSI=11, MISO=13, SCK=12, CS=44, DC=14, RST=43" in WEB),
    ("GPIO38 is not used for TFT backlight", "pinMode(38" not in HEADER and "digitalWrite(38" not in HEADER and "TFT_BL" not in HEADER),
    ("TFT sleep/wake uses ST7789 controller commands", "ST7789_DISPOFF" in HEADER and "ST7789_SLPIN" in HEADER and "ST7789_SLPOUT" in HEADER and "ST7789_DISPON" in HEADER),
    ("native ST7789 path cannot pull Arduino SD dependency", "Adafruit seesaw" not in PIO and "Adafruit ST7735 and ST7789 Library" not in PIO),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL"), name)

if failed:
    raise SystemExit(f"{len(failed)} ST7789/display checks failed: {', '.join(failed)}")

print(f"{len(checks)}/{len(checks)} ST7789/display checks PASS")
