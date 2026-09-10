# PingPilot

PingPilot is a YAML-configured active network monitor compatible with InfluxDB. 
It runs DNS, HTTP(S), ICMP, TCP-connect, and traceroute probes, then writes aggregated measurements to InfluxDB through the v1 HTTP line-protocol API.

> **Note:** This is early-stage software written with extensive use of LLM support. Use at your own risk. IPv6 support and traceroute probes are not tested.

## Features

- DNS query monitoring through `kdig`
- HTTP/HTTPS endpoint checks through `curl`
- ICMP reachability, latency, and loss through `fping`
- TCP-connect reachability and latency through `tcpping`
- ICMP and TCP traceroute statistics through `mtr`
- IPv4 or IPv6 operation
- InfluxDB v1 line-protocol export
- Sequential, predictable execution per runner instance

## Quick start

1. Copy the example configuration:

   ```sh
   cp config.example.yaml config.yaml
   ```

2. Install Python dependencies and the [required system tools](#requirements). 
   See [Docker deployment](DOCKER.md) for a container-based setup instead.

3. Run all configured targets once:

   ```sh
   python -m pip install -r requirements.txt
   python monitor.py --config config.yaml --once
   ```

4. Run continuously:

   ```sh
   python monitor.py --config config.yaml
   ```

Run the automated tests with:

```sh
python -m unittest discover -s tests -v
```

## Supported probes

| Probe type | Target value | Options | Purpose |
|---|---|---|---|
| `dns` | Nameserver address | `query`, `record_type` | Measures DNS query success and latency |
| `curl` | Full HTTP/HTTPS URL | `method`, `expected_status` | Checks an endpoint and measures request latency |
| `icmp_ping` | Hostname or IP address | — | Measures ICMP reachability, loss, and latency |
| `tcp_ping` | Hostname or IP address | `port` | Measures TCP-connect reachability, loss, and latency |
| `traceroute_icmp` | Hostname or IP address | `max_hops` | Produces ICMP traceroute statistics per hop |
| `traceroute_tcp` | Hostname or IP address | `port`, `max_hops` | Produces TCP traceroute statistics per hop |

## Execution model

A PingPilot instance runs targets sequentially. It starts a cycle, executes every configured target, waits for the remaining time in `scheduler.interval_seconds`, and starts the next cycle. If a cycle takes longer than the configured interval, PingPilot logs a warning and starts the next cycle immediately.

Keep the worst-case duration of all configured targets below the interval. For a large estate, split targets across multiple independent PingPilot instances rather than relying on concurrency within one instance.

## Configuration

See **[CONFIG.md](CONFIG.md)** for the complete configuration reference, option meanings, probe examples, timing behaviour, and InfluxDB metric schema.

## Requirements

PingPilot requires Python and `PyYAML` for parsing the YAML configuration. 
It also requires the following system commands in `PATH`:

- `curl` for HTTP/HTTPS probes
- `kdig` for DNS probes and hostname resolution through configured resolvers
- `fping` for ICMP probes
- [`tcpping`](https://github.com/deajan/tcpping) for TCP probes
- `mtr` for traceroute probes and ASN lookup

On Linux, install `tcpping` if your distribution does not package it:

```sh
curl -fsSL https://raw.githubusercontent.com/deajan/tcpping/master/tcpping -o /usr/local/bin/tcpping
chmod 755 /usr/local/bin/tcpping
```

## Docker

You can run PingPilot in a Docker container. See **[DOCKER.md](DOCKER.md)** for details.

## License

See **[LICENSE](LICENSE)** for license information.
