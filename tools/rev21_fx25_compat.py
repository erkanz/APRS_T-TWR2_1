#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"
WEB = ROOT / "src/webservice.cpp"
AX25 = ROOT / "lib/LibAPRS_ESP32S3/AX25.cpp"


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    old_default = "  config.fx25_mode = 2;"
    new_default = "  config.fx25_mode = 1; // Rev2.1 default: FX.25 RX-only; standard AX.25/APRS TX"
    if old_default in text:
        if text.count(old_default) != 1:
            raise SystemExit(f"ERROR: expected one FX.25 factory default, found {text.count(old_default)}")
        text = text.replace(old_default, new_default, 1)
    elif new_default not in text:
        raise SystemExit("ERROR: FX.25 factory default anchor not found")

    anchor = "  afskSetModem(config.modem_type, config.audio_lpf, config.tx_timeslot, config.preamble * 100,config.fx25_mode);\n"
    diag = anchor + "  if (config.fx25_mode == 2)\n    log_w(\"[FX25] RX+TX active: RF TX uses FX.25 FEC; standard AX.25/APRS radios may not decode it.\");\n  else if (config.fx25_mode == 1)\n    log_i(\"[FX25] RX-only active: RF TX remains standard AX.25/APRS.\");\n"
    if diag not in text:
        if text.count(anchor) != 1:
            raise SystemExit(f"ERROR: expected one afskSetModem anchor, found {text.count(anchor)}")
        text = text.replace(anchor, diag, 1)

    if "config.fx25_mode = 2;" in text:
        raise SystemExit("ERROR: legacy RX+TX FX.25 factory default remains")
    if "[FX25] RX-only active: RF TX remains standard AX.25/APRS." not in text:
        raise SystemExit("ERROR: FX.25 RX-only compatibility diagnostic missing")

    MAIN.write_text(text, encoding="utf-8")


def patch_web() -> None:
    text = WEB.read_text(encoding="utf-8")
    old = "</select>  (FX.25 = AX.25 + FEC)"
    new = "</select>  (RX recommended: standard AX.25 TX; RX+TX sends FX.25 FEC and may not decode on standard APRS radios)"
    if old in text:
        text = text.replace(old, new)
    elif new not in text:
        raise SystemExit("ERROR: FX.25 web compatibility note anchor not found")
    WEB.write_text(text, encoding="utf-8")


def verify_mode_mapping() -> None:
    text = AX25.read_text(encoding="utf-8")
    required = [
        "if(fx25Mode==0){",
        "Ax25Config.fx25 = 0;",
        "Ax25Config.fx25Tx = 0;",
        "}else if(fx25Mode==1){",
        "Ax25Config.fx25 = 1;",
        "Ax25Config.fx25Tx = 1;",
        "if(Ax25Config.fx25 && Ax25Config.fx25Tx)",
    ]
    for item in required:
        if item not in text:
            raise SystemExit(f"ERROR: FX.25 mode mapping invariant missing: {item}")

    rx_only = text.find("}else if(fx25Mode==1){")
    rx_tx = text.find("}else{", rx_only)
    if rx_only < 0 or rx_tx < 0:
        raise SystemExit("ERROR: FX.25 mode mapping ranges not found")
    rx_only_block = text[rx_only:rx_tx]
    if "Ax25Config.fx25 = 1;" not in rx_only_block or "Ax25Config.fx25Tx = 0;" not in rx_only_block:
        raise SystemExit("ERROR: FX.25 mode 1 is not RX-only")


def main() -> None:
    patch_main()
    patch_web()
    verify_mode_mapping()
    print("PASS FX.25 factory default changed from RX+TX to RX-only")
    print("PASS FX.25 RX-only preserves standard AX.25/APRS RF TX")
    print("PASS FX.25 RX+TX compatibility warning installed")
    print("PASS explicit user FX.25 mode remains configurable; no saved setting is forcibly migrated")


if __name__ == "__main__":
    main()
