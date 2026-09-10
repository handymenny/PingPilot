from pathlib import Path
import unittest

from monitoring.config import load_config


class ConfigTests(unittest.TestCase):
    def test_example_uses_global_dns_and_single_target_values(self) -> None:
        config = load_config(Path("config.example.yaml"))

        self.assertEqual(
            config.targets[0].global_dns_cfg.nameservers, ("1.1.1.1", "8.8.8.8")
        )
        self.assertEqual(config.ip_version, 4)
        self.assertEqual(config.targets[0].ip_version, 4)
        self.assertEqual(config.targets[0].target, "1.1.1.1")
        self.assertEqual(config.targets[1].target, "https://example.com/")
        self.assertEqual(config.targets[1].probe.type, "curl")
        self.assertEqual(config.targets[1].probe.method, "GET")
        self.assertEqual(config.targets[1].probe.expected_text, "Example Domain")
        self.assertEqual(config.targets[1].probe.user_agent, "ping-monitor/1.0")
        self.assertEqual(config.targets[2].target, "example.com")
        self.assertEqual(
            config.targets[2].global_dns_cfg, config.targets[0].global_dns_cfg
        )
        self.assertEqual(config.scheduler.interval_seconds, 60)
        self.assertEqual(config.scheduler.minimum_delay_between_targets_seconds, 1)
        self.assertFalse(config.scheduler.random_order)
        self.assertEqual(config.targets[2].probe.type, "icmp_ping")
        self.assertEqual(config.targets[2].count, 3)
        self.assertEqual(config.targets[2].minimum_delay_per_ping_seconds, 1)

        def test_target_names_must_be_unique(self) -> None:
            path = Path("tests/duplicate-names-config.yaml")
            path.write_text(
                """
global_config:
    influx:
        url: http://localhost:8086
        database: monitoring
targets:
    - name: duplicate
        target: example.com
        probe_type: icmp_ping
    - name: duplicate
        target: 1.1.1.1
        probe_type: icmp_ping
""",
                encoding="utf-8",
            )
            try:
                with self.assertRaisesRegex(ValueError, "target names must be unique"):
                    load_config(path)
            finally:
                path.unlink()

    def test_ipv6_is_propagated_to_targets(self) -> None:
        path = Path("tests/ipv6-config.yaml")
        path.write_text(
            """
global_config:
  ip_version: 6
  influx:
    url: http://localhost:8086
    database: monitoring
targets:
  - target: example.com
    probe_type: icmp_ping
""",
            encoding="utf-8",
        )
        try:
            config = load_config(path)
        finally:
            path.unlink()

        self.assertEqual(config.ip_version, 6)
        self.assertEqual(config.targets[0].ip_version, 6)


if __name__ == "__main__":
    unittest.main()
