#!/usr/bin/env python3
"""Rev2.1 RF validation patch entry point.

Runs the proven hardware/RF transition fixes, FX.25 interoperability defaults,
the guarded FX.25 RX detector discovered during on-air AnyTone testing, the
persistent 100-packet RF decode history, and the Last Heard dashboard refresh
race fix.
"""

from rev21_hw_validation_fixes_base import main as base_main
from rev21_fx25_compat import main as fx25_main
from rev21_fx25_rx_guard import main as fx25_rx_guard_main
from rev21_persistent_packet_history import main as packet_history_main
from rev21_lastheard_refresh import main as lastheard_refresh_main


def main() -> None:
    base_main()
    fx25_main()
    fx25_rx_guard_main()
    packet_history_main()
    lastheard_refresh_main()


if __name__ == "__main__":
    main()
