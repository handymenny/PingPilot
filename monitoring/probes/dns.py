from __future__ import annotations

import re
import logging
import shutil
import time
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
class DnsProbe:
    query: str
    record_type: str = "A"

    def run(self, target_cfg: TargetConfig) -> list[Sample]:
        query = self.query
        record_type = self.record_type
        if not query:
            raise ValueError("DNS probes require query")

        nameserver = resolved_ip(
            target_cfg.target, target_cfg.global_dns_cfg, target_cfg.ip_version
        )
        if not nameserver:
            nameserver = target_cfg.target
            LOG.warning(
                "DNS probe for %s: could not resolve nameserver, passing nameserver directly",
                target_cfg.name,
            )

        kdig = shutil.which("kdig")
        if not kdig:
            raise RuntimeError("kdig is required for DNS probes")

        timeout_seconds = target_cfg.timeout_seconds
        latencies: list[float | None] = []
        losses = []
        fields: dict[str, Scalar] = {}
        ip = ""
        for attempt in range(target_cfg.count):
            try:
                result = run_process(
                    [
                        kdig,
                        f"+time={timeout_seconds}",
                        "+retry=0",
                        f"@{nameserver}",
                        query,
                        record_type,
                        "+noall",
                        "+answer",
                        "+stats",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds + 1,
                    check=False,
                )  # nosec B603
                answers = [
                    line
                    for line in result.stdout.splitlines()
                    if line and not line.startswith(";")
                ]
                if result.returncode or not answers:
                    raise RuntimeError(
                        result.stderr.strip() or "kdig returned no answer"
                    )
                ip = answers[0].split()[-1] if record_type in {"A", "AAAA"} else ""
                loss = False
            except Exception as exc:
                LOG.warning("DNS probe failed for %s: %s", query, exc)
                loss = True
                ip = ""
            query_latency = None
            if not loss:
                match = re.search(
                    r"\bin\s+(\d+(?:\.\d+)?)\s*m(?:s|sec)\b",
                    result.stdout,
                    re.IGNORECASE,
                )
                query_latency = float(match.group(1)) if match else None
            latencies.append(query_latency)
            losses.append(loss)
            if (
                attempt < target_cfg.count - 1
                and target_cfg.minimum_delay_per_ping_seconds > 0
            ):
                time.sleep(target_cfg.minimum_delay_per_ping_seconds)
        fields.update(latency_fields(latencies, losses))
        return [sample(base_tags(target_cfg, "dns", ip), fields)]


def probe_dns(target_cfg: TargetConfig, probe: ProbeConfig) -> list[Sample]:
    if probe.query is None:
        raise ValueError("DNS probes require query")
    return DnsProbe(probe.query, probe.record_type).run(target_cfg)
