#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    old = '''#ifdef __XTENSA__
                    //esp_sleep_enable_ext1_wakeup(0x1, ESP_EXT1_WAKEUP_ALL_LOW);
                    esp_sleep_enable_ext1_wakeup(0x0, ESP_EXT1_WAKEUP_ALL_LOW);
#else
                    esp_deep_sleep_enable_gpio_wakeup((1 << 9), ESP_GPIO_WAKEUP_GPIO_LOW);
#endif
                    esp_sleep_enable_timer_wakeup((uint64_t)config.pwr_sleep_interval * uS_TO_S_FACTOR);'''

    new = '''#ifdef __XTENSA__
                    // ESP32-S3 Rev2.1 Mode C is timer-wake only. The legacy code
                    // configured EXT1 with mask 0x0 and ALL_LOW; mask 0 selects
                    // no GPIO and ALL_LOW is unsupported/deprecated on ESP32-S3.
                    // Do not invent a wake GPIO: the configured timer below is
                    // the only valid wake source for this mode in this firmware.
#else
                    esp_deep_sleep_enable_gpio_wakeup((1 << 9), ESP_GPIO_WAKEUP_GPIO_LOW);
#endif
                    esp_sleep_enable_timer_wakeup((uint64_t)config.pwr_sleep_interval * uS_TO_S_FACTOR);'''

    if new in text:
        print("SKIP  ESP32-S3 Mode C timer-only wake already normalized")
    elif old in text:
        text = text.replace(old, new, 1)
        print("PATCH remove invalid ESP32-S3 EXT1 zero-mask/ALL_LOW wake source")
    else:
        raise RuntimeError("unexpected Mode C deep-sleep wake block; refusing blind edit")

    # Remove stale commented references to the ESP32-only ALL_LOW enum in other
    # legacy sleep branches. This touches comments only; any active occurrence is
    # intentionally left intact so the invariant verifier will still reject it.
    text, comment_count = re.subn(
        r'^(\s*//.*)ESP_EXT1_WAKEUP_ALL_LOW(.*)$',
        r'\1legacy_ALL_LOW\2',
        text,
        flags=re.MULTILINE,
    )
    if comment_count:
        print(f"PATCH remove stale ALL_LOW enum name from {comment_count} comment lines")
    else:
        print("SKIP  no stale ALL_LOW enum comments remain")

    MAIN.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_main()
    print("Rev2.1 ESP32-S3 sleep compatibility fix applied.")
