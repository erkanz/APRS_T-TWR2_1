#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEM = ROOT / "lib/LibAPRS_ESP32S3/modem.cpp"
MAIN = ROOT / "src/main.cpp"
MAIN_H = ROOT / "include/main.h"
PARSE = ROOT / "src/parse_aprs.cpp"

DUPLICATE = '''extern int8_t adcEn;
extern volatile int8_t adcEn;
'''
CLEAN = '''extern volatile int8_t adcEn;
'''


def normalize_modem_externs() -> None:
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


def patch_main_header() -> None:
    text = MAIN_H.read_text(encoding="utf-8")
    old = '''String trk_gps_postion(String comment);
String trk_fix_position(String comment);
'''
    new = '''String trk_gps_postion(String comment, bool forceUncompressed = true);
String trk_fix_position(String comment, bool forceUncompressed = true);
'''
    if old in text:
        if text.count(old) != 1:
            raise SystemExit(f"ERROR: expected one tracker declaration block in main.h, found {text.count(old)}")
        text = text.replace(old, new, 1)
    elif new not in text:
        raise SystemExit("ERROR: tracker declarations not found in main.h")
    MAIN_H.write_text(text, encoding="utf-8")


def patch_main() -> int:
    main_text = MAIN.read_text(encoding="utf-8")

    # The upstream tracker diagnostics have appeared in more than one printf
    # format (%d/%u and with/without the INTERVAL suffix). Remove by stable
    # message prefix after all compatibility passes so no variant can flood USB.
    had_final_newline = main_text.endswith("\n")
    lines = main_text.splitlines()
    filtered = [line for line in lines if "TRACKER tx_counter=" not in line]
    removed = len(lines) - len(filtered)
    main_text = "\n".join(filtered)
    if had_final_newline:
        main_text += "\n"
    if "TRACKER tx_counter=" in main_text:
        raise SystemExit("ERROR: tracker tx_counter serial diagnostic remains after cleanup")

    # AnyTone interoperability: keep manualBeaconTx() itself byte-for-byte
    # compatible with the deep compatibility pass.  The default argument lives
    # only in include/main.h; do not add a second declaration in this .cpp.
    local_prototypes_true = '''String trk_gps_postion(String comment, bool forceUncompressed = true);
String trk_fix_position(String comment, bool forceUncompressed = true);

'''
    local_prototypes_false = '''String trk_gps_postion(String comment, bool forceUncompressed = false);
String trk_fix_position(String comment, bool forceUncompressed = false);

'''
    main_text = main_text.replace(local_prototypes_true, "", 1)
    main_text = main_text.replace(local_prototypes_false, "", 1)
    manual_anchor = "void manualBeaconTx()\n{\n"
    if manual_anchor not in main_text:
        raise SystemExit("ERROR: manualBeaconTx anchor not found")

    old_gps_sig = "String trk_gps_postion(String comment)\n{"
    new_gps_sig = "String trk_gps_postion(String comment, bool forceUncompressed)\n{"
    if old_gps_sig in main_text:
        main_text = main_text.replace(old_gps_sig, new_gps_sig, 1)
    elif new_gps_sig not in main_text:
        raise SystemExit("ERROR: tracker GPS position function signature not found")

    old_fix_sig = "String trk_fix_position(String comment)\n{"
    new_fix_sig = "String trk_fix_position(String comment, bool forceUncompressed)\n{"
    if old_fix_sig in main_text:
        main_text = main_text.replace(old_fix_sig, new_fix_sig, 1)
    elif new_fix_sig not in main_text:
        raise SystemExit("ERROR: tracker fixed position function signature not found")

    gps_start = main_text.find(new_gps_sig)
    fix_start = main_text.find(new_fix_sig, gps_start)
    if gps_start < 0 or fix_start < 0:
        raise SystemExit("ERROR: tracker function ranges not found")
    gps_part = main_text[gps_start:fix_start]
    if "if (config.trk_compress && !forceUncompressed)" not in gps_part:
        if "if (config.trk_compress)" not in gps_part:
            raise SystemExit("ERROR: GPS tracker compression branch not found")
        gps_part = gps_part.replace("if (config.trk_compress)", "if (config.trk_compress && !forceUncompressed)", 1)
    compat_log = '  if (forceUncompressed)\n    log_i("[APRS COMPAT] beacon format=UNCOMPRESSED");\n'
    if compat_log not in gps_part:
        gps_body_anchor = new_gps_sig + "\n"
        gps_part = gps_part.replace(gps_body_anchor, gps_body_anchor + compat_log, 1)
    main_text = main_text[:gps_start] + gps_part + main_text[fix_start:]

    fix_start = main_text.find(new_fix_sig)
    fix_end = main_text.find("String igate_position(", fix_start)
    if fix_start < 0 or fix_end < 0:
        raise SystemExit("ERROR: fixed tracker function range not found")
    fix_part = main_text[fix_start:fix_end]
    if "if (config.trk_compress && !forceUncompressed)" not in fix_part:
        if "if (config.trk_compress)" not in fix_part:
            raise SystemExit("ERROR: fixed tracker compression branch not found")
        fix_part = fix_part.replace("if (config.trk_compress)", "if (config.trk_compress && !forceUncompressed)", 1)
    if compat_log not in fix_part:
        fix_body_anchor = new_fix_sig + "\n"
        fix_part = fix_part.replace(fix_body_anchor, fix_body_anchor + compat_log, 1)
    main_text = main_text[:fix_start] + fix_part + main_text[fix_end:]

    # Keep the manual function body canonical: its one-argument calls resolve to
    # forceUncompressed=true through include/main.h. Periodic tracker calls are
    # explicit false so they continue honoring config.trk_compress.
    manual_start = main_text.find(manual_anchor)
    manual_end = main_text.find("void burstAfterVoice()", manual_start)
    if manual_start < 0 or manual_end < 0:
        raise SystemExit("ERROR: manual beacon function range not found")
    manual = main_text[manual_start:manual_end]
    if "trk_gps_postion(cmn);" not in manual or "trk_fix_position(cmn);" not in manual:
        raise SystemExit("ERROR: canonical manual beacon tracker calls not found")

    periodic_gps = "rawData = trk_gps_postion(cmn);"
    periodic_fix = "rawData = trk_fix_position(cmn);"
    gps_idx = main_text.rfind(periodic_gps)
    if gps_idx > manual_end:
        main_text = main_text[:gps_idx] + "rawData = trk_gps_postion(cmn, false);" + main_text[gps_idx + len(periodic_gps):]
    elif "rawData = trk_gps_postion(cmn, false);" not in main_text[manual_end:]:
        raise SystemExit("ERROR: periodic GPS tracker call not found")

    # Recompute because the previous replacement changes offsets.
    fix_idx = main_text.rfind(periodic_fix)
    if fix_idx > manual_end:
        main_text = main_text[:fix_idx] + "rawData = trk_fix_position(cmn, false);" + main_text[fix_idx + len(periodic_fix):]
    elif "rawData = trk_fix_position(cmn, false);" not in main_text[manual_end:]:
        raise SystemExit("ERROR: periodic fixed tracker call not found")

    if "TRACKER tx_counter=" in main_text:
        raise SystemExit("ERROR: tracker counter serial spam survived final main patch")
    if local_prototypes_true in main_text or local_prototypes_false in main_text:
        raise SystemExit("ERROR: duplicate local tracker prototypes remain in main.cpp")
    if "trk_gps_postion(cmn, false)" not in main_text or "trk_fix_position(cmn, false)" not in main_text:
        raise SystemExit("ERROR: periodic tracker configured-mode calls missing")

    MAIN.write_text(main_text, encoding="utf-8")
    return removed


