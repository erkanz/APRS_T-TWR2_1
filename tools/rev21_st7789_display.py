#!/usr/bin/env python3
"""Add Rev2.1 ST7789 mirrored display support and display power management.

Design goals:
- preserve the existing 128x64 SH1106 UI as the canonical framebuffer;
- mirror that framebuffer to an external ST7789 240x320 panel on the official
  T-TWR expansion SPI pins;
- select OLED, TFT, or BOTH without changing Configuration size (mode is stored
  separately in NVS, avoiding an EEPROM configuration migration/reset);
- implement the existing oled_timeout setting as a real screen timeout;
- wake the display on BOOT, side PTT, encoder push, or encoder rotation;
- never use GPIO38 for the TFT backlight in this firmware.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "include/rev21_sh1106_compat.h"
MAIN_H = ROOT / "include/main.h"
MAIN = ROOT / "src/main.cpp"
WEB = ROOT / "src/webservice.cpp"
PIO = ROOT / "platformio.ini"

HEADER_CONTENT = r'''#pragma once

#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_SH110X.h>
#include <Adafruit_I2CDevice.h>
#include <Adafruit_ST7789.h>

// Rev2.1 display compatibility wrapper.
//
// The existing firmware draws a 128x64 monochrome UI into the SH1106 framebuffer.
// That framebuffer remains the single rendering source.  When TFT output is
// selected, display() mirrors it at 2x scale into the centre of a 240x320 ST7789
// running landscape (logical 320x240).  This keeps every existing menu, icon and
// APRS screen coherent without maintaining two separate UI implementations.
//
// Official T-TWR expansion SPI pins:
//   SCK=12, MISO=13, MOSI=11, CS=44, DC=14, RST=43
// GPIO38 is intentionally NOT used for backlight control in this firmware.
class Rev21SH1106G : public Adafruit_SH1106G
{
public:
    enum OutputMode : uint8_t
    {
        OUTPUT_OLED = 0,
        OUTPUT_TFT = 1,
        OUTPUT_BOTH = 2,
    };

    Rev21SH1106G(uint16_t w, uint16_t h, TwoWire *wire = &Wire,
                 int16_t rst_pin = -1, uint32_t preclk = 400000,
                 uint32_t postclk = 400000)
        : Adafruit_SH1106G(w, h, wire, rst_pin, preclk, postclk),
          _rev21Wire(wire), _tft(44, 14, 43)
    {
    }

    void setOutputMode(uint8_t mode)
    {
        _outputMode = (mode <= OUTPUT_BOTH) ? mode : OUTPUT_OLED;
    }

    uint8_t outputMode() const { return _outputMode; }
    bool usesOLED() const { return _outputMode == OUTPUT_OLED || _outputMode == OUTPUT_BOTH; }
    bool usesTFT() const { return _outputMode == OUTPUT_TFT || _outputMode == OUTPUT_BOTH; }
    bool oledReady() const { return _oledReady; }
    bool tftReady() const { return _tftReady; }
    bool sleeping() const { return _sleeping; }

    bool begin(uint8_t addr = 0x3C, bool reset = true)
    {
        // Allocate the same 1-bpp framebuffer used by Adafruit_GrayOLED::_init.
        // It is needed even in TFT-only mode because the legacy UI draws into it.
        if ((!buffer) &&
            !(buffer = (uint8_t *)malloc(_bpp * WIDTH * ((HEIGHT + 7) / 8))))
        {
            return false;
        }
        clearDisplay();

        bool ready = false;
        if (usesOLED() && addr != 0)
        {
            _oledReady = beginOLED(addr, reset);
            ready = ready || _oledReady;
        }

        if (usesTFT())
        {
            _tftReady = beginTFT();
            ready = ready || _tftReady;
        }

        _sleeping = false;
        return ready;
    }

    // Hide the base display() so every legacy flush also updates ST7789.
    void display()
    {
        if (_sleeping)
            return;
        if (usesOLED() && _oledReady)
        {
            Adafruit_SH1106G::display();
            _rev21Wire->setClock(400000);
        }
        if (usesTFT() && _tftReady)
            mirrorToTFT();
    }

    // Existing UI dimming remains OLED-only. TFT timeout is controlled by
    // setPanelSleep(), not by pretending an ST7789 has an OLED contrast register.
    void setContrast(uint8_t contrast)
    {
        if (usesOLED() && _oledReady)
        {
            Adafruit_SH1106G::setContrast(contrast);
            _rev21Wire->setClock(400000);
        }
    }

    void setPanelSleep(bool sleep)
    {
        if (_sleeping == sleep)
            return;

        if (usesOLED() && _oledReady)
        {
            oled_command(sleep ? SH110X_DISPLAYOFF : SH110X_DISPLAYON);
            _rev21Wire->setClock(400000);
        }
        if (usesTFT() && _tftReady)
        {
            _tft.enableDisplay(!sleep);
        }

        _sleeping = sleep;
        if (!sleep)
            display();
    }

    void drawYBitmap(int16_t x, int16_t y,
                     const uint8_t bitmap[], int16_t w, int16_t h,
                     uint16_t color)
    {
        const int16_t byteHeight = (h + 7) / 8;

        startWrite();
        for (int16_t page = 0; page < byteHeight; ++page, y += 8)
        {
            for (int16_t i = 0; i < w; ++i)
            {
                uint8_t byte = pgm_read_byte(&bitmap[i + (page * w)]);
                for (int8_t bit = 0; bit < 8; ++bit)
                {
                    if (byte & 0x01)
                        writePixel(x + i, y + bit, color);
                    byte >>= 1;
                }
            }
        }
        endWrite();
    }

private:
    bool beginOLED(uint8_t addr, bool reset)
    {
        if (reset && (rstPin >= 0))
        {
            pinMode(rstPin, OUTPUT);
            digitalWrite(rstPin, HIGH);
            delay(10);
            digitalWrite(rstPin, LOW);
            delay(10);
            digitalWrite(rstPin, HIGH);
            delay(10);
        }

        // AXP2101 PMU.begin() already owns/initializes the shared Wire bus.
        _rev21Wire->setClock(400000);
        _rev21Wire->beginTransmission(addr);
        if (_rev21Wire->endTransmission() != 0)
            return false;

        if (i2c_dev)
        {
            delete i2c_dev;
            i2c_dev = nullptr;
        }
        i2c_dev = new Adafruit_I2CDevice(addr, _rev21Wire);
        if (!i2c_dev)
            return false;

        window_x1 = 0;
        window_y1 = 0;
        window_x2 = WIDTH - 1;
        window_y2 = HEIGHT - 1;
        _page_start_offset = 2;

        static const uint8_t init[] = {
            SH110X_DISPLAYOFF,
            SH110X_SETDISPLAYCLOCKDIV, 0x80,
            SH110X_SETMULTIPLEX, 0x3F,
            SH110X_SETDISPLAYOFFSET, 0x00,
            SH110X_SETSTARTLINE,
            SH110X_DCDC, 0x8B,
            SH110X_SEGREMAP + 1,
            SH110X_COMSCANDEC,
            SH110X_SETCOMPINS, 0x12,
            SH110X_SETCONTRAST, 0xFF,
            SH110X_SETPRECHARGE, 0x1F,
            SH110X_SETVCOMDETECT, 0x40,
            0x33,
            SH110X_NORMALDISPLAY,
            SH110X_MEMORYMODE, 0x10,
            SH110X_DISPLAYALLON_RESUME,
        };

        if (!oled_commandList(init, sizeof(init)))
            return false;

        delay(100);
        oled_command(SH110X_DISPLAYON);
        _rev21Wire->setClock(400000);
        return true;
    }

    bool beginTFT()
    {
        // Share the board SPI bus with the SD interface. Keep SD deselected while
        // initializing/updating the TFT. The current Rev2.1 build does not mount SD
        // at boot, but the CS discipline keeps the bus safe if that changes later.
        pinMode(10, OUTPUT);
        digitalWrite(10, HIGH);
        SPI.begin(12, 13, 11);

        _tft.init(240, 320);
        _tft.setRotation(1); // logical 320x240
        _tft.fillScreen(ST77XX_BLACK);
        _tft.enableDisplay(true);
        return true;
    }

    void mirrorToTFT()
    {
        // 128x64 -> 256x128 at 2x scale, centred in 320x240 landscape.
        static constexpr int16_t SCALE = 2;
        static constexpr int16_t MIRROR_W = 128 * SCALE;
        static constexpr int16_t MIRROR_H = 64 * SCALE;
        static constexpr int16_t X0 = (320 - MIRROR_W) / 2;
        static constexpr int16_t Y0 = (240 - MIRROR_H) / 2;
        uint16_t row[MIRROR_W];

        _tft.startWrite();
        for (int16_t y = 0; y < 64; ++y)
        {
            for (int16_t x = 0; x < 128; ++x)
            {
                const bool on = (buffer[x + (y >> 3) * 128] & (1U << (y & 7))) != 0;
                const uint16_t color = on ? ST77XX_WHITE : ST77XX_BLACK;
                row[x * 2] = color;
                row[x * 2 + 1] = color;
            }
            _tft.setAddrWindow(X0, Y0 + y * 2, MIRROR_W, 2);
            _tft.writePixels(row, MIRROR_W, true);
            _tft.writePixels(row, MIRROR_W, true);
        }
        _tft.endWrite();
    }

    TwoWire *_rev21Wire;
    Adafruit_ST7789 _tft;
    uint8_t _outputMode = OUTPUT_OLED;
    bool _oledReady = false;
    bool _tftReady = false;
    bool _sleeping = false;
};
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label}: expected exactly one source match, found {count}")
    return text.replace(old, new, 1)


def patch_main_h() -> None:
    text = MAIN_H.read_text(encoding="utf-8")
    marker = "#define DISPLAY_OUTPUT_OLED 0"
    if marker not in text:
        anchor = "#define SDCARD\n"
        block = anchor + "\n#define DISPLAY_OUTPUT_OLED 0\n#define DISPLAY_OUTPUT_TFT 1\n#define DISPLAY_OUTPUT_BOTH 2\n"
        text = replace_once(text, anchor, block, "display output constants")

    proto = "uint8_t getDisplayOutputMode();"
    if proto not in text:
        anchor = "void convertSecondsToDHMS(char *dmhs,unsigned long totalSeconds);\n"
        block = anchor + "uint8_t getDisplayOutputMode();\nvoid setDisplayOutputMode(uint8_t mode);\nbool displayOutputUsesTFT();\n"
        text = replace_once(text, anchor, block, "display output prototypes")
    MAIN_H.write_text(text, encoding="utf-8")


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    if "#include <Preferences.h>" not in text:
        text = replace_once(text, "#include <LITTLEFS.h>\n", "#include <LITTLEFS.h>\n#include <Preferences.h>\n", "Preferences include")

    settings_marker = "static uint8_t rev21DisplayOutputMode = DISPLAY_OUTPUT_OLED;"
    if settings_marker not in text:
        anchor = "Configuration config;\n"
        block = r'''Configuration config;

// Display output mode is stored independently from Configuration so adding this
// feature never changes the EEPROM binary layout or resets existing user settings.
static uint8_t rev21DisplayOutputMode = DISPLAY_OUTPUT_OLED;

uint8_t getDisplayOutputMode()
{
  return rev21DisplayOutputMode;
}

bool displayOutputUsesTFT()
{
  return rev21DisplayOutputMode == DISPLAY_OUTPUT_TFT || rev21DisplayOutputMode == DISPLAY_OUTPUT_BOTH;
}

static void loadDisplayOutputMode()
{
  Preferences prefs;
  if (prefs.begin("twr-display", true))
  {
    rev21DisplayOutputMode = prefs.getUChar("mode", DISPLAY_OUTPUT_OLED);
    prefs.end();
  }
  if (rev21DisplayOutputMode > DISPLAY_OUTPUT_BOTH)
    rev21DisplayOutputMode = DISPLAY_OUTPUT_OLED;
  // Legacy oled_enable becomes the master "display task enabled" flag. All three
  // new modes require the task, so an old disabled value must not suppress TFT.
  config.oled_enable = true;
  log_i("[DISPLAY] output=%s timeout=%ds",
        rev21DisplayOutputMode == DISPLAY_OUTPUT_OLED ? "OLED" :
        (rev21DisplayOutputMode == DISPLAY_OUTPUT_TFT ? "TFT" : "BOTH"),
        config.oled_timeout);
}

void setDisplayOutputMode(uint8_t mode)
{
  if (mode > DISPLAY_OUTPUT_BOTH)
    mode = DISPLAY_OUTPUT_OLED;
  rev21DisplayOutputMode = mode;
  Preferences prefs;
  if (prefs.begin("twr-display", false))
  {
    prefs.putUChar("mode", rev21DisplayOutputMode);
    prefs.end();
  }
  log_i("[DISPLAY] saved output mode=%u; applies after reboot", rev21DisplayOutputMode);
}
'''
        text = replace_once(text, anchor, block, "display NVS settings")

    setup_marker = "  loadDisplayOutputMode();\n  display.setOutputMode(getDisplayOutputMode());\n"
    if setup_marker not in text:
        anchor = "  setupPower();\n  Wire.setClock(config.i2c_freq);\n"
        replacement = anchor + setup_marker
        text = replace_once(text, anchor, replacement, "display mode startup")

    old_no_oled = '''  } else {\n    log_d("No OLED found");\n    config.oled_enable = false;\n  }   \n'''
    new_no_oled = '''  } else {\n    log_d("No OLED found");\n    // TFT-only remains fully operational without an OLED. In BOTH mode the TFT\n    // remains available even if the onboard OLED is absent/faulty.\n    if (getDisplayOutputMode() == DISPLAY_OUTPUT_OLED)\n      config.oled_enable = false;\n  }   \n'''
    if old_no_oled in text:
        text = replace_once(text, old_no_oled, new_no_oled, "TFT-only OLED probe handling")
    elif new_no_oled not in text:
        raise SystemExit("ERROR: OLED probe branch not found")

    # Wake/sleep service: observe button/encoder pin transitions without consuming
    # events, so the same press still performs its normal radio/menu action.
    timeout_marker = "static void serviceDisplayScreenTimeout()"
    if timeout_marker not in text:
        anchor = "bool ptt_stat_old = false;\n\nvoid loop()\n{\n  vTaskDelay(10 / portTICK_PERIOD_MS);\n"
        block = r'''bool ptt_stat_old = false;

static uint32_t displayLastActivityMs = 0;
static bool displayTimeoutSleeping = false;
static int8_t displayButtonState[5] = {-1, -1, -1, -1, -1};

static void serviceDisplayScreenTimeout()
{
  const int pins[5] = {BOOT_PIN, BUTTON_PTT_PIN, ENCODER_OK_PIN, ENCODER_A_PIN, ENCODER_B_PIN};
  bool activity = false;
  for (size_t i = 0; i < 5; ++i)
  {
    const int state = digitalRead(pins[i]);
    if (displayButtonState[i] < 0)
      displayButtonState[i] = state;
    else if (displayButtonState[i] != state)
    {
      displayButtonState[i] = state;
      activity = true;
    }
  }

  const uint32_t nowMs = millis();
  if (displayLastActivityMs == 0)
    displayLastActivityMs = nowMs;

  if (activity)
  {
    displayLastActivityMs = nowMs;
    if (displayTimeoutSleeping)
    {
      display.setPanelSleep(false);
      displayTimeoutSleeping = false;
      log_i("[DISPLAY] wake: button/encoder activity");
    }
  }

  if (config.oled_timeout <= 0)
  {
    if (displayTimeoutSleeping)
    {
      display.setPanelSleep(false);
      displayTimeoutSleeping = false;
    }
    return;
  }

  const uint32_t timeoutMs = static_cast<uint32_t>(config.oled_timeout) * 1000UL;
  if (!displayTimeoutSleeping && (uint32_t)(nowMs - displayLastActivityMs) >= timeoutMs)
  {
    display.setPanelSleep(true);
    displayTimeoutSleeping = true;
    log_i("[DISPLAY] sleep: timeout=%ds", config.oled_timeout);
  }
}

void loop()
{
  vTaskDelay(10 / portTICK_PERIOD_MS);
  serviceDisplayScreenTimeout();
'''
        text = replace_once(text, anchor, block, "display timeout service")

    # Encoder A/B are also wake sources; establish stable pull-up levels before loop.
    pin_marker = "  pinMode(ENCODER_A_PIN, INPUT_PULLUP);\n  pinMode(ENCODER_B_PIN, INPUT_PULLUP);\n"
    if pin_marker not in text:
        anchor = "  pinMode(BOOT_PIN, INPUT_PULLUP);\n  pinMode(ENCODER_OK_PIN, INPUT_PULLUP);\n"
        replacement = anchor + pin_marker
        text = replace_once(text, anchor, replacement, "encoder wake pin setup")

    MAIN.write_text(text, encoding="utf-8")


def patch_web() -> None:
    text = WEB.read_text(encoding="utf-8")

    # Add parser for the new dropdown while retaining the old oledEnable parser for
    # backwards compatibility with cached pages/older clients.
    parser_marker = 'if (request->argName(i) == "displayMode")'
    if parser_marker not in text:
        anchor = '''\t\t\tif (request->argName(i) == "oledEnable")\n'''
        idx = text.find(anchor)
        if idx < 0:
            raise SystemExit("ERROR: display POST parser anchor not found")
        parser = '''\t\t\tif (request->argName(i) == "displayMode")\n\t\t\t{\n\t\t\t\tif (request->arg(i) != "" && isValidNumber(request->arg(i)))\n\t\t\t\t{\n\t\t\t\t\tint mode = request->arg(i).toInt();\n\t\t\t\t\tif (mode >= DISPLAY_OUTPUT_OLED && mode <= DISPLAY_OUTPUT_BOTH)\n\t\t\t\t\t{\n\t\t\t\t\t\tsetDisplayOutputMode((uint8_t)mode);\n\t\t\t\t\t\tconfig.oled_enable = true;\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n'''
        text = text[:idx] + parser + text[idx:]

    old_ui = '''\t\thtml += "<td style=\\"text-align: right;\\"><b>OLED/TFT Enable</b></td>\\\n";\n\t\tString oledFlageEn = "";\n\t\tif (config.oled_enable == true)\n\t\t\toledFlageEn = "checked";\n\t\thtml += "<td style=\\"text-align: left;\\"><label class=\\"switch\\"><input type=\\"checkbox\\" name=\\"oledEnable\\" value=\\"OK\\" " + oledFlageEn + "><span class=\\"slider round\\"></span></label></td>\\\n";\n\t\thtml += "</tr>\\\n";\n\t\toledFlageEn = "";\n'''
    new_ui = '''\t\thtml += "<td style=\\"text-align: right;\\"><b>Display Output</b></td>\\\n";\n\t\thtml += "<td style=\\"text-align: left;\\"><select name=\\"displayMode\\" id=\\"displayMode\\">";\n\t\thtml += getDisplayOutputMode() == DISPLAY_OUTPUT_OLED ? "<option value=\\"0\\" selected>OLED (SH1106)</option>" : "<option value=\\"0\\">OLED (SH1106)</option>";\n\t\thtml += getDisplayOutputMode() == DISPLAY_OUTPUT_TFT ? "<option value=\\"1\\" selected>TFT (ST7789)</option>" : "<option value=\\"1\\">TFT (ST7789)</option>";\n\t\thtml += getDisplayOutputMode() == DISPLAY_OUTPUT_BOTH ? "<option value=\\"2\\" selected>Both</option>" : "<option value=\\"2\\">Both</option>";\n\t\thtml += "</select> <i>*Output change applies after reboot.</i></td>\\\n";\n\t\thtml += "</tr>\\\n";\n\t\thtml += "<tr><td style=\\"text-align: right;\\"><b>ST7789 Interface</b></td><td style=\\"text-align: left;\\">240x320 SPI; MOSI=11, MISO=13, SCK=12, CS=44, DC=14, RST=43</td></tr>\\\n";\n\t\tString oledFlageEn = "";\n'''
    if old_ui in text:
        text = text.replace(old_ui, new_ui, 1)
    elif "<b>Display Output</b>" not in text:
        raise SystemExit("ERROR: display output UI anchor not found")

    text = text.replace("<b>OLED/TFT Sleep</b>", "<b>Screen Timeout</b>")
    text = text.replace('>" + String(i) + " Sec</option>', '>" + (i == 0 ? String("Never") : String(i) + " Sec") + "</option>')

    WEB.write_text(text, encoding="utf-8")


def patch_platformio() -> None:
    text = PIO.read_text(encoding="utf-8")
    dep = "\tadafruit/Adafruit ST7735 and ST7789 Library@^1.11.0\n"
    if "Adafruit ST7735 and ST7789 Library" not in text:
        anchor = "\tadafruit/Adafruit SH110X@2.1.14\n"
        text = replace_once(text, anchor, anchor + dep, "ST7789 dependency")
    PIO.write_text(text, encoding="utf-8")


def main() -> None:
    HEADER.write_text(HEADER_CONTENT, encoding="utf-8")
    patch_main_h()
    patch_main()
    patch_web()
    patch_platformio()

    print("PASS ST7789 240x320 support installed on official T-TWR expansion SPI pins")
    print("PASS OLED/TFT/BOTH mode stored independently in NVS")
    print("PASS existing screen timeout activated for OLED and TFT")
    print("PASS BOOT/PTT/encoder push/encoder rotation wake the display")
    print("PASS legacy 128x64 UI mirrored 2x to ST7789 landscape")
    print("PASS GPIO38 remains unused by TFT backlight control")


if __name__ == "__main__":
    main()
