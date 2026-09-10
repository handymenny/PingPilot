from __future__ import annotations

import shutil
import logging
import subprocess  # nosec B404
import time
import urllib.parse
from dataclasses import dataclass

from ..influx import require_http_url
from ..models import ProbeConfig, Sample, Scalar, TargetConfig, base_tags, sample
from .probe_common import latency_fields, resolved_ip


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurlProbe:
    method: str = "GET"
    expected_status: int | None = None
    expected_text: str | None = None
    user_agent: str | None = None

    def run(self, target_cfg: TargetConfig) -> list[Sample]:
        return _run_curl(target_cfg, self)


def _run_curl(target_cfg: TargetConfig, probe: CurlProbe) -> list[Sample]:
    url = target_cfg.target
    require_http_url(url)
    timeout = target_cfg.timeout_seconds
    parsed_url = urllib.parse.urlparse(url)
    hostname = parsed_url.hostname or ""
    ip = resolved_ip(hostname, target_cfg.global_dns_cfg, target_cfg.ip_version)
    curl_path = shutil.which("curl")
    if not curl_path:
        raise RuntimeError("curl executable is required for curl probes")
    port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
    command = [
        curl_path,
        "--silent",
        "--show-error",
        "--request",
        probe.method,
        "--max-time",
        str(timeout),
    ]
    if probe.user_agent is not None:
        command.extend(["--user-agent", probe.user_agent])
    if target_cfg.ip_version == 6:
        command.append("--ipv6")
    if ip:
        command.extend(["--resolve", f"{hostname}:{port}:{ip}"])
    else:
        LOG.warning(
            "curl probe for %s: could not resolve hostname, passing hostname directly",
            target_cfg.name,
        )
    command.append(url)
    latencies: list[float | None] = []
    losses = []
    fields: dict[str, Scalar] = {}
    for attempt in range(target_cfg.count):
        status_code = 0
        content = ""
        latency = None
        try:
            result = subprocess.run(
                command + ["--write-out", "\n%{http_code}\n%{time_total}"],
                capture_output=True,
                text=True,
                timeout=timeout + 1,
                check=False,
            )  # nosec B603
            body, status_line, timing_line = (
                result.stdout.rsplit("\n", 2)
                if result.stdout.count("\n") >= 2
                else ("", "0", "")
            )
            content = body
            status_code = int(status_line.strip() or 0)
            latency = float(timing_line.strip()) * 1000 if timing_line.strip() else None
            if result.returncode != 0:
                LOG.warning(
                    "curl probe failed for %s: %s",
                    url,
                    result.stderr.strip()
                    or f"curl exited with code {result.returncode}",
                )
        except Exception as exc:
            LOG.warning("curl probe failed for %s: %s", url, exc)
        content_match = (
            True if probe.expected_text is None else probe.expected_text in content
        )
        loss = not (bool(status_code) and content_match)
        fields: dict[str, Scalar] = {}
        if probe.expected_status is not None:
            loss = status_code != probe.expected_status or not content_match
        latencies.append(latency)
        losses.append(loss)
        if (
            attempt < target_cfg.count - 1
            and target_cfg.minimum_delay_per_ping_seconds > 0
        ):
            time.sleep(target_cfg.minimum_delay_per_ping_seconds)
    fields.update(latency_fields(latencies, losses))
    return [sample(base_tags(target_cfg, "curl", ip), fields)]


def probe_curl(target: TargetConfig, probe: ProbeConfig) -> list[Sample]:
    return CurlProbe(
        probe.method, probe.expected_status, probe.expected_text, probe.user_agent
    ).run(target)
