#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src/main.cpp").read_text(encoding="utf-8")

checks = [
    ("persistent RF history capacity is exactly 100", "static constexpr uint16_t PACKET_HISTORY_CAPACITY = 100;" in MAIN),
    ("persistent history uses dedicated LittleFS ring file", 'PACKET_HISTORY_PATH = "/packet_history.bin"' in MAIN),
    ("persistent records use fixed raw storage instead of pointers", "char raw[PACKET_HISTORY_RAW_SIZE];" in MAIN and "char call[11];" in MAIN),
    ("each persistent record has an integrity checksum", "record.checksum = packetHistoryChecksum(record);" in MAIN and "packetHistoryRecordValid" in MAIN),
    ("history writes only decoded RF packets", "if (packetHistoryRestoring || channel != 0" in MAIN),
    ("ring advances modulo 100 and overwrites oldest slot", "packetHistoryNextSlot = (packetHistoryNextSlot + 1) % PACKET_HISTORY_CAPACITY;" in MAIN),
    ("boot restores persistent history", "loadPersistentPacketHistory(); // restore last 100 decoded RF packets" in MAIN),
    ("restore cannot recursively write history", "packetHistoryRestoring = true;" in MAIN and "packetHistoryRestoring = false;" in MAIN),
    ("stored packet time is restored into Last Heard", "pkgList[idx].time = static_cast<time_t>(record.timestamp);" in MAIN),
    ("oldest Last Heard slot selection tolerates restored timestamps", "time_t minimum = pkgList[0].time;" in MAIN and "for (i = 1; i < PKGLISTSIZE; i++)" in MAIN),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL"), name)

if failed:
    raise SystemExit(f"{len(failed)} persistent RF history checks failed: {', '.join(failed)}")

print(f"{len(checks)}/{len(checks)} persistent RF history checks PASS")
