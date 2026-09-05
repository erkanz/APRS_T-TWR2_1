#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEM = ROOT / "lib/LibAPRS_ESP32S3/modem.cpp"
MAIN = ROOT / "src/main.cpp"

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

# The upstream tracker diagnostics have appeared in more than one printf format
# (%d/%u and with/without the INTERVAL suffix).  Remove by stable message prefix
# after all compatibility passes so no variant can flood the USB serial console.
main_text = MAIN.read_text(encoding="utf-8")
had_final_newline = main_text.endswith("\n")
lines = main_text.splitlines()
filtered = [line for line in lines if "TRACKER tx_counter=" not in line]
removed = len(lines) - len(filtered)
main_text = "\n".join(filtered)
if had_final_newline:
    main_text += "\n"
if "TRACKER tx_counter=" in main_text:
    raise SystemExit("ERROR: tracker tx_counter serial diagnostic remains after cleanup")
MAIN.write_text(main_text, encoding="utf-8")

print("PASS Rev2.1 late modem adcEn extern normalized")
print(f"PASS tracker tx_counter serial diagnostics removed: {removed} line(s)")
