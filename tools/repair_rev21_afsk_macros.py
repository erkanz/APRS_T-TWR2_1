#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "lib/LibAPRS_ESP32S3/AFSK.h"
text = path.read_text(encoding="utf-8")

broken_start = """#define AFSK_DAC_IRQ_START()         \\\n    do                               \\\n    {                                \\\n        extern bool hw_afsk_dac_isr; \\\n        hw_afsk_dac_isr = true;      \\\n    } while (0)
"""
fixed_start = """#define AFSK_DAC_IRQ_START()         \\\n    do                               \\\n    {                                \\\n        extern bool hw_afsk_dac_isr; \\\n        hw_afsk_dac_isr = true;      \\\n        (void)0;                      \\\n    } while (0)
"""

broken_stop = """#define AFSK_DAC_IRQ_STOP()          \\\n    do                               \\\n    {                                \\\n        extern bool hw_afsk_dac_isr; \\\n        hw_afsk_dac_isr = false;     \\\n    } while (0)
"""
fixed_stop = """#define AFSK_DAC_IRQ_STOP()          \\\n    do                               \\\n    {                                \\\n        extern bool hw_afsk_dac_isr; \\\n        hw_afsk_dac_isr = false;     \\\n        (void)0;                      \\\n    } while (0)
"""

changed = False
if broken_start in text:
    text = text.replace(broken_start, fixed_start, 1)
    changed = True
if broken_stop in text:
    text = text.replace(broken_stop, fixed_stop, 1)
    changed = True

if not changed:
    if fixed_start in text and fixed_stop in text:
        print("AFSK macros already repaired")
    else:
        raise SystemExit("Unexpected AFSK macro layout; refusing blind edit")
else:
    path.write_text(text, encoding="utf-8")
    print("AFSK Rev2.1 macro continuations repaired")
