"""Run the agent desk (paper trading only).

    python run_desk.py            # run scanner + monitor loops until Ctrl+C
    python run_desk.py --once     # one scan + one monitor pass, then exit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from desk.config import load_config
from desk.pipeline import Desk


def main() -> None:
    parser = argparse.ArgumentParser(description="Grok multi-agent trading desk (paper trading only)")
    parser.add_argument("--once", action="store_true", help="run one scan and one monitor pass")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    # httpx logs full request URLs at INFO; the Telegram URL contains the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    config = load_config()
    print(f"Grok trading desk: PAPER TRADING ONLY · model {config.xai_model} · db {config.db_path}")
    desk = Desk(config)
    if args.once:
        print(json.dumps({"scan": desk.scan_once(), "closed": desk.monitor_once()}, indent=2))
    else:
        desk.run_forever()


if __name__ == "__main__":
    main()
