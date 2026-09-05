#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEM = ROOT / "lib/LibAPRS_ESP32S3/modem.cpp"

DUPLICATE = '''extern int8_t adcEn;
extern volatile int8_t adcEn;
'''
CLEAN = '''extern volatile int8_t adcEn;
'''

text = MODEM.read_text(encoding="utf-8")
if DUPLICATE in text:
    if text.count(DUPLICATE) != 1:
        raise SystemExit(f"ERROR: expected one duplicate late adcEn extern pair, found {text.count(DUPLICATE)}")
    text = text.replace(DUPLICATE, CLEAN, 1)
elif "extern int8_t adcEn;" in text:
    raise SystemExit("ERROR: unexpected nonvolatile adcEn extern remains in modem.cpp")
elif "extern volatile int8_t adcEn;" not in text:
    raise SystemExit("ERROR: volatile adcEn extern not found in modem.cpp")

MODEM.write_text(text, encoding="utf-8")
print("PASS Rev2.1 late modem adcEn extern normalized")
