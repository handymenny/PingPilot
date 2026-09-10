from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal


type Scalar = str | int | float | bool
type IpVersion = Literal[4, 6]


@dataclass(frozen=True, slots=True)
class Sample:
    tags: dict[str, str]
    fields: dict[str, Scalar]
    timestamp_ns: int


@dataclass(frozen=True, slots=True)
class ProbeConfig:
    type: str
    query: str | None = None
    record_type: str = "A"
    method: str = "GET"
    expected_status: int | None = None
    expected_text: str | None = None
    user_agent: str | None = None
    port: int | None = None
    max_hops: int = 30


@dataclass(frozen=True, slots=True)
class DnsConfig:
    nameservers: tuple[str, ...] = ()
    timeout_seconds: float = 1
    random_order: bool = False


@dataclass(frozen=True, slots=True)
class TargetConfig:
    name: str
    target: str
    timeout_seconds: int = 3
    count: int = 1
    minimum_delay_per_ping_seconds: float = 0
    probe: ProbeConfig | None = None
    global_dns_cfg: DnsConfig = DnsConfig()
    ip_version: IpVersion = 4


@dataclass(frozen=True, slots=True)
class InfluxConfig:
    url: str
    database: str
    username: str = ""
    password: str = ""
    measurement: str = "network"
    verify_tls: bool = True


@dataclass(frozen=True, slots=True)
class SchedulerConfig:
    interval_seconds: float = 60
    minimum_delay_between_targets_seconds: float = 0
    random_order: bool = False


@dataclass(frozen=True, slots=True)
class MonitorConfig:
    influx: InfluxConfig
    scheduler: SchedulerConfig
    targets: tuple[TargetConfig, ...]
    global_dns_cfg: DnsConfig = DnsConfig()
    ip_version: IpVersion = 4


def now_ns() -> int:
    return time.time_ns()


def base_tags(
    target_cfg: TargetConfig, probe_type: str, ip: str = ""
) -> dict[str, str]:
    return {
        "target": target_cfg.target,
        "name": target_cfg.name,
        "type": probe_type,
        "resolved_ip": ip,
    }


def sample(tags: dict[str, str], fields: dict[str, Scalar]) -> Sample:
    return Sample(tags, fields, now_ns())
