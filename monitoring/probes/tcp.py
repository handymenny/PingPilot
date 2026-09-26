from __future__ import annotations

import re
import logging
import shutil
from dataclasses import dataclass

from ..models import ProbeConfig, Sample, Scalar, TargetConfig, base_tags, sample
from .probe_common import latency_fields, resolved_ip
from ..process import run as run_process


LOG = logging.getLogger(__name__)


def tcpping_latencies(output: str) -> list[float]:
    return [
        float(value) * 1000 if unit.lower().startswith("s") else float(value)
        for value, unit in re.findall(
            r"(?:time\s*[=<:]\s*)?(\d+(?:\.\d+)?)\s*(ms|msec|s|sec)\b",
            output,
            re.IGNORECASE,
        )
    ]


@dataclass(frozen=True)
class TcpProbe:
    port: int

    def run(self, target_cfg: TargetConfig) -> list[Sample]:
        port = self.port
        timeout = target_cfg.timeout_seconds
        host = target_cfg.target
        ip = resolved_ip(host, target_cfg.global_dns_cfg, target_cfg.ip_version)
        tcpping = shutil.which("tcpping")
        if not tcpping:
            raise RuntimeError("tcpping is required for TCP probes")

        if ip:
            target = ip
        else:
            LOG.warning(
                "TCP probe for %s:%s: could not resolve hostname, passing hostname directly",
                host,
                port,
            )
            target = host

        command = [
            tcpping,
            "-w",
            str(timeout),
            "-r",
            str(target_cfg.minimum_delay_per_ping_seconds),
            "-x",
            str(target_cfg.count),
            target,
            str(port),
        ]
        if target_cfg.ip_version == 6:
            command.insert(1, "-6")
        fields: dict[str, Scalar] = {}
        try:
            result = run_process(
                command,
                capture_output=True,
                text=True,
                timeout=timeout * target_cfg.count + 1,
                check=False,
            )  # nosec B603
            output = result.stdout + result.stderr
            parsed_latencies = tcpping_latencies(output)
            latencies: list[float | None] = parsed_latencies + [None] * max(
                0, target_cfg.count - len(parsed_latencies)
            )
            losses = [False] * len(parsed_latencies) + [True] * max(
                0, target_cfg.count - len(parsed_latencies)
            )
            if result.returncode != 0 or not parsed_latencies:
                LOG.warning(
                    "TCP probe failed for %s:%s: %s",
                    host,
                    port,
                    output.strip() or f"tcpping exited with code {result.returncode}",
                )
        except Exception as exc:
            latencies = [None] * target_cfg.count
            losses = [True] * target_cfg.count
            LOG.warning("TCP probe failed for %s:%s: %s", host, port, exc)
        fields.update(latency_fields(latencies, losses))
        return [sample(base_tags(target_cfg, "tcp_ping", ip), fields)]


def probe_tcp(target_cfg: TargetConfig, probe: ProbeConfig) -> list[Sample]:
    if probe.port is None:
        raise ValueError("TCP ping probes require port")
    return TcpProbe(probe.port).run(target_cfg)
