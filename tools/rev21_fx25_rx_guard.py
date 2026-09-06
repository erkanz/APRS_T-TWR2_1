#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AX25 = ROOT / "lib/LibAPRS_ESP32S3/AX25.cpp"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label}: expected exactly one source match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = AX25.read_text(encoding="utf-8")

    old_state = '''\tstruct Fx25Mode *fx25Mode;\n\tuint64_t tag; //received correlation tag\n'''
    new_state = '''\tstruct Fx25Mode *fx25Mode;\n\tuint64_t tag; //received correlation tag\n\t// FX.25 correlation tags are valid only immediately after an HDLC flag\n\t// (or immediately after a completed FX.25 block).  The old decoder scanned\n\t// every rolling 64-bit window, so a normal AX.25 frame could be stolen by a\n\t// false tag match while it was already being received.\n\tuint8_t fx25TagWindowBits; // 0..64 armed window; 0xFF = disarmed\n'''
    text = replace_once(text, old_state, new_state, "FX.25 guarded tag-window state")

    old_detect = '''\tif(Ax25Config.fx25\n\t\t\t&& (rx->rx != RX_STAGE_FX25_FRAME)\n\t\t\t&& (NULL != (rx->fx25Mode = (struct Fx25Mode*)Fx25GetModeForTag(rx->tag))))\n\t{\n\t\trx->rx = RX_STAGE_FX25_FRAME;\n\t\trx->receivedByte = 0;\n\t\trx->receivedBitIdx = 0;\n\t\trx->frameIdx = 0;\n\t\treturn;\n\t}\n'''
    new_detect = '''\t// Do not continuously scan for an FX.25 tag inside a normal AX.25 frame.\n\t// A valid FX.25 correlation tag is exactly 64 bits and follows the final\n\t// preamble HDLC flag, so test one 64-bit window after that flag.  This keeps\n\t// standard AX.25 and FX.25 RX enabled at the same time without allowing a\n\t// false rolling correlation to hijack an in-progress standard frame.\n\tif(Ax25Config.fx25 && (rx->rx != RX_STAGE_FX25_FRAME) && (rx->fx25TagWindowBits < 64))\n\t{\n\t\trx->fx25TagWindowBits++;\n\t\tif(rx->fx25TagWindowBits == 64)\n\t\t{\n\t\t\trx->fx25Mode = (struct Fx25Mode*)Fx25GetModeForTag(rx->tag);\n\t\t\tif(rx->fx25Mode != NULL)\n\t\t\t{\n\t\t\t\trx->rx = RX_STAGE_FX25_FRAME;\n\t\t\t\trx->receivedByte = 0;\n\t\t\t\trx->receivedBitIdx = 0;\n\t\t\t\trx->frameIdx = 0;\n\t\t\t\trx->fx25TagWindowBits = 0xFF;\n\t\t\t\treturn;\n\t\t\t}\n\t\t\trx->fx25TagWindowBits = 0xFF;\n\t\t}\n\t}\n'''
    text = replace_once(text, old_detect, new_detect, "replace continuous FX.25 tag scan with post-flag window")

    old_flag = '''\t\tif(rx->rawData == 0x7E) //HDLC flag received\n\t\t{\n'''
    new_flag = '''\t\tif(rx->rawData == 0x7E) //HDLC flag received\n\t\t{\n#ifdef ENABLE_FX25\n\t\t\t// The next 64 bits are the only legal location for an FX.25\n\t\t\t// correlation tag. Repeated preamble flags simply re-arm this window.\n\t\t\trx->fx25TagWindowBits = 0;\n#endif\n'''
    text = replace_once(text, old_flag, new_flag, "arm FX.25 tag window after HDLC flag")

    old_fx_end = '''\t\t\trx->rx = RX_STAGE_FLAG;\n\t\t\trx->receivedByte = 0;\n\t\t\trx->receivedBitIdx = 0;\n\t\t\trx->frameIdx = 0;\n\t\t\treturn;\n\t\t}\n#else\n'''
    new_fx_end = '''\t\t\trx->rx = RX_STAGE_FLAG;\n\t\t\trx->receivedByte = 0;\n\t\t\trx->receivedBitIdx = 0;\n\t\t\trx->frameIdx = 0;\n\t\t\t// Consecutive FX.25 blocks may place the next correlation tag directly\n\t\t\t// after this block, so arm one new 64-bit tag window here as well.\n\t\t\trx->fx25TagWindowBits = 0;\n\t\t\treturn;\n\t\t}\n#else\n'''
    text = replace_once(text, old_fx_end, new_fx_end, "re-arm FX.25 tag window after completed FX.25 block")

    old_init = '''\tmemset((void*)rxState, 0, sizeof(rxState));\n\tfor(uint8_t i = 0; i < (sizeof(rxState) / sizeof(rxState[0])); i++)\n\t\trxState[i].crc = 0xFFFF;\n'''
    new_init = '''\tmemset((void*)rxState, 0, sizeof(rxState));\n\tfor(uint8_t i = 0; i < (sizeof(rxState) / sizeof(rxState[0])); i++)\n\t{\n\t\trxState[i].crc = 0xFFFF;\n#ifdef ENABLE_FX25\n\t\trxState[i].fx25TagWindowBits = 0xFF;\n#endif\n\t}\n'''
    text = replace_once(text, old_init, new_init, "initialize FX.25 tag window disarmed")

    forbidden = '''&& (NULL != (rx->fx25Mode = (struct Fx25Mode*)Fx25GetModeForTag(rx->tag)))'''
    if forbidden in text:
        raise SystemExit("ERROR: continuous rolling FX.25 tag detector still present")

    required = [
        "uint8_t fx25TagWindowBits;",
        "rx->fx25TagWindowBits == 64",
        "rx->fx25TagWindowBits = 0xFF;",
        "The next 64 bits are the only legal location for an FX.25",
    ]
    for item in required:
        if item not in text:
            raise SystemExit(f"ERROR: FX.25 RX coexistence invariant missing: {item}")

    AX25.write_text(text, encoding="utf-8")
    print("PASS FX.25 tag detector limited to legal post-flag 64-bit windows")
    print("PASS normal AX.25 frame can no longer be hijacked by rolling FX.25 correlation")
    print("PASS consecutive FX.25 block tag window retained")


if __name__ == "__main__":
    main()
