#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/main.cpp"
PIO = ROOT / "platformio.ini"


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

    # Rev2.1 hardware pins are invariants, not user-remappable settings.
    profile_old = '''  config.adc_sel_gpio = -1;\n  config.dac_sel_gpio = 17;    // audio mux\n}'''
    profile_new = '''  config.adc_sel_gpio = -1;\n  config.dac_sel_gpio = 17;    // Rev2.1 microphone/audio routing switch\n  config.i2c_enable = true;\n  config.i2c_sda_pin = 8;\n  config.i2c_sck_pin = 9;\n  config.i2c_freq = 400000;\n}'''
    text = replace_once(text, profile_old, profile_new,
                        "force Rev2.1 I2C pins/frequency in hardware profile")

    # GPIO38 is absent as an RF H/L selector on Rev2.1.  NiceRF SA868S firmware
    # instead uses DMOSETGROUP parameter 0 for HIGH and 1 for LOW power.
    helper_old = '''// Rev2.1 has no GPIO-controlled RF-power rail.  GPIO38 belongs to Rev2.0.\nstatic inline void rev21SetRfPower(bool highPower)\n{\n  (void)highPower;\n}\n'''
    helper_new = '''// Rev2.1 has no GPIO38 H/L selector.  SA868S NiceRF firmware uses\n// DMOSETGROUP parameter 0=HIGH, 1=LOW for TX power.  The legacy helper stays\n// a no-op because changing power is applied atomically when RF_MODULE()\n// reprograms the radio (web radio changes set RF_INIT=true).\nstatic inline uint8_t rev21Sa868PowerBit(bool highPower)\n{\n  return highPower ? 0 : 1;\n}\n\nstatic inline void rev21SetRfPower(bool highPower)\n{\n  (void)highPower;\n}\n'''
    text = replace_once(text, helper_old, helper_new,
                        "map Rev2.1 SA868S RF power to DMOSETGROUP semantics")

    # Never key the active-low PTT during radio boot.  afskSetPTT() has already
    # established idle HIGH, and RF_MODULE must preserve it while cycling PD.
    boot_ptt_old = '''    digitalWrite(SA868_PTT_PIN,LOW);\n    \n    // pinMode(config.rf_tx_gpio,OUTPUT);'''
    boot_ptt_new = '''    pinMode(SA868_PTT_PIN, OUTPUT);\n    digitalWrite(SA868_PTT_PIN, HIGH); // Rev2.1 idle/RX; PTT is active LOW\n    \n    // pinMode(config.rf_tx_gpio,OUTPUT);'''
    text = replace_once(text, boot_ptt_old, boot_ptt_new,
                        "hold GPIO41 HIGH/idle throughout SA868 boot")

    # SA868S Rev2.1: first DMOSETGROUP parameter is TX power, not the separate
    # legacy NW-band setting. HIGH=true -> 0, LOW=false -> 1.
    group_old = '''sprintf(str, "AT+DMOSETGROUP=%01d,%0.4f,%0.4f,%04d,%01d,%04d\\r\\n", config.band, config.freq_tx, config.freq_rx, config.tone_tx, config.sql_level, config.tone_rx);'''
    group_new = '''sprintf(str, "AT+DMOSETGROUP=%01d,%0.4f,%0.4f,%04d,%01d,%04d\\r\\n", rev21Sa868PowerBit(config.rf_power), config.freq_tx, config.freq_rx, config.tone_tx, config.sql_level, config.tone_rx);'''
    text = replace_once(text, group_old, group_new,
                        "program SA868S HIGH/LOW power from config.rf_power")

    # Let XPowers initialize the shared I2C bus once.  Calling Wire.begin()
    # immediately before PMU.begin(...pins...) produces Arduino-ESP32 3.x
    # 'Bus already started' warnings.  Restore the desired 400 kHz after PMU init.
    i2c_old = '''  config.i2c_enable = true;\n  Wire.begin(config.i2c_sda_pin, config.i2c_sck_pin, config.i2c_freq);\n\n  // Setup Power PMU AXP2101\n  setupPower();\n'''
    i2c_new = '''  config.i2c_enable = true;\n\n  // Setup Power PMU AXP2101. PMU.begin() initializes Wire on Rev2.1 pins.\n  setupPower();\n  Wire.setClock(config.i2c_freq);\n'''
    text = replace_once(text, i2c_old, i2c_new,
                        "initialize the shared Rev2.1 I2C bus only once")

    # PMU retry log must describe an actual failed attempt, not print an error
    # unconditionally before the first successful begin().
    pmu_loop_old = '''  while (result == false)\n  {\n    log_d("PMU is not online...");\n    delay(500);\n    result = PMU.begin(Wire, AXP2101_SLAVE_ADDRESS, I2C_SDA_SYS, I2C_SCL_SYS);\n    if (result)\n      break;\n    c++;\n    if (c > 10)\n      return;\n  }\n'''
    pmu_loop_new = '''  while (result == false)\n  {\n    result = PMU.begin(Wire, AXP2101_SLAVE_ADDRESS, I2C_SDA_SYS, I2C_SCL_SYS);\n    if (result)\n      break;\n    c++;\n    log_w("PMU init failed, retry %d/10", c);\n    if (c > 10)\n    {\n      log_e("PMU initialization failed");\n      return;\n    }\n    delay(500);\n  }\n'''
    text = replace_once(text, pmu_loop_old, pmu_loop_new,
                        "make PMU retry diagnostics truthful")

    # Match LilyGO Rev2.1 idle power domains.  ALDO2=SD, ALDO4=GNSS,
    # BLDO1=microphone are enabled. DC3/DC5/ALDO1/ALDO3/BLDO2/DLDO1 are off.
    rails_old = '''  //! External pin power supply\n  PMU.enableDC5();\n  PMU.enableALDO1();\n  PMU.enableALDO3();\n  PMU.enableBLDO2();\n\n  //! ALDO2 MICRO TF Card VDD\n  PMU.enableALDO2();\n\n  //! ALDO4 GNSS VDD\n  PMU.enableALDO4();\n\n  //! BLDO1 MIC VDD\n  PMU.enableBLDO1();\n\n  //! DC3 Radio & Pixels VDD\n  // Rev2.1: DC3 unused; keep disabled.\n  // power off when not in use\n  PMU.disableDC2();\n  PMU.disableDC4();\n  PMU.disableCPUSLDO();\n  PMU.disableDLDO1();\n  PMU.disableDLDO2();\n'''
    rails_new = '''  //! Rev2.1 idle power-domain state follows LilyGO TWRClass::beginPower/begin.\n  PMU.disableDC3();   // Rev2.1 unused; radio is battery-fed and controlled by PD GPIO40\n  PMU.disableDC5();   // user rail, unused by base APRS firmware\n  PMU.disableALDO1(); // user rail, unused by base APRS firmware\n  PMU.disableALDO3(); // LOW selects Radio -> onboard audio amplifier on Rev2.1\n  PMU.disableBLDO2(); // user rail, unused by base APRS firmware\n  PMU.disableDLDO1(); // downloader routing switch disabled in normal operation\n\n  //! ALDO2 MICRO TF Card VDD\n  PMU.enableALDO2();\n\n  //! ALDO4 GNSS VDD\n  PMU.enableALDO4();\n\n  //! BLDO1 MIC VDD\n  PMU.enableBLDO1();\n\n  // power off unavailable/unused channels\n  PMU.disableDC2();\n  PMU.disableDC4();\n  PMU.disableCPUSLDO();\n  PMU.disableDLDO2();\n'''
    text = replace_once(text, rails_old, rails_new,
                        "match LilyGO Rev2.1 PMU idle power domains")

    # Normalize the charge-current diagnostic after older migration scripts may
    # have nested the bounds guard multiple times.
    charge_pattern = re.compile(
        r'''  uint8_t val = PMU\.getChargerConstantCurr\(\);\n  log_d\("Val = %d", val\);\n.*?\n  // Get charging target voltage''',
        re.DOTALL,
    )
    charge_repl = '''  uint8_t val = PMU.getChargerConstantCurr();\n  log_d("Val = %d", val);\n  if (val < (sizeof(currTable) / sizeof(currTable[0])))\n    log_d("Setting Charge Target Current : %d", currTable[val]);\n  else\n    log_w("Charge current enum %u is outside legacy display table", (unsigned)val);\n\n  // Get charging target voltage'''
    new_text, n = charge_pattern.subn(charge_repl, text, count=1)
    if n != 1:
        raise RuntimeError("unable to normalize charge-current diagnostic block")
    text = new_text
    print("PATCH normalize charge-current diagnostic block")

    # Guard the charge-voltage display table as well.
    voltage_old = '''  val = PMU.getChargeTargetVoltage();\n  log_d("Setting Charge Target Voltage : %d", tableVoltage[val]);\n'''
    voltage_new = '''  val = PMU.getChargeTargetVoltage();\n  if (val < (sizeof(tableVoltage) / sizeof(tableVoltage[0])))\n    log_d("Setting Charge Target Voltage : %d", tableVoltage[val]);\n  else\n    log_w("Charge voltage enum %u is outside legacy display table", (unsigned)val);\n'''
    text = replace_once(text, voltage_old, voltage_new,
                        "bound-check charge-voltage display table")

    MAIN.write_text(text, encoding="utf-8")


