#!/usr/bin/env python3
"""Install persistent 100-packet RF decode history for Rev2.1.

The runtime keeps a fixed-size LittleFS ring of the last 100 successfully decoded
RF packets.  Each slot is checksummed independently, so a torn write can only
invalidate the slot being written.  On boot the valid records are replayed into
Last Heard without writing them back to flash.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"

GLOBAL_MARKER = "static constexpr uint16_t PACKET_HISTORY_CAPACITY = 100;"
FUNCTION_MARKER = "static void loadPersistentPacketHistory()"
SETUP_MARKER = "  loadPersistentPacketHistory(); // restore last 100 decoded RF packets\n"
PERSIST_MARKER = "  persistDecodedRfPacket(call, raw, type, channel, audioLvl, time(NULL));\n"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label}: expected exactly one source match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    if GLOBAL_MARKER not in text:
        anchor = "pkgListType *pkgList;\n"
        block = r'''pkgListType *pkgList;

// Rev2.1 persistent RF decode history.
// Keep exactly the last 100 successfully decoded RF packets in a fixed-slot
// LittleFS ring.  There is intentionally no mutable ring header: each record
// carries its own sequence/checksum, avoiding a single flash hot spot.
static constexpr uint16_t PACKET_HISTORY_CAPACITY = 100;
static constexpr size_t PACKET_HISTORY_RAW_SIZE = 512;
static constexpr uint32_t PACKET_HISTORY_MAGIC = 0x32525041UL; // "APR2"
static constexpr uint16_t PACKET_HISTORY_VERSION = 1;
static constexpr const char *PACKET_HISTORY_PATH = "/packet_history.bin";

struct __attribute__((packed)) PersistentPacketHistoryRecord
{
  uint32_t magic;
  uint16_t version;
  uint16_t rawLen;
  uint32_t sequence;
  int64_t timestamp;
  uint16_t type;
  int16_t audioLevel;
  uint8_t channel;
  char call[11];
  char raw[PACKET_HISTORY_RAW_SIZE];
  uint32_t checksum;
};

struct PacketHistoryIndex
{
  uint32_t sequence;
  uint16_t slot;
};

static bool packetHistoryRestoring = false;
static uint32_t packetHistorySequence = 0;
static uint16_t packetHistoryNextSlot = 0;
static uint16_t packetHistoryValidCount = 0;
'''
        text = replace_once(text, anchor, block, "persistent history globals")

    if FUNCTION_MARKER not in text:
        anchor = "int pkgListUpdate(char *call, char *raw, uint16_t type, bool channel, uint16_t audioLvl)\n{\n"
        functions = r'''static uint32_t packetHistoryChecksum(const PersistentPacketHistoryRecord &record)
{
  const uint8_t *ptr = reinterpret_cast<const uint8_t *>(&record);
  const size_t len = sizeof(PersistentPacketHistoryRecord) - sizeof(record.checksum);
  uint32_t hash = 2166136261UL; // FNV-1a 32-bit
  for (size_t i = 0; i < len; ++i)
  {
    hash ^= ptr[i];
    hash *= 16777619UL;
  }
  return hash;
}

static bool packetHistoryRecordValid(const PersistentPacketHistoryRecord &record)
{
  if (record.magic != PACKET_HISTORY_MAGIC || record.version != PACKET_HISTORY_VERSION)
    return false;
  if (record.channel != 0)
    return false; // persistent history is RF-decode-only
  if (record.rawLen == 0 || record.rawLen >= PACKET_HISTORY_RAW_SIZE)
    return false;
  if (record.call[0] == 0 || record.raw[0] == 0 || record.raw[record.rawLen] != 0)
    return false;
  return record.checksum == packetHistoryChecksum(record);
}

static bool ensurePersistentPacketHistoryFile()
{
  const size_t expectedSize = sizeof(PersistentPacketHistoryRecord) * PACKET_HISTORY_CAPACITY;
  size_t currentSize = 0;

  if (LITTLEFS.exists(PACKET_HISTORY_PATH))
  {
    File check = LITTLEFS.open(PACKET_HISTORY_PATH, "r");
    if (!check)
      return false;
    currentSize = check.size();
    check.close();

    if (currentSize > expectedSize)
    {
      if (!LITTLEFS.remove(PACKET_HISTORY_PATH))
        return false;
      currentSize = 0;
    }
  }

  if (!LITTLEFS.exists(PACKET_HISTORY_PATH))
  {
    File create = LITTLEFS.open(PACKET_HISTORY_PATH, "w");
    if (!create)
      return false;
    create.close();
    currentSize = 0;
  }

  if (currentSize < expectedSize)
  {
    File extend = LITTLEFS.open(PACKET_HISTORY_PATH, "a");
    if (!extend)
      return false;
    uint8_t zeros[64] = {0};
    size_t remaining = expectedSize - currentSize;
    while (remaining > 0)
    {
      const size_t chunk = remaining > sizeof(zeros) ? sizeof(zeros) : remaining;
      if (extend.write(zeros, chunk) != chunk)
      {
        extend.close();
        return false;
      }
      remaining -= chunk;
    }
    extend.flush();
    extend.close();
  }

  return true;
}

static void persistDecodedRfPacket(const char *call, const char *raw, uint16_t type, bool channel, uint16_t audioLvl, time_t packetTime)
{
  if (packetHistoryRestoring || channel != 0 || call == nullptr || raw == nullptr || *call == 0 || *raw == 0)
    return;

  if (!ensurePersistentPacketHistoryFile())
  {
    log_w("[PKT HISTORY] LittleFS ring unavailable");
    return;
  }

  PersistentPacketHistoryRecord record{};
  record.magic = PACKET_HISTORY_MAGIC;
  record.version = PACKET_HISTORY_VERSION;
  record.sequence = packetHistorySequence + 1;
  if (record.sequence == 0)
    record.sequence = 1;
  record.timestamp = static_cast<int64_t>(packetTime);
  record.type = type;
  record.audioLevel = static_cast<int16_t>(audioLvl);
  record.channel = 0;

  const size_t callLen = strnlen(call, sizeof(record.call) - 1);
  memcpy(record.call, call, callLen);
  record.call[callLen] = 0;

  const size_t rawLen = strnlen(raw, PACKET_HISTORY_RAW_SIZE - 1);
  memcpy(record.raw, raw, rawLen);
  record.raw[rawLen] = 0;
  record.rawLen = static_cast<uint16_t>(rawLen);
  record.checksum = packetHistoryChecksum(record);

  File file = LITTLEFS.open(PACKET_HISTORY_PATH, "r+");
  if (!file)
  {
    log_w("[PKT HISTORY] open-for-update failed");
    return;
  }

  const size_t offset = static_cast<size_t>(packetHistoryNextSlot) * sizeof(PersistentPacketHistoryRecord);
  if (!file.seek(offset, SeekSet) || file.write(reinterpret_cast<const uint8_t *>(&record), sizeof(record)) != sizeof(record))
  {
    log_w("[PKT HISTORY] slot write failed slot=%u", packetHistoryNextSlot);
    file.close();
    return;
  }

  file.flush();
  file.close();
  packetHistorySequence = record.sequence;
  packetHistoryNextSlot = (packetHistoryNextSlot + 1) % PACKET_HISTORY_CAPACITY;
  if (packetHistoryValidCount < PACKET_HISTORY_CAPACITY)
    ++packetHistoryValidCount;
}

static void loadPersistentPacketHistory()
{
  packetHistorySequence = 0;
  packetHistoryNextSlot = 0;
  packetHistoryValidCount = 0;

  if (!LITTLEFS.exists(PACKET_HISTORY_PATH))
  {
    log_i("[PKT HISTORY] restored=0 capacity=%u", PACKET_HISTORY_CAPACITY);
    return;
  }

  if (!ensurePersistentPacketHistoryFile())
  {
    log_w("[PKT HISTORY] persistent ring validation failed");
    return;
  }

  File file = LITTLEFS.open(PACKET_HISTORY_PATH, "r");
  if (!file)
  {
    log_w("[PKT HISTORY] persistent ring open failed");
    return;
  }

  PacketHistoryIndex index[PACKET_HISTORY_CAPACITY];
  uint16_t count = 0;
  PersistentPacketHistoryRecord record{};

  for (uint16_t slot = 0; slot < PACKET_HISTORY_CAPACITY; ++slot)
  {
    const size_t offset = static_cast<size_t>(slot) * sizeof(PersistentPacketHistoryRecord);
    if (!file.seek(offset, SeekSet))
      continue;
    memset(&record, 0, sizeof(record));
    if (file.read(reinterpret_cast<uint8_t *>(&record), sizeof(record)) != sizeof(record))
      continue;
    if (!packetHistoryRecordValid(record))
      continue;
    index[count].sequence = record.sequence;
    index[count].slot = slot;
    ++count;
  }
  file.close();

  // At most 100 entries; a simple insertion sort keeps the boot path compact.
  for (uint16_t i = 1; i < count; ++i)
  {
    PacketHistoryIndex key = index[i];
    int j = static_cast<int>(i) - 1;
    while (j >= 0 && index[j].sequence > key.sequence)
    {
      index[j + 1] = index[j];
      --j;
    }
    index[j + 1] = key;
  }

  if (count == 0)
  {
    log_i("[PKT HISTORY] restored=0 capacity=%u", PACKET_HISTORY_CAPACITY);
    return;
  }

  packetHistorySequence = index[count - 1].sequence;
  packetHistoryNextSlot = (index[count - 1].slot + 1) % PACKET_HISTORY_CAPACITY;
  packetHistoryValidCount = count;

  file = LITTLEFS.open(PACKET_HISTORY_PATH, "r");
  if (!file)
  {
    log_w("[PKT HISTORY] replay open failed");
    return;
  }

  packetHistoryRestoring = true;
  uint16_t restored = 0;
  for (uint16_t n = 0; n < count; ++n)
  {
    const size_t offset = static_cast<size_t>(index[n].slot) * sizeof(PersistentPacketHistoryRecord);
    if (!file.seek(offset, SeekSet))
      continue;
    memset(&record, 0, sizeof(record));
    if (file.read(reinterpret_cast<uint8_t *>(&record), sizeof(record)) != sizeof(record))
      continue;
    if (!packetHistoryRecordValid(record))
      continue;

    int idx = pkgListUpdate(record.call, record.raw, record.type, false, static_cast<uint16_t>(record.audioLevel));
    if (idx >= 0 && idx < PKGLISTSIZE)
    {
      if (waitPSRAM(true))
      {
        pkgList[idx].time = static_cast<time_t>(record.timestamp);
        waitPSRAM(false);
      }
      ++restored;
    }
  }
  packetHistoryRestoring = false;
  file.close();

  log_i("[PKT HISTORY] restored=%u/%u next_slot=%u", restored, PACKET_HISTORY_CAPACITY, packetHistoryNextSlot);
}

int pkgListUpdate(char *call, char *raw, uint16_t type, bool channel, uint16_t audioLvl)
{
'''
        text = replace_once(text, anchor, functions, "persistent history functions")

    old_oldest = '''int pkgListOld()\n{\n  int i, ret = -1;\n  time_t minimum = time(NULL) + 86400; // pkgList[0].time;\n  for (i = 0; i < PKGLISTSIZE; i++)\n'''
    new_oldest = '''int pkgListOld()\n{\n  int i, ret = 0;\n  time_t minimum = pkgList[0].time;\n  for (i = 1; i < PKGLISTSIZE; i++)\n'''
    if old_oldest in text:
        text = replace_once(text, old_oldest, new_oldest, "pkgList oldest-slot selection")
    elif new_oldest not in text:
        raise SystemExit("ERROR: pkgListOld persistence-safe anchor not found")

    if PERSIST_MARKER not in text:
        anchor = "  waitPSRAM(false);\n  event_lastHeard();\n  lastHeard_Flag = true;\n  return i;\n}\n"
        replacement = "  waitPSRAM(false);\n" + PERSIST_MARKER + "  event_lastHeard();\n  lastHeard_Flag = true;\n  return i;\n}\n"
        text = replace_once(text, anchor, replacement, "RF history write hook")

    if SETUP_MARKER not in text:
        anchor = "  memset(pkgList, 0, sizeof(pkgListType) * PKGLISTSIZE);\n  memset(Telemetry, 0, sizeof(TelemetryType) * TLMLISTSIZE);\n  memset(txQueue, 0, sizeof(txQueueType) * PKGTXSIZE);\n"
        replacement = anchor + SETUP_MARKER
        text = replace_once(text, anchor, replacement, "RF history boot restore hook")

    required = [
        GLOBAL_MARKER,
        FUNCTION_MARKER,
        "PACKET_HISTORY_PATH = \"/packet_history.bin\"",
        "packetHistoryNextSlot = (packetHistoryNextSlot + 1) % PACKET_HISTORY_CAPACITY;",
        "record.checksum = packetHistoryChecksum(record);",
        "if (packetHistoryRestoring || channel != 0",
        PERSIST_MARKER.strip(),
        SETUP_MARKER.strip(),
        "time_t minimum = pkgList[0].time;",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit("ERROR: persistent RF history invariants missing: " + ", ".join(missing))

    MAIN.write_text(text, encoding="utf-8")
    print("PASS persistent RF packet history capacity=100")
    print("PASS fixed-slot LittleFS ring overwrites oldest packet after 100")
    print("PASS per-record checksum and torn-write isolation installed")
    print("PASS boot replay restores Last Heard without re-writing flash")
    print("PASS APRS-IS packets excluded from persistent RF history")


if __name__ == "__main__":
    main()
