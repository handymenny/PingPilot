from __future__ import annotations

import csv
import logging
import shutil
from dataclasses import dataclass

from ..models import ProbeConfig, Sample, Scalar, TargetConfig, base_tags, sample
from ..process import run as run_process


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
        tags = base_tags(target, probe_type)
        tags["hop"] = "0"
        return sample(
            tags,
            {
                "host": target.target,
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
        "--csv",
        "--report-cycles",
        str(target.count),
        "--no-dns",
        "--aslookup",
        "--show-ips",
        "--order",
        "LNBAW",
        "--max-ttl",
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
        result = run_process(
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

    for row in csv.DictReader(result.stdout.splitlines()):
        try:
            hop = int(row["Hop"])
            loss_text = row["Loss%"]
            best_text = row["Best"]
            mean_text = row["Avg"]
            worst_text = row["Wrst"]
        except (KeyError, ValueError):
            continue
        loss_percent = float(loss_text)
        mean = None if mean_text == "-" else float(mean_text)
        minimum = None if best_text == "-" else float(best_text)
        maximum = None if worst_text == "-" else float(worst_text)
        probe_type = "traceroute_tcp" if probe.tcp else "traceroute_icmp"
        fields: dict[str, Scalar] = {
            "host": destination,
            "ip": row["Ip"],
            "asn": row["Asn"],
            "loss_percent": loss_percent,
        }
        if minimum is not None:
            fields["latency_min_ms"] = minimum
        if maximum is not None:
            fields["latency_max_ms"] = maximum
        if mean is not None:
            fields["latency_mean_ms"] = mean
        tags = base_tags(target, probe_type, row["Ip"])
        tags["hop"] = str(hop)
        results.append(sample(tags, fields))
    return results


def probe_traceroute(
    target: TargetConfig, probe: ProbeConfig, tcp: bool
) -> list[Sample]:
    return TracerouteProbe(tcp, probe.max_hops, probe.port).run(target)
