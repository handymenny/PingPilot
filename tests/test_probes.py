import unittest
from unittest.mock import patch

from monitoring import probes
from monitoring.probes import curl, dns, icmp, probe_common, tcp, traceroute
from monitoring.models import DnsConfig, ProbeConfig, TargetConfig
from monitoring.probes import build_probe


class ProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = TargetConfig(name="test", target="127.0.0.1")

    def test_icmp_uses_fping_for_all_pings(self) -> None:
        with patch.object(icmp.shutil, "which", return_value="fping"), patch.object(
            icmp, "_run_icmp", return_value=([1.0, 1.0, 1.0], "")
        ) as _run_icmp:
            target = TargetConfig(
                name="test",
                target="127.0.0.1",
                timeout_seconds=1,
                count=3,
                minimum_delay_per_ping_seconds=0.5,
                ip_version=4,
            )
            results = probes.probe_icmp(target, ProbeConfig(type="icmp_ping"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].fields["latency_min_ms"], 1.0)
        self.assertEqual(results[0].fields["latency_max_ms"], 1.0)
        self.assertEqual(results[0].fields["latency_mean_ms"], 1.0)
        self.assertEqual(results[0].fields["latency_median_ms"], 1.0)
        self.assertEqual(results[0].fields["loss_percent"], 0.0)
        _run_icmp.assert_called_once_with("127.0.0.1", 1, 3, 0.5, 4)

    def test_probe_instances_can_run_directly(self) -> None:
        target = TargetConfig(name="test", target="127.0.0.1", timeout_seconds=1)
        with patch.object(icmp.shutil, "which", return_value="fping"), patch.object(
            icmp, "_run_icmp", return_value=([1.0], "")
        ):
            result = icmp.IcmpProbe().run(target)

        self.assertEqual(result[0].fields["latency_mean_ms"], 1.0)

    def test_build_probe_creates_concrete_probe_instance(self) -> None:
        probe: tcp.TcpProbe = build_probe(ProbeConfig(type="tcp_ping", port=443))  # type: ignore

        self.assertIsInstance(probe, tcp.TcpProbe)
        self.assertEqual(probe.port, 443)

    def test_fping_receives_repetitions_delay_and_timeout(self) -> None:
        result = type(
            "FpingResult",
            (),
            {
                "stdout": "127.0.0.1 : [0], 64 bytes, 1.0 ms (7.28 avg, 0% loss)\n127.0.0.1 : [1], 64 bytes, 2.0 ms (8.39 avg, 0% loss)\n127.0.0.1 : [2], 64 bytes, timed out (NaN avg, 100% loss)\n",
                "stderr": "",
                "returncode": 1,
            },
        )()
        with patch.object(icmp.shutil, "which", return_value="fping"), patch.object(
            icmp.subprocess, "run", return_value=result
        ) as run:
            latencies, _ = icmp._run_icmp("127.0.0.1", 3, 3, 0.5)

        self.assertEqual(latencies, [1.0, 2.0, None])
        self.assertEqual(
            run.call_args.args[0],
            ["fping", "-C", "3", "-t", "3000", "-p", "500", "127.0.0.1"],
        )

    def test_resolved_ip_accepts_literal_ip_addresses(self) -> None:
        default_dns = DnsConfig(nameservers=("8.8.8.8",))
        self.assertEqual(probe_common.resolved_ip("1.1.1.1", default_dns), "1.1.1.1")

    def test_resolved_ip_uses_system_default_nameserver(self) -> None:
        result = type(
            "KdigResult", (), {"stdout": "1.1.1.1\n", "stderr": "", "returncode": 0}
        )()
        with patch.object(
            probe_common.shutil, "which", return_value="kdig"
        ), patch.object(probe_common.subprocess, "run", return_value=result) as run:
            resolved = probe_common.resolved_ip("example.com")

        self.assertEqual(resolved, "1.1.1.1")
        self.assertEqual(run.call_args.args[0], ["kdig", "+short", "example.com", "A"])

    def test_resolved_ip_uses_aaaa_for_ipv6(self) -> None:
        result = type(
            "KdigResult", (), {"stdout": "2001:db8::1\n", "stderr": "", "returncode": 0}
        )()
        with patch.object(
            probe_common.shutil, "which", return_value="kdig"
        ), patch.object(probe_common.subprocess, "run", return_value=result) as run:
            resolved = probe_common.resolved_ip("example.com", DnsConfig(), 6)

        self.assertEqual(resolved, "2001:db8::1")
        self.assertEqual(
            run.call_args.args[0], ["kdig", "+short", "example.com", "AAAA"]
        )

    def test_tcp_uses_tcpping_latency(self) -> None:
        result = type(
            "TcpPingResult",
            (),
            {
                "stdout": "tcp response from 127.0.0.1:443 time=12.5 ms\n",
                "stderr": "",
                "returncode": 0,
            },
        )()
        with patch.object(tcp, "resolved_ip", return_value="127.0.0.1"), patch.object(
            tcp.shutil, "which", return_value="tcpping"
        ), patch.object(tcp.subprocess, "run", return_value=result) as run:
            target = TargetConfig(name="test", target="example.com")
            fields = probes.probe_tcp(target, ProbeConfig(type="tcp_ping", port=443))[
                0
            ].fields

        self.assertEqual(fields["latency_mean_ms"], 12.5)
        self.assertEqual(fields["loss_percent"], 0.0)
        self.assertEqual(
            run.call_args.args[0],
            ["tcpping", "-w", "3", "-r", "0", "-x", "1", "127.0.0.1", "443"],
        )

    def test_tcp_delegates_repetitions_and_delay_to_tcpping(self) -> None:
        result = type(
            "TcpPingResult",
            (),
            {
                "stdout": "seq 0: tcp response from 127.0.0.1:443 time=12.5 ms\nseq 1: tcp response from 127.0.0.1:443 time=15 ms\n",
                "stderr": "",
                "returncode": 0,
            },
        )()
        with patch.object(tcp, "resolved_ip", return_value="127.0.0.1"), patch.object(
            tcp.shutil, "which", return_value="tcpping"
        ), patch.object(tcp.subprocess, "run", return_value=result) as run:
            target = TargetConfig(
                name="test",
                target="example.com",
                timeout_seconds=2,
                count=2,
                minimum_delay_per_ping_seconds=0.5,
            )
            fields = probes.probe_tcp(target, ProbeConfig(type="tcp_ping", port=443))[
                0
            ].fields

        self.assertEqual(fields["latency_mean_ms"], 13.75)
        self.assertEqual(fields["loss_percent"], 0.0)
        self.assertEqual(
            run.call_args.args[0],
            ["tcpping", "-w", "2", "-r", "0.5", "-x", "2", "127.0.0.1", "443"],
        )

    def test_icmp_does_not_report_latency_for_lost_pings(self) -> None:
        with patch.object(icmp.shutil, "which", return_value="fping"), patch.object(
            icmp, "_run_icmp", return_value=([None], "timed out")
        ):
            target = TargetConfig(name="test", target="127.0.0.1", timeout_seconds=3)
            fields = probes.probe_icmp(target, ProbeConfig(type="icmp_ping"))[0].fields

        self.assertEqual(fields["loss_percent"], 100.0)
        self.assertNotIn("latency_mean_ms", fields)
        self.assertNotIn("error", fields)

    def test_icmp_command_error_is_reported_as_loss(self) -> None:
        with patch.object(icmp.shutil, "which", return_value="fping"), patch.object(
            icmp.subprocess, "run", side_effect=OSError("fping unavailable")
        ):
            target = TargetConfig(name="test", target="127.0.0.1")
            fields = probes.probe_icmp(target, ProbeConfig(type="icmp_ping"))[0].fields

        self.assertEqual(fields["loss_percent"], 100.0)
        self.assertNotIn("error", fields)

    def test_tcp_command_error_is_reported_as_loss(self) -> None:
        with patch.object(tcp, "resolved_ip", return_value="127.0.0.1"), patch.object(
            tcp.shutil, "which", return_value="tcpping"
        ), patch.object(
            tcp.subprocess, "run", side_effect=OSError("tcpping unavailable")
        ):
            target = TargetConfig(name="test", target="example.com")
            fields = probes.probe_tcp(target, ProbeConfig(type="tcp_ping", port=443))[
                0
            ].fields

        self.assertEqual(fields["loss_percent"], 100.0)
        self.assertNotIn("error", fields)

    def test_dns_uses_kdig_query_time(self) -> None:
        result = type(
            "DnsResult",
            (),
            {
                "stdout": "example.com. 149 IN A 172.66.147.243\nexample.com. 149 IN A 104.20.23.154\n;; From 1.1.1.1@53(UDP) in 19.7 ms\n",
                "stderr": "",
                "returncode": 0,
            },
        )()
        with patch.object(dns, "resolved_ip", return_value="8.8.8.8"), patch.object(
            dns.shutil, "which", return_value="kdig"
        ), patch.object(dns.subprocess, "run", return_value=result):
            target = TargetConfig(name="dns", target="example.com")
            fields = probes.probe_dns(
                target, ProbeConfig(type="dns", query="example.com")
            )[0].fields

        self.assertEqual(fields["latency_mean_ms"], 19.7)

    def test_curl_requires_expected_text_in_response_body(self) -> None:
        target = TargetConfig(name="web", target="https://example.com/")
        probe = ProbeConfig(type="curl", expected_text="page body")
        result = type(
            "CurlResult",
            (),
            {"stdout": "page body\n200\n0.012", "stderr": "", "returncode": 0},
        )()
        with patch.object(curl, "shutil") as shutil_module, patch.object(
            curl.subprocess, "run", return_value=result
        ):
            shutil_module.which.return_value = "curl"
            samples = probes.probe_curl(target, probe)

        self.assertEqual(samples[0].fields["loss_percent"], 0.0)
        self.assertNotIn("http_status", samples[0].fields)
        self.assertNotIn("content_match", samples[0].fields)
        self.assertEqual(samples[0].fields["latency_mean_ms"], 12.0)

    def test_curl_passes_custom_user_agent(self) -> None:
        target = TargetConfig(name="web", target="https://example.com/")
        result = type(
            "CurlResult",
            (),
            {"stdout": "\n200\n0.012", "stderr": "", "returncode": 0},
        )()
        with patch.object(curl, "shutil") as shutil_module, patch.object(
            curl.subprocess, "run", return_value=result
        ) as run:
            shutil_module.which.return_value = "curl"
            probes.probe_curl(
                target, ProbeConfig(type="curl", user_agent="monitor/1.0")
            )

        self.assertIn("--user-agent", run.call_args.args[0])
        self.assertIn("monitor/1.0", run.call_args.args[0])

    def test_traceroute_uses_mtr_csv(self) -> None:
        result = type(
            "MtrResult",
            (),
            {
                "stdout": "Mtr_Version,Start_Time,Status,Host,Hop,Ip,Asn,Loss%,Last,Best,Avg,Wrst,\nMTR.0.96,1727000000,OK,127.0.0.1,1,127.0.0.1,AS64500,0.00,0.20,0.10,0.30,0.40\n",
                "stderr": "",
                "returncode": 0,
            },
        )()
        with patch.object(traceroute.shutil, "which", return_value="mtr"), patch.object(
            traceroute.subprocess, "run", return_value=result
        ):
            target = TargetConfig(
                name="test",
                target="127.0.0.1",
                timeout_seconds=1,
                count=2,
                minimum_delay_per_ping_seconds=0,
            )
            results = probes.probe_traceroute(
                target,
                ProbeConfig(type="traceroute_icmp", max_hops=2),
                False,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].fields["asn"], "AS64500")
        self.assertEqual(results[0].fields["latency_min_ms"], 0.1)
        self.assertEqual(results[0].fields["latency_max_ms"], 0.4)
        self.assertEqual(results[0].fields["latency_mean_ms"], 0.3)
        self.assertEqual(results[0].fields["latency_median_ms"], 0.3)
        self.assertEqual(results[0].fields["loss_percent"], 0.0)

    def test_traceroute_passes_timeout_and_interval_to_mtr(self) -> None:
        result = type("MtrResult", (), {"stdout": "", "stderr": "", "returncode": 0})()
        with patch.object(traceroute.shutil, "which", return_value="mtr"), patch.object(
            traceroute.subprocess, "run", return_value=result
        ) as run:
            target = TargetConfig(
                name="test",
                target="127.0.0.1",
                timeout_seconds=3,
                minimum_delay_per_ping_seconds=0.5,
            )
            probes.probe_traceroute(
                target,
                ProbeConfig(type="traceroute_icmp", max_hops=2),
                False,
            )

        command = run.call_args.args[0]
        self.assertIn("--order", command)
        self.assertEqual(command[command.index("--order") + 1], "LNBAW")
        self.assertEqual(
            command[-5:], ["--timeout", "3", "--interval", "0.5", "127.0.0.1"]
        )


if __name__ == "__main__":
    unittest.main()
