#!/usr/bin/env python3
from pathlib import Path
import csv
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".pio/build/esp32s3-twrplus"
DIST = ROOT / "dist"
FLASH_SIZE = 0x1000000  # 16 MiB
APP_SLOT_SIZE = 0x400000

checks = []
def expect(name, condition, detail=""):
    ok = bool(condition)
    checks.append((name, ok, detail))
    print(("PASS" if ok else "FAIL") + f"  {name}" + (f" — {detail}" if detail else ""))


def image_header(path: Path):
    data = path.read_bytes()
    if len(data) < 8:
        raise RuntimeError(f"{path} is too short to be an ESP image")
    return data, data[0], data[1], data[2], data[3]


def parse_size(value: str) -> int:
    value = value.strip()
    if value.lower().startswith("0x"):
        return int(value, 16)
    suffix = value[-1:].upper()
    if suffix == "K":
        return int(value[:-1]) * 1024
    if suffix == "M":
        return int(value[:-1]) * 1024 * 1024
    return int(value, 10)


def source_partitions():
    rows = []
    with (ROOT / "partitions.csv").open(newline="", encoding="utf-8") as f:
        for raw in csv.reader(f):
            if not raw or raw[0].strip().startswith("#"):
                continue
            if len(raw) < 5:
                continue
            label = raw[0].strip()
            offset = parse_size(raw[3])
            size = parse_size(raw[4])
            rows.append((label, offset, size))
    return rows


def binary_partitions(path: Path):
    data = path.read_bytes()
    rows = []
    for pos in range(0, len(data), 32):
        entry = data[pos:pos + 32]
        if len(entry) < 32:
            break
        magic = struct.unpack_from("<H", entry, 0)[0]
        if magic == 0xFFFF:
            break
        if magic != 0x50AA:
            continue
        offset, size = struct.unpack_from("<II", entry, 4)
        label = entry[12:28].split(b"\0", 1)[0].decode("ascii", errors="replace")
        rows.append((label, offset, size))
    return rows


def main():
    board = json.loads((ROOT / "boards/LilyGo-T-TWR-Plus.json").read_text(encoding="utf-8"))
    build = board["build"]
    arduino = build["arduino"]
    expect("official board memory topology", arduino.get("memory_type") == "qio_opi", arduino.get("memory_type", "missing"))
    expect("official board flash mode setting", build.get("flash_mode") == "qio", build.get("flash_mode", "missing"))
    expect("official board flash clock", build.get("f_flash") == "80000000L", build.get("f_flash", "missing"))
    expect("official board flash size", board["upload"].get("flash_size") == "16MB", board["upload"].get("flash_size", "missing"))

    boot_path = BUILD / "bootloader.bin"
    app_path = BUILD / "firmware.bin"
    part_path = BUILD / "partitions.bin"
    for p in (boot_path, app_path, part_path):
        expect(f"build output exists: {p.name}", p.is_file())

    boot, magic, segments, mode, sizefreq = image_header(boot_path)
    expect("bootloader ESP image magic", magic == 0xE9, f"0x{magic:02X}")
    # PlatformIO's Arduino ESP32 builder intentionally normalizes board qio/qout
    # to a DIO ROM-bootstrap image. The second-stage software bootloader then
    # enables Quad I/O according to the configured qio memory profile. Therefore
    # 0x02 here is expected and must NOT be treated as a failed QIO configuration.
    expect("bootloader ROM bootstrap mode is expected DIO", mode == 0x02, f"header mode=0x{mode:02X}")
    expect("bootloader header advertises 16MB/80MHz", sizefreq == 0x4F, f"header size/freq=0x{sizefreq:02X}")

    app, amag, asegments, amode, asizefreq = image_header(app_path)
    expect("application ESP image magic", amag == 0xE9, f"0x{amag:02X}")
    expect("application image header generated with DIO bootstrap mode", amode == 0x02, f"header mode=0x{amode:02X}")
    expect("application header advertises 16MB/80MHz", asizefreq == 0x4F, f"header size/freq=0x{asizefreq:02X}")
    expect("application fits 4MiB OTA slot", len(app) <= APP_SLOT_SIZE, f"{len(app)} / {APP_SLOT_SIZE} bytes")

    src_parts = source_partitions()
    bin_parts = binary_partitions(part_path)
    expect("partition binary matches partitions.csv labels/offsets/sizes", src_parts == bin_parts, f"{len(bin_parts)} entries")
    expected = {
        "nvs": (0x9000, 0x5000),
        "otadata": (0xE000, 0x2000),
        "app0": (0x10000, 0x400000),
        "app1": (0x410000, 0x400000),
        "spiffs": (0x810000, 0x7E0000),
        "coredump": (0xFF0000, 0x10000),
    }
    actual = {label: (offset, size) for label, offset, size in src_parts}
    expect("Rev2.1 OTA/LittleFS partition map exact", actual == expected)

    ordered = sorted(src_parts, key=lambda x: x[1])
    no_overlap = all(ordered[i][1] + ordered[i][2] <= ordered[i + 1][1] for i in range(len(ordered) - 1))
    expect("partition regions do not overlap", no_overlap)
    flash_end = max(offset + size for _, offset, size in ordered)
    expect("partition map ends exactly at 16MiB", flash_end == FLASH_SIZE, f"0x{flash_end:X}")

    if DIST.exists():
        full = DIST / "TWR_APRS_Rev21_FULL_INSTALL.bin"
        update = DIST / "TWR_APRS_Rev21_UPDATE.bin"
        dist_boot = DIST / "bootloader.bin"
        dist_part = DIST / "partitions.bin"
        boot_app = DIST / "boot_app0.bin"
        for p in (full, update, dist_boot, dist_part, boot_app):
            expect(f"packaged output exists: {p.name}", p.is_file())
        if all(p.is_file() for p in (full, update, dist_boot, dist_part, boot_app)):
            merged = full.read_bytes()
            ub = update.read_bytes()
            bb = dist_boot.read_bytes()
            pb = dist_part.read_bytes()
            ob = boot_app.read_bytes()
            expect("packaged UPDATE equals compiled firmware", ub == app)
            expect("packaged bootloader equals compiled bootloader", bb == boot)
            expect("packaged partitions equals compiled partitions", pb == part_path.read_bytes())
            expect("merged bootloader region exact", merged[0:len(bb)] == bb)
            expect("merged partition region exact", merged[0x8000:0x8000 + len(pb)] == pb)
            expect("merged boot_app0 region exact", merged[0xE000:0xE000 + len(ob)] == ob)
            expect("merged application region exact", merged[0x10000:0x10000 + len(ub)] == ub)
            expect("merged install image stays inside 16MiB", len(merged) <= FLASH_SIZE, f"{len(merged)} bytes")

    failed = [name for name, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} binary checks passed")
    if failed:
        print("FAILED binary checks:", file=sys.stderr)
        for name in failed:
            print(" - " + name, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
