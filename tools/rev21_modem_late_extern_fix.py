#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEM = ROOT / "lib/LibAPRS_ESP32S3/modem.cpp"

OLD = '''extern int8_t adcEn;
extern int8_t dacEn;
extern bool hw_afsk_dac_isr;
void ModemTxTestStop(void)
'''

NEW = '''extern volatile int8_t adcEn;
extern volatile int8_t dacEn;
extern volatile bool hw_afsk_dac_isr;
void ModemTxTestStop(void)
'''

text = MODEM.read_text(encoding="utf-8")
if OLD in text:
    if text.count(OLD) != 1:
        raise SystemExit(f"ERROR: expected one late ModemTxTest transition extern block, found {text.count(OLD)}")
    text = text.replace(OLD, NEW, 1)
elif NEW not in text:
    raise SystemExit("ERROR: late ModemTxTest transition extern block not found")

MODEM.write_text(text, encoding="utf-8")
print("PASS Rev2.1 late modem transition externs normalized")