def patch_platformio() -> None:
    text = PIO.read_text(encoding="utf-8")

    if "boards_dir = boards" not in text:
        text = text.replace("\n\n[env:esp32s3-twrplus]", "\n\n[platformio]\nboards_dir = boards\n\n[env:esp32s3-twrplus]", 1)
        print("PATCH use repository-local board definitions")
    else:
        print("SKIP  repository-local board definitions already enabled")

    text = text.replace("board = esp32s3box\n", "board = LilyGo-T-TWR-Plus\n")
    text = text.replace("board_build.arduino.memory_type = dio_opi\n", "board_build.arduino.memory_type = qio_opi\n")
    # Keep the project's OTA/LittleFS partition layout rather than the factory
    # demo partition table, while adopting LilyGO's actual flash/PSRAM bus mode.
    if "board_build.flash_mode = qio\n" not in text:
        anchor = "board_build.f_flash = 80000000L\n"
        if anchor not in text:
            raise RuntimeError("platformio flash-frequency anchor missing")
        text = text.replace(anchor, anchor + "board_build.flash_mode = qio\n", 1)
    print("PATCH select official LilyGO T-TWR Plus QIO/OPI hardware profile")

    PIO.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_main()
    patch_platformio()
    print("Rev2.1 full hardware compatibility pass applied.")
