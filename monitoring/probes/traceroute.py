from __future__ import annotations

import re
import logging
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass

from ..models import ProbeConfig, Sample, Scalar, TargetConfig, base_tags, sample


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class TracerouteProbe:
    tcp: bool = False
    max_hops: int = 30
    port: int | None = None

    def run(self, target: TargetConfig) -> list[Sample]:
        return _run_traceroute(target, self)


def _run_traceroute(target: TargetConfig, probe: TracerouteProbe) -> list[Sample]:
    probe_type = "traceroute_tcp" if probe.tcp else "traceroute_icmp"

    def failed_sample() -> Sample:
        return sample(
            base_tags(target, probe_type),
            {
                "host": target.target,
                "hop": 0,
                "ip": "",
                "asn": "",
                "loss_percent": 100.0,
            },
        )

    mtr = shutil.which("mtr")
    if not mtr:
        LOG.error("traceroute probe failed for %s: mtr is required", target.target)
        return [failed_sample()]
    destination = target.target
    max_hops = probe.max_hops
    timeout = target.timeout_seconds
    port = probe.port or 443
    command = [
        mtr,
        "--report",
        "--report-cycles",
        str(target.count),
        "--numeric",
        "--wide",
        "--aslookup",
        "--max-hops",
        str(max_hops),
        "--timeout",
        str(timeout),
    ]
    if target.minimum_delay_per_ping_seconds > 0:
        command.extend(["--interval", str(target.minimum_delay_per_ping_seconds)])
    if probe.tcp:
        command.extend(["--tcp", "--port", str(port)])
    if target.ip_version == 6:
        command.append("--inet6")
    command.append(destination)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout * target.count * max_hops + 1,
            check=False,
        )  # nosec B603
    except Exception as exc:
        LOG.warning("traceroute probe failed for %s: %s", destination, exc)
        return [failed_sample()]
    if result.returncode != 0:
        LOG.warning(
            "traceroute probe failed for %s: %s",
            destination,
            result.stderr.strip() or f"mtr exited with code {result.returncode}",
        )
        return [failed_sample()]
    results = []
    for line in result.stdout.splitlines():
        match = re.match(
            r"^\s*(\d+)\.\|--\s+(?:(AS\d+)\s+)?(\S+)\s+(\S+)%\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)",
            line,
            re.IGNORECASE,
        )
        if not match:
            continue
        hop, asn, ip, loss_text, last_text, mean_text, best_text, worst_text = (
            match.groups()
        )
        loss_percent = float(loss_text)
        mean = None if mean_text == "-" else float(mean_text)
        minimum = None if best_text == "-" else float(best_text)
        maximum = None if worst_text == "-" else float(worst_text)
        probe_type = "traceroute_tcp" if probe.tcp else "traceroute_icmp"
        fields: dict[str, Scalar] = {
            "host": destination,
            "hop": int(hop),
            "ip": ip,
            "asn": asn or "",
            "loss_percent": loss_percent,
        }
        if minimum is not None:
            fields["latency_min_ms"] = minimum
        if maximum is not None:
            fields["latency_max_ms"] = maximum
        if mean is not None:
            fields["latency_mean_ms"] = mean
            fields["latency_median_ms"] = mean
        results.append(sample(base_tags(target, probe_type, ip), fields))
    return results


def probe_traceroute(
    target: TargetConfig, probe: ProbeConfig, tcp: bool
) -> list[Sample]:
    return TracerouteProbe(tcp, probe.max_hops, probe.port).run(target)
