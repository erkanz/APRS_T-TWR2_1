# T-TWR Plus Rev2.1 hardware port

This branch is the hardware-correctness port for LILYGO T-TWR Plus Rev2.1.

The build applies and verifies these invariants before compiling:

- SA868 UART: ESP32 TX GPIO39, RX GPIO48
- SA868 PTT: GPIO41
- SA868 power-down: GPIO40
- SA868 SQL: GPIO2, active LOW
- APRS RX audio: GPIO1
- APRS TX audio: GPIO18
- Audio mux: GPIO17
- GPIO38 is treated as Rev2.0-only and is never driven
- AXP2101 DC3 is not used to switch the Rev2.1 radio
- BLDO1 is configured to 2.0 V, matching LilyGO's Rev2.1 beginPower() implementation
- GPIO2/GPIO4 are not used as fake AFSK RX/TX LED pins
- Global TWDT is framework-managed; application-level TWDT reconfiguration/reset calls are removed
- Adafruit NeoPixel is pinned to 1.12.3 to avoid the ESP32-S3 Arduino 3.2.0 RMT/light-sleep initialization regression
- Charge-current diagnostic table access is bounds-checked
- TX-to-RX recovery blocks ADC DMA during TX, bounds/flushes the RX FIFO, and completes PTT/audio routing changes in task context
- Manual BOOT beacons use classic uncompressed APRS for broader analog-radio interoperability; periodic tracker beacons retain the configured compression preference
- CRC-valid AnyTone position packets with the observed minute-hundredths overflow form (for example `10849.:0E`) are normalized locally for APRS parsing while the raw packet remains visible unchanged
- Per-second `TRACKER tx_counter=` diagnostics are removed from the final build

GitHub Actions builds `esp32s3-twrplus`, verifies the source invariants, packages the individual flash images, creates a merged firmware image, and publishes SHA-256 hashes as a workflow artifact.

## Release authority

The normal `T-TWR Rev2.1 Firmware` workflow is the only automatic workflow allowed to update the Nightly GitHub Release. The RF-validation workflow is manual/artifact-only so it cannot race the normal build or advance the release source checkpoint while publishing is in progress.

## Current validation state

- Rev2.1 PTT41/MUX17 TX START/STOP sequencing: physically observed PASS
- Post-TX RX recovery: physically observed PASS
- AX.25 receive and valid APRS parsing: physically observed PASS
- AnyTone interoperability compatibility: compile/package verified; physical retest required
- Firmware remains Nightly until over-air TX decode is physically confirmed
