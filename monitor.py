#!/usr/bin/env python3
"""Configurable network latency monitor with InfluxDB v1 line protocol export."""

import argparse
import logging
from pathlib import Path

from monitoring.config import load_config
from monitoring.process import install_shutdown_handler
from monitoring.runner import monitor
from monitoring.validation import validate_full_cycle, validate_schedule


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--once", action="store_true", help="run all configured targets once and exit"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = load_config(args.config)
    install_shutdown_handler()
    logger = logging.getLogger("network-monitor")
    for message in validate_schedule(config):
        if "exceeding" in message:
            logger.warning("Schedule check: %s", message)
        else:
            logger.info("Schedule check: %s", message)

    for msg in validate_full_cycle(config):
        if "exceeding" in msg:
            logger.warning("Full cycle check: %s", msg)
        else:
            logger.info("Full cycle check: %s", msg)

    monitor(config, once=args.once)


if __name__ == "__main__":
    main()
