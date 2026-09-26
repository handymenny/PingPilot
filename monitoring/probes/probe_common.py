import ipaddress
import logging
import shutil
from statistics import median
import random

from ..models import DnsConfig, Scalar
from ..process import run as run_process


LOG = logging.getLogger(__name__)


def latency_fields(
    latencies: list[float | None], losses: list[bool]
) -> dict[str, Scalar]:
    fields: dict[str, Scalar] = {"loss_percent": sum(losses) / len(losses) * 100}
    successful_latencies = [
        latency
        for latency, loss in zip(latencies, losses)
        if not loss and latency is not None
    ]
    if successful_latencies:
        fields.update(
            {
                "latency_min_ms": min(successful_latencies),
                "latency_max_ms": max(successful_latencies),
                "latency_mean_ms": sum(successful_latencies)
                / len(successful_latencies),
                "latency_median_ms": median(successful_latencies),
            }
        )
    return fields


def resolved_ip(host: str, dns: DnsConfig = DnsConfig(), ip_version: int = 4) -> str:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    kdig = shutil.which("kdig")
    if not kdig:
        return ""
    nameservers = list(dns.nameservers)
    if dns.random_order:
        random.shuffle(nameservers)
    nameserver_args = [f"@{nameserver}" for nameserver in nameservers] or [""]
    for nameserver_arg in nameserver_args:
        command = [kdig, "+short"]
        if nameserver_arg:
            command.append(nameserver_arg)
        command.extend([host, "AAAA" if ip_version == 6 else "A"])

        try:
            result = run_process(
                command,
                capture_output=True,
                text=True,
                timeout=dns.timeout_seconds,
                check=False,
            )  # nosec B603
        except Exception as exc:
            LOG.warning("IP resolution failed for %s: %s", host, exc)
            continue

        for line in result.stdout.splitlines():
            candidate = line.strip()
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if address.version == ip_version:
                return candidate
    return ""
