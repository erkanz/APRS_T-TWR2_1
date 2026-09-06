#!/usr/bin/env python3
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]

# Preserve all established Rev2.1 RF/hardware regression checks.
runpy.run_path(str(ROOT / "tools/verify_rev21_hw_validation_base.py"), run_name="__main__")

MAIN = (ROOT / "src/main.cpp").read_text(encoding="utf-8")
WEB = (ROOT / "src/webservice.cpp").read_text(encoding="utf-8")
AX25 = (ROOT / "lib/LibAPRS_ESP32S3/AX25.cpp").read_text(encoding="utf-8")

rx_only = AX25.find("}else if(fx25Mode==1){")
rx_tx = AX25.find("}else{", rx_only)
rx_only_block = AX25[rx_only:rx_tx] if rx_only >= 0 and rx_tx > rx_only else ""

checks = [
    ("FX.25 factory default is RX-only", "config.fx25_mode = 1; // Rev2.1 default: FX.25 RX-only; standard AX.25/APRS TX" in MAIN),
    ("FX.25 RX-only maps to RX enabled / TX disabled", "Ax25Config.fx25 = 1;" in rx_only_block and "Ax25Config.fx25Tx = 0;" in rx_only_block),
    ("FX.25 RX+TX TX path remains explicit opt-in", "if(Ax25Config.fx25 && Ax25Config.fx25Tx)" in AX25),
    ("FX.25 standard-APRS compatibility diagnostic present", "[FX25] RX-only active: RF TX remains standard AX.25/APRS." in MAIN),
    ("FX.25 web UI warns about RX+TX interoperability", "RX recommended: standard AX.25 TX; RX+TX sends FX.25 FEC and may not decode on standard APRS radios" in WEB),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL"), name)

if failed:
    raise SystemExit(f"{len(failed)} FX.25 interoperability checks failed: {', '.join(failed)}")

print(f"{len(checks)}/{len(checks)} FX.25 interoperability checks PASS")
runpy.run_path(str(ROOT / "tools/verify_rev21_fx25_rx_guard.py"), run_name="__main__")
