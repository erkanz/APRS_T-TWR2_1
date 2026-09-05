#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    old = '  display.begin(SSD1306_SWITCHCAPVCC, oled_addr, false); // initialize with the I2C addr 0x3C (for the 128x64)\n'
    new = ('  // Rev2.1 shared I2C bus is already initialized by AXP2101 PMU.begin().\n'
           '  // periphBegin=false prevents Adafruit_SSD1306 from calling Wire.begin() again.\n'
           '  display.begin(SSD1306_SWITCHCAPVCC, oled_addr, false, false);\n')

    if new in text:
        print("SKIP  OLED already reuses the initialized Rev2.1 I2C bus")
    elif old in text:
        text = text.replace(old, new, 1)
        print("PATCH prevent duplicate Wire.begin() from OLED initialization")
    else:
        raise RuntimeError("unexpected OLED begin call; refusing blind edit")

    MAIN.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_main()
    print("Rev2.1 OLED/shared-I2C compatibility fix applied.")
