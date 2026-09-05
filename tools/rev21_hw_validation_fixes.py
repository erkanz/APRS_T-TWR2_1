#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AFSK = ROOT / "lib/LibAPRS_ESP32S3/AFSK.cpp"
AFSK_H = ROOT / "lib/LibAPRS_ESP32S3/AFSK.h"
MODEM = ROOT / "lib/LibAPRS_ESP32S3/modem.cpp"
MAIN = ROOT / "src/main.cpp"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label}: expected exactly one source match, found {count}")
    return text.replace(old, new, 1)


def patch_afsk() -> None:
    text = AFSK.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "bool pttON = false;\nbool pttOFF = false;",
        "volatile bool pttON = false;\nvolatile bool pttOFF = false;",
        "volatile PTT transition flags",
    )
    text = replace_once(
        text,
        "bool hw_afsk_dac_isr = false;",
        "volatile bool hw_afsk_dac_isr = false;",
        "volatile TX ISR flag",
    )
    text = replace_once(
        text,
        "int8_t adcEn = 0;\nint8_t dacEn = 0;",
        "volatile int8_t adcEn = 0;\nvolatile int8_t dacEn = 0;",
        "volatile ADC/DAC transition flags",
    )

    old_led = '''void LED_init(int8_t led_tx_pin, int8_t led_rx_pin, int8_t led_strip_pin)
{
  _led_tx_pin = led_tx_pin;
  _led_rx_pin = led_rx_pin;
  _led_strip_pin = led_strip_pin;
  if (led_strip_pin > -1)
  {
    rgbTimeout = millis() + 50;
    strip = new Adafruit_NeoPixel(1, _led_strip_pin, NEO_GRB + NEO_KHZ800);
    strip->begin();
    strip->show();
  }
  if (led_tx_pin > -1)
'''
    new_led = '''void LED_init(int8_t led_tx_pin, int8_t led_rx_pin, int8_t led_strip_pin)
{
  _led_tx_pin = led_tx_pin;
  _led_rx_pin = led_rx_pin;

  // Rev2.1 hardware-validation build: do not claim GPIO42 through the Arduino
  // NeoPixel/RMT backend. Arduino-ESP32 can reject this RMT channel when light
  // sleep power-down is enabled. APRS RF operation does not depend on the RGB LED.
  _led_strip_pin = -1;
  if (led_strip_pin > -1)
    log_w("[REV2.1] NeoPixel GPIO%d disabled during RF validation", led_strip_pin);

  if (led_tx_pin > -1)
'''
    text = replace_once(text, old_led, new_led, "disable Rev2.1 NeoPixel/RMT init")

    afsk_init_marker = "  _led_strip_pin = led_strip_pin;\n\n  _ptt_active = ptt_act;"
    afsk_init_replacement = (
        "  _led_strip_pin = -1; // Rev2.1 RF validation: NeoPixel/RMT disabled\n\n"
        "  _ptt_active = ptt_act;"
    )
    text = replace_once(
        text,
        afsk_init_marker,
        afsk_init_replacement,
        "disable strip pin in AFSK_init",
    )

    old_setptt_tail = '''    // delay(100);
    pttOFF = true;
  }
}
'''
    new_setptt_tail = '''    // delay(100);
    // pttOFF is the ISR-to-task deferred RX transition flag. setPtt(false)
    // is executed in task context and must not re-arm that flag.
  }
}
'''
    text = replace_once(
        text,
        old_setptt_tail,
        new_setptt_tail,
        "do not re-arm deferred PTT flag",
    )

    timer_mux = "portMUX_TYPE timerMux = portMUX_INITIALIZER_UNLOCKED;\n\n"
    helpers = '''portMUX_TYPE timerMux = portMUX_INITIALIZER_UNLOCKED;

void AFSK_FlushRxFifo(void)
{
  portENTER_CRITICAL(&timerMux);
  RingBuffer_Init(&fifo);
  portEXIT_CRITICAL(&timerMux);
}

void AFSK_LogRadioState(const char *phase)
{
  const int pttLevel = (_ptt_pin > -1) ? digitalRead(_ptt_pin) : -1;
  const int muxLevel = digitalRead(17);
  log_i("[RF TX] %s PTT%d=%d active=%s MUX17=%d DAC%d=%s",
        phase,
        _ptt_pin,
        pttLevel,
        _ptt_active ? "HIGH" : "LOW",
        muxLevel,
        _dac_pin,
        (phase && phase[0] == 'S' && phase[1] == 'T' && phase[2] == 'A') ? "ACTIVE" : "IDLE");
}

'''
    if "void AFSK_FlushRxFifo(void)" not in text:
        text = replace_once(text, timer_mux, helpers, "RX FIFO/diagnostic helpers")

    callback_open = '''bool IRAM_ATTR s_conv_done_cb(adc_continuous_handle_t stAdcHandle, const adc_continuous_evt_data_t *edata, void *user_data)
{

  portENTER_CRITICAL_ISR(&timerMux);
'''
    callback_new = '''bool IRAM_ATTR s_conv_done_cb(adc_continuous_handle_t stAdcHandle, const adc_continuous_evt_data_t *edata, void *user_data)
{
  // TX and RX share the audio path. Never enqueue ADC DMA samples while the
  // DAC/AFSK transmitter owns the path; stale TX-era samples poison RX recovery.
  if (hw_afsk_dac_isr)
    return true;

  portENTER_CRITICAL_ISR(&timerMux);
'''
    text = replace_once(
        text,
        callback_open,
        callback_new,
        "drop ADC DMA samples while TX is active",
    )

    old_fifo_push = '''fifo.buffer[fifo.head] = adcPush;
fifo.head = (fifo.head + 1) % BUFFER_SIZE; // Wrap around using modulo
fifo.count++;
'''
    new_fifo_push = '''    if (fifo.count < BUFFER_SIZE)
    {
      fifo.buffer[fifo.head] = adcPush;
      fifo.head = (fifo.head + 1) % BUFFER_SIZE; // Wrap around using modulo
      fifo.count++;
    }
'''
    text = replace_once(
        text,
        old_fifo_push,
        new_fifo_push,
        "bound RX FIFO count",
    )

    AFSK.write_text(text, encoding="utf-8")


