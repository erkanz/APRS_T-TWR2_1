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
- User TWDT does not subscribe IDLE0/IDLE1

GitHub Actions builds `esp32s3-twrplus`, verifies the source invariants, packages the individual flash images, creates a merged firmware image, and publishes SHA-256 hashes as a workflow artifact.
