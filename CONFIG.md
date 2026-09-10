# PingPilot configuration

PingPilot reads one YAML configuration file. Start from `config.example.yaml`, save it as `config.yaml`, and run:

```sh
python monitor.py --config config.yaml
```

The root contains `global_config` and `targets`.

```yaml
global_config:
  influx:
    url: http://localhost:8086
    database: monitoring
    username: monitor
    password: change-me
    measurement: network
    verify_tls: true

  ip_version: 4

  dns:
    nameservers: [1.1.1.1, 8.8.8.8]
    timeout_seconds: 1
    random_order: false

  scheduler:
    interval_seconds: 60
    minimum_delay_between_targets_seconds: 1
    random_order: false

targets: []
```

## Global options

### `global_config.influx`

| Key | Meaning |
|---|---|
| `url` | Base URL of the InfluxDB HTTP endpoint, for example `http://influxdb:8086` |
| `database` | Database used by the InfluxDB v1 write endpoint |
| `username` | Optional HTTP-authentication username |
| `password` | Optional HTTP-authentication password |
| `measurement` | Base measurement name; PingPilot appends the probe type |
| `verify_tls` | Enables or disables TLS certificate verification for an HTTPS InfluxDB endpoint |

PingPilot writes to `POST /write?db=<database>&precision=ns`. This works with InfluxDB 1.x and with InfluxDB 2.x only when its v1 compatibility API is configured.

Do not commit production credentials. Prefer a local untracked configuration file, Docker secrets, or another secrets-management mechanism.

### `global_config.ip_version`

Set `ip_version` to `4` or `6`; the default is `4`.

- `4` resolves hostnames through `A` records and forces IPv4 where supported by the probe.
- `6` resolves hostnames through `AAAA` records and forces IPv6 where supported by the probe.

The selected IP version applies to target hostname resolution and probes. DNS nameserver addresses must be reachable using the networking available to the runner.

### `global_config.dns`

| Key | Meaning |
|---|---|
| `nameservers` | Resolver addresses used to resolve hostnames for applicable targets |
| `timeout_seconds` | Timeout for a resolution attempt against each resolver |
| `random_order` | When `true`, resolver order is randomized for each resolution; otherwise the declared order is used |

These resolvers are used to resolve hostname targets. A `dns` probe is different: its `target` is the nameserver being tested.

### `global_config.scheduler`

| Key | Meaning |
|---|---|
| `interval_seconds` | Intended interval between the start of full monitoring cycles |
| `minimum_delay_between_targets_seconds` | Minimum pause after one target finishes before the next starts |
| `random_order` | When `true`, target order is shuffled once at startup and retained for later cycles |

If all targets take longer than `interval_seconds`, PingPilot logs a warning and begins the next cycle immediately after the previous cycle ends.

## Target options

Each item in `targets` defines one measurement target.

| Key | Meaning |
|---|---|
| `name` | Unique target name, exported as the InfluxDB `name` tag |
| `target` | Probe destination; its format depends on `probe_type` |
| `probe_type` | One of `dns`, `curl`, `icmp_ping`, `tcp_ping`, `traceroute_icmp`, or `traceroute_tcp` |
| `timeout_seconds` | Maximum timeout for the target probe |
| `count` | Number of repeated measurements or command cycles for the probe |
| `minimum_delay_per_ping_seconds` | Minimum delay between repeated measurements |
| `add_opts` | Map of probe-specific options; required for several probe types |

Use a separate target entry when the same endpoint needs multiple measurements. `name` must stay unique even if the `target` value is the same.

## Probe configuration

### DNS

The `target` is the nameserver to query. `query` is the domain name being requested.

```yaml
- name: cloudflare-dns
  target: 1.1.1.1
  timeout_seconds: 3
  count: 1
  minimum_delay_per_ping_seconds: 0
  probe_type: dns
  add_opts:
    query: example.com
    record_type: A
```

| `add_opts` key | Meaning |
|---|---|
| `query` | DNS name to query |
| `record_type` | Requested DNS record type, for example `A` or `AAAA` |

