from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass

from ..models import (
    ProbeConfig,
    Sample,
    Scalar,
    TargetConfig,
    base_tags,
    sample,
)
from .probe_common import latency_fields, resolved_ip
from ..process import run as run_process


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class IcmpProbe:
    def run(self, target_cfg: TargetConfig) -> list[Sample]:
        timeout = target_cfg.timeout_seconds
        ip = resolved_ip(
            target_cfg.target, target_cfg.global_dns_cfg, target_cfg.ip_version
        )
        latencies: list[float | None] = []
        losses = []
        fields: dict[str, Scalar] = {}

        if ip:
            target = ip
        else:
            LOG.warning(
                "ICMP probe for %s: could not resolve hostname, passing hostname directly",
                target_cfg.target,
            )
            target = target_cfg.target

        try:
            icmp_args = (
                target,
                timeout,
                target_cfg.count,
                target_cfg.minimum_delay_per_ping_seconds,
            )

            if target_cfg.ip_version == 6:
                icmp_args += (6,)
            else:
                icmp_args += (4,)

            latencies, error = _run_icmp(*icmp_args)
            losses = [latency is None for latency in latencies]
            if any(losses) and error:
                LOG.warning(
                    "ICMP probe lost packets for %s: %s", target_cfg.target, error
                )
        except Exception as exc:
            latencies = [None] * target_cfg.count
            losses = [True] * target_cfg.count
            LOG.warning("ICMP probe failed for %s: %s", target_cfg.target, exc)
        fields.update(latency_fields(latencies, losses))
        return [sample(base_tags(target_cfg, "icmp_ping", ip), fields)]


def _run_icmp(
    host: str,
    timeout: int,
    count: int = 1,
    interval: float = 0,
    ip_version: int = 4,
) -> tuple[list[float | None], str]:
    fping = shutil.which("fping")
    if not fping:
        raise FileNotFoundError("fping is not installed")

    interval_ms = round(interval * 1000)
    command = [
        fping,
        "-C",
        str(count),
        "-t",
        str(timeout * 1000),
        "-p",
        str(interval_ms),
    ]
    if ip_version == 6:
        command.insert(1, "-6")
    command.append(host)

    latencies: list[float | None] = []
    output = ""

    result = run_process(
        command,
        capture_output=True,
        text=True,
        timeout=timeout * count + interval * max(0, count - 1) + 1,
        check=False,
    )  # nosec B603

    output = result.stdout + result.stderr

    for line in output.splitlines():
        # Filtro: righe tipo "IP : [seq], ..." o "IP : t1 t2 ..."
        if " : " not in line:
            continue

        # Latency è l'ultimo token della riga, es. "7.28 ms" o "timed out"
        # I token sono separati da ", "
        # Ma l'ultimo ha delle parantesi, quindi usiamo elemento -2.
        # Es. 127.0.0.1: [0], 64 bytes, 7.28 ms (7.28 avg, 0% loss)

        parts = line.split(", ")
        if len(parts) < 2:
            continue

        latency = parts[-2].split()[0]

        try:
            latencies.append(float(latency))
        except ValueError:
            continue

        # abbiamo aggiunto n latencies, quindi se abbiamo raggiunto il count, possiamo uscire
        if len(latencies) == count:
            break

    # Se non abbiamo abbastanza latencies, aggiungi None
    while len(latencies) < count:
        latencies.append(None)

    return latencies, output.strip()


def probe_icmp(target: TargetConfig, probe: ProbeConfig) -> list[Sample]:
    return IcmpProbe().run(target)
