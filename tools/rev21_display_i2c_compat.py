#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    # Final Rev2.1 source uses the board's real SH1106 controller. SH110X
    # legitimately calls Wire.begin(), but Arduino-ESP32 reuses an already
    # initialized TwoWire bus; the display object is also configured to restore
    # the shared bus to 400 kHz after transfers. Do not try to rewrite the
    # SH1106 begin call back into the legacy SSD1306 form.
    if (("Adafruit_SH1106G display(" in text or "Rev21SH1106G display(" in text) and
            "display.begin(oled_addr, false);" in text):
        print("SKIP  Rev2.1 SH1106 already uses the initialized shared Wire bus")
        MAIN.write_text(text, encoding="utf-8")
        return

    old = '  display.begin(SSD1306_SWITCHCAPVCC, oled_addr, false); // initialize with the I2C addr 0x3C (for the 128x64)\n'
    new = ('  // Rev2.1 shared I2C bus is already initialized by AXP2101 PMU.begin().\n'
           '  // periphBegin=false prevents Adafruit_SSD1306 from calling Wire.begin() again.\n'
           '  display.begin(SSD1306_SWITCHCAPVCC, oled_addr, false, false);\n')

    if new in text:
        print("SKIP  legacy SSD1306 path already reuses the initialized Rev2.1 I2C bus")
    elif old in text:
        text = text.replace(old, new, 1)
        print("PATCH prevent duplicate Wire.begin() from legacy OLED initialization")
    else:
        raise RuntimeError("unexpected OLED begin call; refusing blind edit")

    MAIN.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_main()
    print("Rev2.1 OLED/shared-I2C compatibility fix applied.")