### HTTP/HTTPS

The `target` is a full URL. Before making the request, PingPilot resolves its hostname using the configured resolvers and supplies the selected address to `curl` with `--resolve`; the original hostname remains in the request and TLS verification context.

```yaml
- name: example-web
  target: https://example.com/
  timeout_seconds: 3
  count: 1
  minimum_delay_per_ping_seconds: 0
  probe_type: curl
  add_opts:
    method: GET
    expected_status: 200
    expected_text: Example Domain
    user_agent: pingpilot/1.0
```

| `add_opts` key | Required | Meaning |
|---|---:|---|
| `method` | Yes | HTTP method, for example `GET` |
| `expected_status` | Yes | HTTP status code required for a successful sample |
| `expected_text` | No | Case-sensitive string that must occur in the response body |
| `user_agent` | No | Value sent in the HTTP `User-Agent` header |

A status mismatch or missing `expected_text` is counted as a failed sample. HTTP status and body-check results are not emitted as dedicated InfluxDB fields.

### ICMP ping

The `target` is a hostname or IP address.

```yaml
- name: example-host
  target: example.com
  timeout_seconds: 3
  count: 3
  minimum_delay_per_ping_seconds: 1
  probe_type: icmp_ping
```

ICMP uses `fping`. `count`, timeout, and per-ping delay are passed to the external tool where applicable.

### TCP ping

The `target` is a hostname or IP address. `port` is required.

```yaml
- name: example-host-tcp
  target: example.com
  timeout_seconds: 3
  count: 3
  minimum_delay_per_ping_seconds: 1
  probe_type: tcp_ping
  add_opts:
    port: 443
```

| `add_opts` key | Meaning |
|---|---|
| `port` | TCP destination port |

TCP ping uses `tcpping` and measures TCP connection success and latency; it is not an ICMP probe.

### ICMP traceroute

The `target` is a hostname or IP address.

```yaml
- name: example-host-traceroute-icmp
  target: example.com
  timeout_seconds: 3
  count: 1
  minimum_delay_per_ping_seconds: 0
  probe_type: traceroute_icmp
  add_opts:
    max_hops: 30
```

### TCP traceroute

The `target` is a hostname or IP address. A TCP port is required.

```yaml
- name: example-host-traceroute-tcp
  target: example.com
  timeout_seconds: 3
  count: 1
  minimum_delay_per_ping_seconds: 0
  probe_type: traceroute_tcp
  add_opts:
    port: 443
    max_hops: 30
```

| `add_opts` key | Required by | Meaning |
|---|---|---|
| `max_hops` | Both traceroute probes | Maximum number of hops to inspect |
| `port` | `traceroute_tcp` | TCP destination port |

Traceroute uses `mtr`. It emits a measurement for each reported hop rather than one aggregate target measurement.

## Repetitions, timeouts, and loss

`count` is a number of repeated measurements, not a failure-only retry policy.

| Probe | Repetition handling |
|---|---|
| `icmp_ping` | `fping` performs repeated pings |
| `tcp_ping` | `tcpping` performs repeated TCP connection attempts |
| `traceroute_icmp` / `traceroute_tcp` | `mtr` performs report cycles and aggregates statistics by hop |
| `dns` | PingPilot runs repeated `kdig` commands and aggregates results |
| `curl` | PingPilot runs repeated `curl` commands and aggregates results |

A command failure or unsuccessful sample contributes to loss. Command errors are logged but are not exported in an InfluxDB `error` field.

## InfluxDB metrics

The value of `global_config.influx.measurement` is used as the measurement name for every written sample.

Common tags are `target`, `name`, `type`, and `resolved_ip` (the IP address to which the target resolves).

All probes emit `loss_percent` and, when at least one response exists, emit `latency_min_ms`, `latency_max_ms`, `latency_mean_ms`, and `latency_median_ms`.

Traceroute measurements also have these additional tags for each reported hop: `host`, `hop`, `ip`, and `asn`.
