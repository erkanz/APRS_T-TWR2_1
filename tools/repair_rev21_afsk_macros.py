#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "lib/LibAPRS_ESP32S3/AFSK.h"
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

changed = 0
i = 0
while i + 2 < len(lines):
    line = lines[i]
    if ("hw_afsk_dac_isr = true;" in line or "hw_afsk_dac_isr = false;" in line) and line.rstrip().endswith("\\"):
        if lines[i + 1].strip() == "" and "} while (0)" in lines[i + 2]:
            lines[i + 1] = "        (void)0;                      \\\n"
            changed += 1
            i += 2
    i += 1

text = "".join(lines)

if changed == 0:
    # Idempotent path: once the source itself has been committed, the repair
    # must be a no-op rather than a failure.
    starts = text.count("(void)0;                      \\")
    if starts >= 2 and "digitalWrite(LED_TX_PIN" not in text:
        print("AFSK macros already repaired")
    else:
        raise SystemExit("Unexpected AFSK macro layout; refusing blind edit")
else:
    if changed != 2:
        raise SystemExit(f"Expected to repair 2 AFSK macros, repaired {changed}")
    path.write_text(text, encoding="utf-8")
    print("AFSK Rev2.1 macro continuations repaired: 2")
