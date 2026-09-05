#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"
AFSK = ROOT / "lib/LibAPRS_ESP32S3/AFSK.cpp"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"SKIP  {label}")
        return text
    if old not in text:
        raise RuntimeError(f"unexpected source while applying: {label}")
    print(f"PATCH {label}")
    return text.replace(old, new, 1)


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    # LilyGO initializes MIC_CTRL_PIN as open-drain; routing LOW selects the
    # normal microphone/radio path and HIGH releases it to the ESP-audio path.
    text = replace_once(
        text,
        '''    pinMode(SA868_MIC_SEL, OUTPUT); // MIC_SEL\n    digitalWrite(SA868_MIC_SEL, LOW);''',
        '''    pinMode(SA868_MIC_SEL, OUTPUT_OPEN_DRAIN); // Rev2.1 MIC_CTRL routing\n    digitalWrite(SA868_MIC_SEL, LOW); // normal microphone/radio path''',
        "match official Rev2.1 MIC_CTRL open-drain routing",
    )

    # Generic radio sleep must deassert active-low PTT and restore the normal
    # audio route before dropping PD.
    text = replace_once(
        text,
        '''  else\n    rev21SetRfPower(LOW);\n  digitalWrite(PULLDOWN_PIN, LOW);\n  // PMU.disableDC3();''',
        '''  else\n    rev21SetRfPower(LOW);\n  digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 RX/idle before radio sleep\n  digitalWrite(SA868_MIC_SEL, LOW);  // normal microphone/radio audio route\n  digitalWrite(PULLDOWN_PIN, LOW);   // SA868 PD asserted\n  // PMU.disableDC3();''',
        "make RF_MODULE_SLEEP PTT/audio/PD ordering safe",
    )

    # Runtime recovery performs a PD cycle. Use the same safe ordering so a
    # failed module probe can never leave the radio keyed while power-cycling it.
    text = replace_once(
        text,
        '''    rev21SetRfPower(LOW);\n    pinMode(PULLDOWN_PIN, OUTPUT);\n    digitalWrite(PULLDOWN_PIN, LOW);\n    delay(500);\n    RF_MODULE(true);''',
        '''    rev21SetRfPower(LOW);\n    digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 RX/idle before recovery cycle\n    digitalWrite(SA868_MIC_SEL, LOW);  // normal microphone/radio audio route\n    pinMode(PULLDOWN_PIN, OUTPUT);\n    digitalWrite(PULLDOWN_PIN, LOW);   // SA868 PD asserted\n    delay(500);\n    RF_MODULE(true);''',
        "make RF_MODULE_CHECK recovery PTT/audio/PD ordering safe",
    )

    MAIN.write_text(text, encoding="utf-8")


def patch_afsk() -> None:
    text = AFSK.read_text(encoding="utf-8")

    # Official LilyGO SA868 driver uses GPIO41 as a push-pull output:
    # LOW=TX, HIGH=RX/idle. The legacy APRS library used open-drain for the
    # active-low case, which is unnecessary on Rev2.1 and depends on a pull-up.
    text = replace_once(
        text,
        '''    else\n    { // Open Collector to LOW\n      pinMode(_ptt_pin, OUTPUT_OPEN_DRAIN);\n      digitalWrite(_ptt_pin, LOW);\n    }''',
        '''    else\n    { // Rev2.1 active LOW PTT: push-pull LOW=TX\n      pinMode(_ptt_pin, OUTPUT);\n      digitalWrite(_ptt_pin, LOW);\n    }''',
        "drive Rev2.1 PTT LOW as push-pull output",
    )

    text = replace_once(
        text,
        '''    else\n    { // Open Collector to HIGH\n      pinMode(_ptt_pin, OUTPUT_OPEN_DRAIN);\n      digitalWrite(_ptt_pin, HIGH);\n    }''',
        '''    else\n    { // Rev2.1 active LOW PTT: push-pull HIGH=RX/idle\n      pinMode(_ptt_pin, OUTPUT);\n      digitalWrite(_ptt_pin, HIGH);\n    }''',
        "drive Rev2.1 PTT HIGH idle as push-pull output",
    )

    text = replace_once(
        text,
        '''  else\n  { // Open Collector to HIGH\n    pinMode(_ptt_pin, OUTPUT_OPEN_DRAIN);\n    digitalWrite(_ptt_pin, HIGH);\n  }''',
        '''  else\n  { // Rev2.1 active LOW PTT: push-pull HIGH=RX/idle\n    pinMode(_ptt_pin, OUTPUT);\n    digitalWrite(_ptt_pin, HIGH);\n  }''',
        "initialize Rev2.1 active-low PTT as push-pull HIGH idle",
    )

    AFSK.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_main()
    patch_afsk()
    print("Rev2.1 radio safety normalization applied.")
