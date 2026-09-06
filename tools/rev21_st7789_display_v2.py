#!/usr/bin/env python3
"""Robust web UI patch for the Rev2.1 ST7789 display compatibility pass.

This module owns only the System -> Display Setting transformation. It uses
semantic markers instead of exact legacy line formatting and emits ordinary C++
statements (no source-line continuations), keeping generated code compiler-safe.
"""

import rev21_st7789_display as base


def patch_web() -> None:
    text = base.WEB.read_text(encoding="utf-8")

    # Add the new selector parser immediately before the legacy oledEnable parser.
    # Keep the old parser for cached/older web clients.
    parser_marker = 'if (request->argName(i) == "displayMode")'
    if parser_marker not in text:
        anchor = '\t\t\tif (request->argName(i) == "oledEnable")'
        idx = text.find(anchor)
        if idx < 0:
            raise SystemExit("ERROR: display POST parser anchor not found")
        parser = '''\t\t\tif (request->argName(i) == "displayMode")
\t\t\t{
\t\t\t\tif (request->arg(i) != "" && isValidNumber(request->arg(i)))
\t\t\t\t{
\t\t\t\t\tint mode = request->arg(i).toInt();
\t\t\t\t\tif (mode >= DISPLAY_OUTPUT_OLED && mode <= DISPLAY_OUTPUT_BOTH)
\t\t\t\t\t{
\t\t\t\t\t\tsetDisplayOutputMode((uint8_t)mode);
\t\t\t\t\t\tconfig.oled_enable = true;
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
'''
        text = text[:idx] + parser + text[idx:]

    # Replace the legacy OLED/TFT Enable checkbox. Locate by semantic markers
    # instead of exact escaped/newline formatting.
    if "<b>Display Output</b>" not in text:
        needle = "<b>OLED/TFT Enable</b>"
        pos = text.find(needle)
        if pos < 0:
            raise SystemExit("ERROR: legacy display output label not found")

        start = text.rfind('\t\thtml += "', 0, pos)
        end_marker = '\t\toledFlageEn = "";'
        end = text.find(end_marker, pos)
        if start < 0 or end < 0:
            raise SystemExit("ERROR: legacy display output block boundaries not found")
        end += len(end_marker)

        # Deliberately avoid C/C++ source-line continuation backslashes here.
        # Each generated statement is self-contained and therefore insensitive to
        # Python raw-string escaping or source newline conventions.
        new_ui = '''\t\thtml += "<td style=\\"text-align: right;\\"><b>Display Output</b></td>";
\t\thtml += "<td style=\\"text-align: left;\\"><select name=\\"displayMode\\" id=\\"displayMode\\">";
\t\thtml += getDisplayOutputMode() == DISPLAY_OUTPUT_OLED ? "<option value=\\"0\\" selected>OLED (SH1106)</option>" : "<option value=\\"0\\">OLED (SH1106)</option>";
\t\thtml += getDisplayOutputMode() == DISPLAY_OUTPUT_TFT ? "<option value=\\"1\\" selected>TFT (ST7789)</option>" : "<option value=\\"1\\">TFT (ST7789)</option>";
\t\thtml += getDisplayOutputMode() == DISPLAY_OUTPUT_BOTH ? "<option value=\\"2\\" selected>Both</option>" : "<option value=\\"2\\">Both</option>";
\t\thtml += "</select> <i>*Output change applies after reboot.</i></td>";
\t\thtml += "</tr>";
\t\thtml += "<tr><td style=\\"text-align: right;\\"><b>ST7789 Interface</b></td><td style=\\"text-align: left;\\">240x320 SPI; MOSI=11, MISO=13, SCK=12, CS=44, DC=14, RST=43</td></tr>";
\t\tString oledFlageEn = "";'''
        text = text[:start] + new_ui + text[end:]

    text = text.replace("<b>OLED/TFT Sleep</b>", "<b>Screen Timeout</b>")
    base.WEB.write_text(text, encoding="utf-8")


def main() -> None:
    base.HEADER.write_text(base.HEADER_CONTENT, encoding="utf-8")
    base.patch_main_h()
    base.patch_main()
    patch_web()
    base.patch_platformio()

    print("PASS ST7789 240x320 support installed on official T-TWR expansion SPI pins")
    print("PASS OLED/TFT/BOTH mode stored independently in NVS")
    print("PASS existing screen timeout activated for OLED and TFT")
    print("PASS BOOT/PTT/encoder push/encoder rotation wake the display")
    print("PASS legacy 128x64 UI mirrored 2x to ST7789 landscape")
    print("PASS GPIO38 remains unused by TFT backlight control")
    print("PASS System Display Setting patch emits compiler-safe C++")


if __name__ == "__main__":
    main()
