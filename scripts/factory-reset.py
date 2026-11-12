#!/usr/bin/env python3
"""Remove Church Cap local state after explicit command-line confirmation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.factory_reset import factory_reset_local_state  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        required=True,
        help="Must be exactly RESET. This guard prevents accidental use.",
    )
    args = parser.parse_args()
    if args.confirm != "RESET":
        parser.error("factory reset confirmation must be exactly RESET")

    result = factory_reset_local_state()
    print(f"Church Cap factory reset completed for {result.support_dir}")
    print(f"Removed {len(result.removed)} local data location(s).")
    print("Restart Church Cap. The complete first-time setup will open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
