#pragma once

#include <Arduino.h>
#include <Adafruit_SH110X.h>

// Compatibility wrapper for the legacy T-TWR UI bitmap format.
// The original fork carried a custom Adafruit_GFX::drawYBitmap() method that
// interprets bitmap bytes as vertical 8-pixel columns, LSB first. Official
// Adafruit GFX does not provide that method, so keep the exact drawing
// semantics here while using the modern SH1106/GFX stack.
class Rev21SH1106G : public Adafruit_SH1106G
{
public:
    using Adafruit_SH1106G::Adafruit_SH1106G;

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
};