def patch_afsk_header() -> None:
    text = AFSK_H.read_text(encoding="utf-8")
    text = text.replace("extern bool hw_afsk_dac_isr;", "extern volatile bool hw_afsk_dac_isr;")

    decl_anchor = '''void LED_init(int8_t led_tx_pin, int8_t led_rx_pin, int8_t led_strip_pin);

#endif
'''
    decl_new = '''void LED_init(int8_t led_tx_pin, int8_t led_rx_pin, int8_t led_strip_pin);
void AFSK_FlushRxFifo(void);
void AFSK_LogRadioState(const char *phase);

extern volatile bool pttON;
extern volatile bool pttOFF;
extern volatile bool hw_afsk_dac_isr;
extern volatile int8_t adcEn;
extern volatile int8_t dacEn;

#endif
'''
    text = replace_once(
        text,
        decl_anchor,
        decl_new,
        "AFSK transition declarations",
    )
    AFSK_H.write_text(text, encoding="utf-8")


def patch_modem() -> None:
    text = MODEM.read_text(encoding="utf-8")
    old_extern = '''extern int8_t dacEn;
extern bool hw_afsk_dac_isr;
'''
    new_extern = '''extern volatile int8_t adcEn;
extern volatile int8_t dacEn;
extern volatile bool hw_afsk_dac_isr;
extern volatile bool pttOFF;
'''
    text = replace_once(text, old_extern, new_extern, "volatile modem transition externs")
    text = text.replace("\nextern bool pttOFF;\nvoid ModemTransmitStop", "\nvoid ModemTransmitStop")

    old_start = '''void ModemTransmitStart(void)
{
\ttxTestState = TEST_DISABLED;
\tsetPtt(true); // PTT on
\tAFSK_TimerEnable(false);
\tDAC_TimerEnable(true);
\tlog_d("ModemTransmitStart");
}
'''
    new_start = '''void ModemTransmitStart(void)
{
\ttxTestState = TEST_DISABLED;
\tsetPtt(true); // PTT on
\tAFSK_LogRadioState("START");
\tAFSK_TimerEnable(false);
\tDAC_TimerEnable(true);
\tlog_d("ModemTransmitStart");
}
'''
    text = replace_once(text, old_start, new_start, "TX START hardware diagnostic")

    old_stop = '''void ModemTransmitStop(void)
{
\tsetPtt(false);
\thw_afsk_dac_isr=false;
\tDAC_TimerEnable(false);
\tAFSK_TimerEnable(true);
\tlog_d("ModemTransmitStop");
}
'''
    new_stop = '''void ModemTransmitStop(void)
{
\t// Called from the DAC baud timer ISR. Do not perform GPIO/RMT/ADC driver
\t// operations here. Quiesce the sample ISR immediately and defer the physical
\t// RX transition to taskAPRS(), which runs every ~10 ms.
\thw_afsk_dac_isr = false;
\tdacEn = -1;
\tadcEn = 1;
\tpttOFF = true;
}
'''
    text = replace_once(text, old_stop, new_stop, "defer TX STOP recovery to task context")

    MODEM.write_text(text, encoding="utf-8")


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "extern bool pttON;\nextern bool pttOFF;",
        "extern volatile bool pttON;\nextern volatile bool pttOFF;",
        "volatile main PTT transition externs",
    )
    old_transition = '''    if (adcEn == 1)
    {
      AFSK_TimerEnable(true);
      adcEn = 0;
    }
    else if (adcEn == -1)
    {
      AFSK_TimerEnable(false);
      adcEn = 0;
    }

    if (dacEn == 1)
    {
      DAC_TimerEnable(true);
      dacEn = 0;
    }
    else if (dacEn == -1)
    {
      DAC_TimerEnable(false);
      dacEn = 0;
    }
'''
    new_transition = '''    // TX completion originates in the DAC timer ISR. Complete the hardware
    // transition back to RX here in FreeRTOS task context.
    if (pttOFF)
    {
      pttOFF = false;
      setPtt(false);
      AFSK_FlushRxFifo();
      AFSK_LogRadioState("STOP");
    }

    // Stop the TX timer before restarting ADC DMA.
    if (dacEn == 1)
    {
      DAC_TimerEnable(true);
      dacEn = 0;
    }
    else if (dacEn == -1)
    {
      DAC_TimerEnable(false);
      dacEn = 0;
    }

    if (adcEn == 1)
    {
      AFSK_TimerEnable(true);
      adcEn = 0;
    }
    else if (adcEn == -1)
    {
      AFSK_TimerEnable(false);
      adcEn = 0;
    }
'''
    text = replace_once(
        text,
        old_transition,
        new_transition,
        "task-context TX-to-RX recovery",
    )
    MAIN.write_text(text, encoding="utf-8")


def main() -> None:
    patch_afsk()
    patch_afsk_header()
    patch_modem()
    patch_main()
    print("Applied Rev2.1 physical RF validation fixes.")


if __name__ == "__main__":
    main()
