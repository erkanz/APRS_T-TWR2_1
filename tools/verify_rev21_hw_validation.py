#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src/main.cpp").read_text(encoding="utf-8")
CONFIG = (ROOT / "src/config.cpp").read_text(encoding="utf-8")
WEB = (ROOT / "src/webservice.cpp").read_text(encoding="utf-8")
AFSK = (ROOT / "lib/LibAPRS_ESP32S3/AFSK.cpp").read_text(encoding="utf-8")
AFSK_H = (ROOT / "lib/LibAPRS_ESP32S3/AFSK.h").read_text(encoding="utf-8")
MODEM = (ROOT / "lib/LibAPRS_ESP32S3/modem.cpp").read_text(encoding="utf-8")

checks = [
    ("tracker counter serial spam removed", 'TRACKER tx_counter=%d' not in MAIN),
    ("PTT deferred flag volatile", "volatile bool pttOFF = false;" in AFSK),
    ("TX ISR flag volatile", "volatile bool hw_afsk_dac_isr = false;" in AFSK),
    ("ADC transition flag volatile", "volatile int8_t adcEn = 0;" in AFSK),
    ("DAC transition flag volatile", "volatile int8_t dacEn = 0;" in AFSK),
    ("ADC DMA blocked during TX", "if (hw_afsk_dac_isr)\n    return true;" in AFSK),
    ("RX FIFO bounded", "if (fifo.count < BUFFER_SIZE)" in AFSK),
    ("RX FIFO flush helper", "void AFSK_FlushRxFifo(void)" in AFSK),
    ("GPIO42 NeoPixel disabled", '_led_strip_pin = -1;' in AFSK and "strip = new Adafruit_NeoPixel" not in AFSK),
    ("NeoPixel validation log", "NeoPixel GPIO%d disabled during RF validation" in AFSK),
    ("TX START diagnostic", 'AFSK_LogRadioState("START");' in MODEM),
    ("TX STOP diagnostic", 'AFSK_LogRadioState("STOP");' in MAIN),
    ("TX stop deferred out of ISR", "pttOFF = true;" in MODEM and "dacEn = -1;" in MODEM and "adcEn = 1;" in MODEM),
    ("task context completes PTT off", "if (pttOFF)" in MAIN and "AFSK_FlushRxFifo();" in MAIN),
    ("DAC stopped before ADC restart", MAIN.find("if (dacEn == 1)") < MAIN.find("if (adcEn == 1)")),
    ("Rev2.1 active-low TX drive", "digitalWrite(_ptt_pin, LOW);" in AFSK),
    ("Rev2.1 RX idle high drive", "digitalWrite(_ptt_pin, HIGH);" in AFSK),
    ("TX audio route high", "digitalWrite(17, HIGH);" in AFSK),
    ("RX audio route low", "digitalWrite(17, LOW);" in AFSK),
    ("header exposes volatile TX ISR flag", "extern volatile bool hw_afsk_dac_isr;" in AFSK_H),
    ("header exposes transition flags", "extern volatile int8_t adcEn;" in AFSK_H and "extern volatile int8_t dacEn;" in AFSK_H),
    ("header exposes FIFO helper", "void AFSK_FlushRxFifo(void);" in AFSK_H),
    ("modem externs use volatile", "extern volatile bool hw_afsk_dac_isr;" in MODEM and "extern volatile int8_t adcEn;" in MODEM),
    ("main PTT externs use volatile", "extern volatile bool pttON;" in MAIN and "extern volatile bool pttOFF;" in MAIN),
    ("main ADC/DAC externs use volatile", "extern volatile int8_t adcEn;" in MAIN and "extern volatile int8_t dacEn;" in MAIN),
    ("config ADC/DAC externs use volatile", "extern volatile int8_t adcEn;" in CONFIG and "extern volatile int8_t dacEn;" in CONFIG),
    ("web ADC/DAC externs use volatile", "extern volatile int8_t adcEn;" in WEB and "extern volatile int8_t dacEn;" in WEB),
    ("Rev2.1 PTT profile retained", "config.rf_ptt_gpio = 41;" in MAIN and "config.rf_ptt_active = LOW;" in MAIN),
    ("GPIO38 RF power remains disabled", "config.rf_pwr_gpio = -1;" in MAIN),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL"), name)

if failed:
    raise SystemExit(f"{len(failed)} Rev2.1 hardware-validation checks failed: {', '.join(failed)}")

print(f"{len(checks)}/{len(checks)} Rev2.1 hardware-validation checks PASS")
