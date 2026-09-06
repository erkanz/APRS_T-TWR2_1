#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AX25 = (ROOT / "lib/LibAPRS_ESP32S3/AX25.cpp").read_text(encoding="utf-8")

checks = [
    ("FX.25 RX has explicit post-flag tag window state", "uint8_t fx25TagWindowBits;" in AX25),
    ("FX.25 tag comparison occurs at exactly 64 post-flag bits", "rx->fx25TagWindowBits == 64" in AX25),
    ("FX.25 tag detector is disarmed outside legal window", "rx->fx25TagWindowBits = 0xFF;" in AX25),
    ("HDLC flag re-arms FX.25 tag window", "The next 64 bits are the only legal location for an FX.25" in AX25 and "rx->fx25TagWindowBits = 0;" in AX25),
    ("continuous rolling FX.25 tag hijack removed", "&& (NULL != (rx->fx25Mode = (struct Fx25Mode*)Fx25GetModeForTag(rx->tag)))" not in AX25),
    ("FX.25 detector still calls correlation matcher", "Fx25GetModeForTag(rx->tag)" in AX25),
    ("consecutive FX.25 block receive remains armed", "Consecutive FX.25 blocks may place the next correlation tag directly" in AX25),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL"), name)

if failed:
    raise SystemExit(f"{len(failed)} FX.25 RX coexistence checks failed: {', '.join(failed)}")

print(f"{len(checks)}/{len(checks)} FX.25 RX coexistence checks PASS")
