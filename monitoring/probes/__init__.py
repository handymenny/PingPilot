from .curl import CurlProbe, probe_curl
from .dns import DnsProbe, probe_dns
from .icmp import IcmpProbe, probe_icmp
from ..models import ProbeConfig, Sample
from .tcp import TcpProbe, probe_tcp
from .traceroute import TracerouteProbe, probe_traceroute

__all__ = [
    "build_probe",
    "run_probe",
    "probe_curl",
    "probe_dns",
    "probe_icmp",
    "probe_tcp",
    "probe_traceroute",
]


def build_probe(config: ProbeConfig):
    """Create the concrete probe represented by a parsed configuration."""
    match config.type:
        case "dns":
            if config.query is None:
                raise ValueError("DNS probes require query")
            return DnsProbe(config.query, config.record_type)
        case "curl":
            return CurlProbe(
                config.method,
                config.expected_status,
                config.expected_text,
                config.user_agent,
            )
        case "icmp_ping":
            return IcmpProbe()
        case "tcp_ping":
            if config.port is None:
                raise ValueError("TCP ping probes require port")
            return TcpProbe(config.port)
        case "traceroute_icmp" | "traceroute_tcp":
            return TracerouteProbe(
                config.type.endswith("tcp"), config.max_hops, config.port
            )
        case _:
            raise ValueError(f"Unknown probe type: {config.type}")


def run_probe(target, probe) -> list[Sample]:
    instance = build_probe(probe) if isinstance(probe, ProbeConfig) else probe
    return instance.run(target)