def patch_anytone_rx_compat() -> None:
    text = PARSE.read_text(encoding="utf-8")
    marker = "// Rev2.1 AnyTone compatibility: normalize minute-hundredths overflow"
    if marker not in text:
        anchor = '''\t/* 3210.70N/13132.15E# */
\tlog_d("sscanf posbuf='%s'", posbuf);
'''
        compat = '''\t// Rev2.1 AnyTone compatibility: normalize minute-hundredths overflow.
\t// Some analog APRS frames have been observed with e.g. 10849.:0E. The
\t// AX.25 FCS is valid, so this is a sender-side coordinate formatting edge
\t// case: ':' is ASCII '0'+10, representing hundredths 100..109 without the
\t// carry into the minutes field. Repair only that impossible APRS pattern in
\t// the local parser copy; the raw packet remains unchanged in Last Heard.
\tchar compat_original[20];
\tmemcpy(compat_original, posbuf, sizeof(compat_original));
\tauto normalize_minute_overflow = [](char *p, int deg_off, int deg_digits,
\t                                    int min_off, int frac_off, int max_deg) -> bool
\t{
\t\tif (p[frac_off] != ':' || p[frac_off + 1] < '0' || p[frac_off + 1] > '9')
\t\t\treturn false;
\t\tint deg = 0;
\t\tfor (int i = 0; i < deg_digits; ++i)
\t\t{
\t\t\tif (p[deg_off + i] < '0' || p[deg_off + i] > '9')
\t\t\t\treturn false;
\t\t\tdeg = deg * 10 + (p[deg_off + i] - '0');
\t\t}
\t\tif (p[min_off] < '0' || p[min_off] > '9' ||
\t\t    p[min_off + 1] < '0' || p[min_off + 1] > '9')
\t\t\treturn false;
\t\tint minute = (p[min_off] - '0') * 10 + (p[min_off + 1] - '0');
\t\tif (minute > 59)
\t\t\treturn false;
\t\tminute += 1;
\t\tif (minute >= 60)
\t\t{
\t\t\tminute = 0;
\t\t\tdeg += 1;
\t\t}
\t\tif (deg > max_deg)
\t\t\treturn false;
\t\tint tmp = deg;
\t\tfor (int i = deg_digits - 1; i >= 0; --i)
\t\t{
\t\t\tp[deg_off + i] = (char)('0' + (tmp % 10));
\t\t\ttmp /= 10;
\t\t}
\t\tp[min_off] = (char)('0' + minute / 10);
\t\tp[min_off + 1] = (char)('0' + minute % 10);
\t\tp[frac_off] = '0';
\t\treturn true;
\t};
\tbool compat_normalized = false;
\tcompat_normalized |= normalize_minute_overflow(posbuf, 0, 2, 2, 5, 89);
\tcompat_normalized |= normalize_minute_overflow(posbuf, 9, 3, 12, 15, 179);
\tif (compat_normalized)
\t\tlog_w("[APRS COMPAT] normalized malformed position '%s' -> '%s'", compat_original, posbuf);

'''
        if anchor not in text:
            raise SystemExit("ERROR: parse_aprs_uncompressed sscanf anchor not found")
        text = text.replace(anchor, compat + anchor, 1)

    required = [
        marker,
        "normalize_minute_overflow(posbuf, 9, 3, 12, 15, 179)",
        "[APRS COMPAT] normalized malformed position",
    ]
    for item in required:
        if item not in text:
            raise SystemExit(f"ERROR: APRS compatibility invariant missing: {item}")
    PARSE.write_text(text, encoding="utf-8")


def main() -> None:
    normalize_modem_externs()
    patch_main_header()
    removed = patch_main()
    patch_anytone_rx_compat()

    header = MAIN_H.read_text(encoding="utf-8")
    if "String trk_gps_postion(String comment, bool forceUncompressed = true);" not in header:
        raise SystemExit("ERROR: AnyTone tracker declaration missing from main.h")

    print("PASS Rev2.1 late modem adcEn extern normalized")
    print(f"PASS tracker tx_counter serial diagnostics removed: {removed} line(s)")
    print("PASS manual beacon defaults to uncompressed APRS; periodic tracker preserves configured mode")
    print("PASS malformed minute-hundredths APRS compatibility normalization installed")


if __name__ == "__main__":
    main()
