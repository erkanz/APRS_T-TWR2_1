#pragma once

#include <Arduino.h>
#include <Adafruit_SH110X.h>
#include <Adafruit_I2CDevice.h>

// Rev2.1 compatibility wrapper around the official SH1106 driver.
//
// Two compatibility details are intentionally kept here instead of carrying
// the fork's old modified Adafruit_GFX/SSD1306 copies:
//   1) The T-TWR UI stores several bitmaps as vertical 8-pixel columns,
//      LSB-first (the legacy fork called this drawYBitmap()).
//   2) AXP2101 PMU.begin() already owns and initializes the shared Wire bus on
//      GPIO8/GPIO9. Adafruit_GrayOLED::_init() would call Wire.begin() again
//      through Adafruit_I2CDevice::begin(), producing an ESP32 duplicate-bus
//      warning and relying on default pins. This wrapper initializes only the
//      OLED device state and never restarts the system I2C controller.
class Rev21SH1106G : public Adafruit_SH1106G
{
public:
    Rev21SH1106G(uint16_t w, uint16_t h, TwoWire *wire = &Wire,
                 int16_t rst_pin = -1, uint32_t preclk = 400000,
                 uint32_t postclk = 400000)
        : Adafruit_SH1106G(w, h, wire, rst_pin, preclk, postclk),
          _rev21Wire(wire)
    {
    }

    bool begin(uint8_t addr = 0x3C, bool reset = true)
    {
        // Allocate the same 1-bpp framebuffer used by Adafruit_GrayOLED::_init.
        if ((!buffer) &&
            !(buffer = (uint8_t *)malloc(_bpp * WIDTH * ((HEIGHT + 7) / 8))))
        {
            return false;
        }

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

        // The bus is already initialized by AXP2101 PMU.begin(). Probe the
        // OLED directly without Adafruit_I2CDevice::begin(), because that
        // method unconditionally calls Wire.begin().
        _rev21Wire->setClock(400000);
        _rev21Wire->beginTransmission(addr);
        if (_rev21Wire->endTransmission() != 0)
        {
            return false;
        }

        if (i2c_dev)
        {
            delete i2c_dev;
            i2c_dev = nullptr;
        }
        i2c_dev = new Adafruit_I2CDevice(addr, _rev21Wire);
        if (!i2c_dev)
        {
            return false;
        }

        clearDisplay();
        window_x1 = 0;
        window_y1 = 0;
        window_x2 = WIDTH - 1;
        window_y2 = HEIGHT - 1;
        _page_start_offset = 2;

        // Official Adafruit_SH1106G 2.1.14 initialization sequence.
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
        {
            return false;
        }

        delay(100);
        oled_command(SH110X_DISPLAYON);
        _rev21Wire->setClock(400000);
        return true;
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
    TwoWire *_rev21Wire;
};
