import unittest

from monitoring.influx import to_line_protocol
from monitoring.models import Sample


class InfluxTests(unittest.TestCase):
    def test_line_protocol_escapes_tags_and_types_fields(self) -> None:
        point = Sample(
            {"target": "host name", "type": "icmp_ping"},
            {"loss_percent": 100.0, "latency_mean_ms": 1.25, "count": 2},
            123,
        )

        self.assertEqual(
            to_line_protocol("network_ping", point),
            "network_ping,target=host\\ name,type=icmp_ping count=2i,latency_mean_ms=1.25,loss_percent=100.0 123",
        )

    def test_line_protocol_omits_empty_tags(self) -> None:
        point = Sample(
            {"resolved_ip": "", "target": "1.1.1.1"},
            {"loss_percent": 0.0},
            123,
        )

        self.assertEqual(
            to_line_protocol("network_ping", point),
            "network_ping,target=1.1.1.1 loss_percent=0.0 123",
        )


if __name__ == "__main__":
    unittest.main()
