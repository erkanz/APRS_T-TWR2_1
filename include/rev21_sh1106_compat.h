#pragma once

#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_SH110X.h>
#include <Adafruit_I2CDevice.h>

// Minimal ST7789 transport for the official T-TWR expansion SPI interface.
// No third-party TFT package is required; this deliberately avoids pulling an
// Arduino SD library that conflicts with the ESP32 framework SD implementation.
class Rev21ST7789
{
public:
    static constexpr int16_t PANEL_WIDTH = 240;
    static constexpr int16_t PANEL_HEIGHT = 320;
    static constexpr uint32_t SPI_HZ = 27000000;

    Rev21ST7789(int8_t cs, int8_t dc, int8_t rst)
        : _cs(cs), _dc(dc), _rst(rst)
    {
    }

    bool begin()
    {
        pinMode(_cs, OUTPUT);
        pinMode(_dc, OUTPUT);
        pinMode(_rst, OUTPUT);
        digitalWrite(_cs, HIGH);
        digitalWrite(_dc, HIGH);

        // Shared T-TWR SPI: SCK12, MISO13, MOSI11. Keep SD deselected.
        pinMode(10, OUTPUT);
        digitalWrite(10, HIGH);
        SPI.begin(12, 13, 11);

        digitalWrite(_rst, HIGH);
        delay(20);
        digitalWrite(_rst, LOW);
        delay(20);
        digitalWrite(_rst, HIGH);
        delay(120);

        command(ST7789_SWRESET);
        delay(150);
        command(ST7789_SLPOUT);
        delay(120);
        commandData(ST7789_COLMOD, 0x55); // RGB565, 16 bits/pixel

        // Landscape rotation: MX + MV. Logical drawing area becomes 320x240.
        commandData(ST7789_MADCTL, 0x60);
        command(ST7789_INVON);
        command(ST7789_NORON);
        delay(10);
        command(ST7789_DISPON);
        delay(100);
        _awake = true;
        return true;
    }

    void enableDisplay(bool on)
    {
        if (on == _awake)
            return;
        if (on)
        {
            command(ST7789_SLPOUT);
            delay(120);
            command(ST7789_DISPON);
        }
        else
        {
            command(ST7789_DISPOFF);
            command(ST7789_SLPIN);
        }
        _awake = on;
    }

    void drawDoubleRow(int16_t x, int16_t y, const uint16_t *row, int16_t width)
    {
        if (!_awake || row == nullptr || width <= 0)
            return;

        startTransaction();
        setAddressWindowInTransaction(x, y, width, 2);
        digitalWrite(_dc, HIGH);
        for (int repeat = 0; repeat < 2; ++repeat)
        {
            for (int16_t i = 0; i < width; ++i)
                SPI.transfer16(row[i]);
        }
        endTransaction();
    }

private:
    static constexpr uint8_t ST7789_SWRESET = 0x01;
    static constexpr uint8_t ST7789_SLPIN   = 0x10;
    static constexpr uint8_t ST7789_SLPOUT  = 0x11;
    static constexpr uint8_t ST7789_NORON   = 0x13;
    static constexpr uint8_t ST7789_INVON   = 0x21;
    static constexpr uint8_t ST7789_DISPOFF = 0x28;
    static constexpr uint8_t ST7789_DISPON  = 0x29;
    static constexpr uint8_t ST7789_CASET   = 0x2A;
    static constexpr uint8_t ST7789_RASET   = 0x2B;
    static constexpr uint8_t ST7789_RAMWR   = 0x2C;
    static constexpr uint8_t ST7789_MADCTL  = 0x36;
    static constexpr uint8_t ST7789_COLMOD  = 0x3A;

    void startTransaction()
    {
        SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
        digitalWrite(_cs, LOW);
    }

    void endTransaction()
    {
        digitalWrite(_cs, HIGH);
        SPI.endTransaction();
    }

    void writeCommandInTransaction(uint8_t cmd)
    {
        digitalWrite(_dc, LOW);
        SPI.transfer(cmd);
    }

    void writeData8InTransaction(uint8_t data)
    {
        digitalWrite(_dc, HIGH);
        SPI.transfer(data);
    }

    void writeData16InTransaction(uint16_t data)
    {
        digitalWrite(_dc, HIGH);
        SPI.transfer16(data);
    }

    void command(uint8_t cmd)
    {
        startTransaction();
        writeCommandInTransaction(cmd);
        endTransaction();
    }

    void commandData(uint8_t cmd, uint8_t data)
    {
        startTransaction();
        writeCommandInTransaction(cmd);
        writeData8InTransaction(data);
        endTransaction();
    }

    void setAddressWindowInTransaction(int16_t x, int16_t y, int16_t w, int16_t h)
    {
        const uint16_t x2 = static_cast<uint16_t>(x + w - 1);
        const uint16_t y2 = static_cast<uint16_t>(y + h - 1);

        writeCommandInTransaction(ST7789_CASET);
        writeData16InTransaction(static_cast<uint16_t>(x));
        writeData16InTransaction(x2);
        writeCommandInTransaction(ST7789_RASET);
        writeData16InTransaction(static_cast<uint16_t>(y));
        writeData16InTransaction(y2);
        writeCommandInTransaction(ST7789_RAMWR);
    }

    int8_t _cs;
    int8_t _dc;
    int8_t _rst;
    bool _awake = false;
};

// Rev2.1 dual-display compatibility wrapper.
// The existing 128x64 monochrome framebuffer remains the canonical UI. TFT mode
// mirrors it 2x into the centre of a 320x240 landscape ST7789 canvas.
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
        // Allocate the 1-bpp framebuffer even in TFT-only mode because all legacy
        // GUI code draws into this framebuffer before display().
        if ((!buffer) &&
            !(buffer = (uint8_t *)malloc(_bpp * WIDTH * ((HEIGHT + 7) / 8))))
            return false;
        clearDisplay();

        bool ready = false;
        if (usesOLED() && addr != 0)
        {
            _oledReady = beginOLED(addr, reset);
            ready = ready || _oledReady;
        }
        if (usesTFT())
        {
            _tftReady = _tft.begin();
            ready = ready || _tftReady;
        }
        _sleeping = false;
        return ready;
    }

    // Hide the base display() so every existing GUI flush reaches the selected
    // output(s) without any call-site changes.
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
            _tft.enableDisplay(!sleep);
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

    void mirrorToTFT()
    {
        static constexpr int16_t SCALE = 2;
        static constexpr int16_t MIRROR_W = 128 * SCALE;
        static constexpr int16_t MIRROR_H = 64 * SCALE;
        static constexpr int16_t X0 = (320 - MIRROR_W) / 2;
        static constexpr int16_t Y0 = (240 - MIRROR_H) / 2;
        uint16_t row[MIRROR_W];

        for (int16_t y = 0; y < 64; ++y)
        {
            for (int16_t x = 0; x < 128; ++x)
            {
                const bool on = (buffer[x + (y >> 3) * 128] & (1U << (y & 7))) != 0;
                // transfer16 sends MSB first in the configured SPI transaction.
                const uint16_t color = on ? 0xFFFF : 0x0000;
                row[x * 2] = color;
                row[x * 2 + 1] = color;
            }
            _tft.drawDoubleRow(X0, Y0 + y * 2, row, MIRROR_W);
        }
    }

    TwoWire *_rev21Wire;
    Rev21ST7789 _tft;
    uint8_t _outputMode = OUTPUT_OLED;
    bool _oledReady = false;
    bool _tftReady = false;
    bool _sleeping = false;
};
