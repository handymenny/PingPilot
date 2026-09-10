from __future__ import annotations

from .models import MonitorConfig, TargetConfig


def estimated_target_duration(target: TargetConfig) -> float:
    """Return a conservative upper bound for one target execution."""
    if target.probe is None:
        return 0
    probe = target.probe
    timeout = target.timeout_seconds
    if probe.type in {"traceroute_icmp", "traceroute_tcp"}:
        attempts_per_run = probe.max_hops * target.count
    else:
        attempts_per_run = target.count
    total_attempts = attempts_per_run
    delays = max(0, total_attempts - 1) * target.minimum_delay_per_ping_seconds
    return total_attempts * timeout + delays


def validate_schedule(config: MonitorConfig) -> list[str]:
    interval = config.scheduler.interval_seconds
    messages: list[str] = []
    for target in config.targets:
        duration = estimated_target_duration(target)
        difference = duration - interval
        if difference > 0:
            messages.append(
                f"target {target.name!r} can take up to {duration:.1f}s, "
                f"exceeding the global interval by {difference:.1f}s"
            )
        else:
            messages.append(
                f"target {target.name!r}: estimated maximum {duration:.1f}s "
                f"within the global interval ({interval:.1f}s)"
            )
    return messages


def estimated_cycle_duration(config: MonitorConfig) -> float:
    """Return the total time to execute all targets sequentially, including minimum delays."""
    total = sum(estimated_target_duration(target) for target in config.targets)
    # Aggiungi i ritardi minimi tra un target e l'altro (N-1 ritardi per N target)
    n_targets = len(config.targets)
    if n_targets > 1:
        total += (
            n_targets - 1
        ) * config.scheduler.minimum_delay_between_targets_seconds
    return total


def validate_full_cycle(config: MonitorConfig) -> list[str]:
    """
    Validate che l'intero ciclo di tutti i target rientri nell'intervallo configurato.
    Restituisce (durata_totale_ciclo, lista_messaggi).
    """
    cycle_duration = estimated_cycle_duration(config)
    interval = config.scheduler.interval_seconds
    messages: list[str] = []

    # Messaggio sul ciclo complessivo
    if cycle_duration > interval:
        messages.append(
            f"{cycle_duration:.1f}s total for {len(config.targets)} targets, "
            f"exceeding the configured interval ({interval:.1f}s) by {cycle_duration - interval:.1f}s"
        )
    else:
        messages.append(
            f"{cycle_duration:.1f}s total for {len(config.targets)} targets, "
            f"within the configured interval ({interval:.1f}s)"
        )

    return messages
