import unittest
from unittest.mock import patch

from monitoring.models import (
    InfluxConfig,
    MonitorConfig,
    ProbeConfig,
    SchedulerConfig,
    TargetConfig,
)
from monitoring.runner import monitor
from monitoring.validation import estimated_target_duration, validate_schedule


class FakeInflux:
    measurement = "network"
    last_instance = None

    def __init__(self, config):
        self.writes = []
        type(self).last_instance = self

    def write(self, samples):
        self.writes.append(samples)


class RunnerTests(unittest.TestCase):
    def test_schedule_validation_accounts_for_count_timeout_and_delay(self) -> None:
        target = TargetConfig(
            name="slow-ping",
            target="127.0.0.1",
            timeout_seconds=3,
            count=3,
            minimum_delay_per_ping_seconds=1,
            probe=ProbeConfig(type="icmp_ping"),
        )
        config = MonitorConfig(
            influx=InfluxConfig(url="http://localhost:8086", database="monitoring"),
            scheduler=SchedulerConfig(interval_seconds=10),
            targets=(target,),
        )

        self.assertEqual(estimated_target_duration(target), 11)
        self.assertIn(
            "exceeding the global interval by 1.0s", validate_schedule(config)[0]
        )

    def test_random_order_is_shuffled_once_at_startup(self) -> None:
        config = MonitorConfig(
            influx=InfluxConfig(url="http://localhost:8086", database="monitoring"),
            targets=(
                TargetConfig(name="first", target="127.0.0.1"),
                TargetConfig(name="second", target="127.0.0.2"),
            ),
            scheduler=SchedulerConfig(interval_seconds=60, random_order=True),
        )
        with patch("monitoring.runner.random.shuffle") as shuffle:
            from monitoring.runner import target_order

            order = target_order(config)

        self.assertEqual(order, (0, 1))
        shuffle.assert_called_once_with([0, 1])

    def test_monitor_waits_for_remaining_cycle_interval(self) -> None:
        config = MonitorConfig(
            influx=InfluxConfig(url="http://localhost:8086", database="monitoring"),
            scheduler=SchedulerConfig(interval_seconds=10),
            targets=(
                TargetConfig(name="first", target="127.0.0.1"),
                TargetConfig(name="second", target="127.0.0.2"),
            ),
        )
        monotonic_values = iter([0.0, 0.0, 3.0, 3.0, 4.0, 4.0])
        with patch("monitoring.runner.InfluxV1", FakeInflux), patch(
            "monitoring.runner.run_probe", return_value=[]
        ), patch(
            "monitoring.runner.time.monotonic", side_effect=monotonic_values
        ), patch("monitoring.runner.time.sleep", side_effect=StopIteration) as sleep:
            with self.assertRaises(StopIteration):
                monitor(config)

        self.assertEqual(sleep.call_args.args, (6.0,))

    def test_once_runs_probe_and_exports_samples(self) -> None:
        config = MonitorConfig(
            influx=InfluxConfig(url="http://localhost:8086", database="monitoring"),
            scheduler=SchedulerConfig(),
            targets=(
                TargetConfig(
                    name="test", target="127.0.0.1", probe=ProbeConfig(type="icmp_ping")
                ),
            ),
        )
        with patch("monitoring.runner.InfluxV1", FakeInflux), patch(
            "monitoring.runner.run_probe", return_value=["sample"]
        ):
            monitor(config, once=True)

        self.assertIsNotNone(FakeInflux.last_instance)
        self.assertEqual(FakeInflux.last_instance.writes, [["sample"]])

    def test_probe_errors_are_logged_without_tracebacks(self) -> None:
        config = MonitorConfig(
            influx=InfluxConfig(url="http://localhost:8086", database="monitoring"),
            scheduler=SchedulerConfig(),
            targets=(
                TargetConfig(
                    name="test", target="127.0.0.1", probe=ProbeConfig(type="icmp_ping")
                ),
            ),
        )
        with patch("monitoring.runner.InfluxV1", FakeInflux), patch(
            "monitoring.runner.run_probe", side_effect=RuntimeError("fping unavailable")
        ), self.assertLogs("network-monitor", level="ERROR") as logs:
            monitor(config, once=True)

        self.assertEqual(
            logs.output,
            ["ERROR:network-monitor:Probe test/icmp_ping failed: fping unavailable"],
        )


if __name__ == "__main__":
    unittest.main()
