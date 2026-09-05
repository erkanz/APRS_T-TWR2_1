#!/usr/bin/env python3
"""Rev2.1 RF validation patch entry point.

Runs the proven hardware/RF transition fixes first, then applies the FX.25
interoperability normalization discovered during on-air AnyTone testing.
"""

from rev21_hw_validation_fixes_base import main as base_main
from rev21_fx25_compat import main as fx25_main


def main() -> None:
    base_main()
    fx25_main()


if __name__ == "__main__":
    main()
