from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import yaml

from .models import (
    DnsConfig,
    InfluxConfig,
    IpVersion,
    MonitorConfig,
    ProbeConfig,
    SchedulerConfig,
    TargetConfig,
)


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return cast(Mapping[str, object], value)


def _string(mapping: Mapping[str, object], key: str, default: str | None = None) -> str:
    value = mapping.get(key, default)
    if value is None:
        raise ValueError(f"missing configuration value: {key}")
    return str(value)


def _number(value: object, context: str) -> str | int | float:
    if not isinstance(value, (str, int, float)):
        raise ValueError(f"{context} must be numeric")
    return value


def _float(
    mapping: Mapping[str, object], key: str, default: float | None = None
) -> float | None:
    value = mapping.get(key, default)
    return None if value is None else float(_number(value, key))


def _int(
    mapping: Mapping[str, object], key: str, default: int | None = None
) -> int | None:
    value = mapping.get(key, default)
    return None if value is None else int(_number(value, key))


def _required_float(mapping: Mapping[str, object], key: str, default: float) -> float:
    value = _float(mapping, key, default)
    if value is None:
        raise ValueError(f"missing configuration value: {key}")
    return value


def _required_int(mapping: Mapping[str, object], key: str, default: int) -> int:
    value = _int(mapping, key, default)
    if value is None:
        raise ValueError(f"missing configuration value: {key}")
    return value


def _strings(value: object, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{context} must be a list")
    return tuple(str(item) for item in value)


def _ip_version(mapping: Mapping[str, object]) -> IpVersion:
    value = mapping.get("ip_version", 4)
    if value not in (4, 6, "4", "6"):
        raise ValueError("ip_version must be 4 or 6")
    return int(value)  # type: ignore[return-value]


def _probe(probe_type_value: object, options_value: object) -> ProbeConfig:
    probe_type = str(probe_type_value).lower()
    raw = _mapping(options_value, "add_opts")
    return ProbeConfig(
        type=probe_type,
        query=None if raw.get("query") is None else str(raw["query"]),
        record_type=_string(raw, "record_type", "A"),
        method=_string(raw, "method", "GET").upper(),
        expected_status=_int(raw, "expected_status"),
        expected_text=None
        if raw.get("expected_text") is None
        else str(raw["expected_text"]),
        user_agent=None if raw.get("user_agent") is None else str(raw["user_agent"]),
        port=_int(raw, "port"),
        max_hops=_required_int(raw, "max_hops", 30),
    )


def _target(value: object, dns: DnsConfig, ip_version: IpVersion) -> TargetConfig:
    raw = _mapping(value, "target")
    target_value = raw.get("target", raw.get("host"))
    if not target_value:
        raise ValueError("each target must define target")
    target = str(target_value)
    probe_type = raw.get("probe_type")
    if probe_type is None:
        raise ValueError(f"target {target} must define probe_type")
    return TargetConfig(
        name=_string(raw, "name", target),
        target=target,
        timeout_seconds=_required_int(raw, "timeout_seconds", 3),
        count=_required_int(raw, "count", 1),
        minimum_delay_per_ping_seconds=_required_float(
            raw, "minimum_delay_per_ping_seconds", 0
        ),
        probe=_probe(probe_type, raw.get("add_opts", {})),
        global_dns_cfg=dns,
        ip_version=ip_version,
    )


def load_config(path: Path) -> MonitorConfig:
    with path.open(encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}
    config = _mapping(raw_config, "config")
    global_config = _mapping(config.get("global_config", {}), "global_config")

    ip_version = _ip_version(global_config)
    raw_targets = config.get("targets", ())
    if (
        isinstance(raw_targets, (str, bytes))
        or not isinstance(raw_targets, Sequence)
        or not raw_targets
    ):
        raise ValueError("config must contain at least one target")
    dns_config = _mapping(global_config.get("dns", {}), "dns")
    nameservers = _strings(dns_config.get("nameservers"), "dns.nameservers")
    dns = DnsConfig(
        nameservers=nameservers,
        timeout_seconds=_required_float(dns_config, "timeout_seconds", 1),
        random_order=bool(dns_config.get("random_order", False)),
    )
    influx = _mapping(global_config.get("influx", {}), "influx")
    scheduler = _mapping(global_config.get("scheduler", {}), "scheduler")

    targets = tuple(_target(item, dns, ip_version) for item in raw_targets)
    target_names = [target.name for target in targets]
    if len(target_names) != len(set(target_names)):
        raise ValueError("target names must be unique")

    return MonitorConfig(
        influx=InfluxConfig(
            url=_string(influx, "url"),
            database=_string(influx, "database"),
            username=_string(influx, "username", ""),
            password=_string(influx, "password", ""),
            measurement=_string(influx, "measurement", "network"),
            verify_tls=bool(influx.get("verify_tls", True)),
        ),
        scheduler=SchedulerConfig(
            interval_seconds=_required_float(scheduler, "interval_seconds", 60),
            minimum_delay_between_targets_seconds=_required_float(
                scheduler, "minimum_delay_between_targets_seconds", 0
            ),
            random_order=bool(scheduler.get("random_order", False)),
        ),
        targets=targets,
        global_dns_cfg=dns,
        ip_version=ip_version,
    )
