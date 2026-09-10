import logging
import random
import time

from .influx import InfluxV1
from .models import MonitorConfig
from .probes import run_probe

LOG = logging.getLogger("network-monitor")


def target_order(config: MonitorConfig) -> tuple[int, ...]:
    indices = list(range(len(config.targets)))
    if config.scheduler.random_order:
        random.shuffle(indices)  # nosec B311
    return tuple(indices)


def monitor(config: MonitorConfig, once: bool = False) -> None:
    influx = InfluxV1(config.influx)
    interval = config.scheduler.interval_seconds
    min_delay = config.scheduler.minimum_delay_between_targets_seconds

    indices = target_order(config)

    while True:
        cycle_start = time.monotonic()
        last_finish: float | None = None

        for i in indices:
            target = config.targets[i]

            # Rispetta minimum_delay_between_targets
            if last_finish is not None:
                earliest = last_finish + min_delay
                wait = max(0, earliest - time.monotonic())
                if not once and wait > 0:
                    time.sleep(wait)

            # Esegui probe
            samples = []
            if target.probe is not None:
                try:
                    samples.extend(run_probe(target, target.probe))
                except Exception as exc:
                    LOG.error(
                        "Probe %s/%s failed: %s", target.name, target.probe.type, exc
                    )

            # Scrivi su Influx
            try:
                influx.write(samples)
            except Exception as exc:
                LOG.error("InfluxDB write failed for %s: %s", target.name, exc)

            last_finish = time.monotonic()

        if once:
            return

        # Attendi il prossimo ciclo
        elapsed = time.monotonic() - cycle_start
        remaining = interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        else:
            LOG.warning(
                "Cycle took %.1fs, exceeding interval by %.1fs",
                elapsed,
                -remaining,
            )
