# PingPilot Docker deployment

The supplied Docker image contains Python and the command-line tools required by PingPilot: `curl`, `kdig`, `fping`, `tcpping`, `mtr`, and `traceroute`.

## Quick start

1. Create a configuration file:

   ```sh
   cp config.example.yaml config.yaml
   ```

2. Set `global_config.influx.url` in `config.yaml` to an InfluxDB endpoint reachable from the container.

3. Build and start PingPilot:

   ```sh
   docker compose up -d --build
   ```

4. Follow the container logs:

   ```sh
   docker compose logs -f ping-monitor
   ```

The Compose file mounts `./config.yaml` into the container at `/app/config.yaml` as read-only, you can edit the local file and restart the container to apply changes.

## Run once

To execute all configured targets once and exit, override the image entrypoint arguments:

```sh
docker compose run --rm ping-monitor --once
```

## Capabilities and probes

HTTP, DNS, and TCP-connect probes can often run without extra container capabilities. ICMP and traceroute may require additional permissions depending on the Docker runtime, host kernel, and selected probe mode.

The supplied `docker-compose.yml` intentionally leaves the capability block commented out:

```yaml
# Add only if required
# cap_add:
#  - NET_RAW
#  - NET_ADMIN
```

If ICMP or traceroute fails because of permissions, enable only the minimum capability set needed in your deployment:

```yaml
services:
  ping-monitor:
    build: .
    restart: unless-stopped
    cap_add:
      - NET_RAW
      - NET_ADMIN
    volumes:
      - ./config.yaml:/app/config.yaml:ro
```

Then recreate the service:

```sh
docker compose up -d --build --force-recreate
```

Do not add `privileged: true` by default. Begin with no extra capability for HTTP, DNS, and TCP checks; add only what testing shows is required for enabled ICMP or traceroute probes.

## InfluxDB connectivity

The monitor does not include or manage an InfluxDB server. It sends measurements to the `global_config.influx.url` configured in `config.yaml`.

### InfluxDB running on the Docker host

On Docker Desktop, `host.docker.internal` commonly resolves to the host machine:

```yaml
global_config:
  influx:
    url: http://host.docker.internal:8086
```

On native Linux Docker, `localhost` inside the PingPilot container refers to the container itself, not the host. Use a reachable host address, connect both services to a Docker network, or add an appropriate host-gateway mapping for your environment.

### InfluxDB in another Compose stack

Connect PingPilot and InfluxDB to a shared Docker network and use the InfluxDB service name as the hostname:

```yaml
global_config:
  influx:
    url: http://influxdb:8086
```

Do not publish database credentials in images or version-controlled configuration files. Supply a local `config.yaml` outside version control or use an appropriate secrets workflow.

## IPv6

Setting `global_config.ip_version: 6` makes PingPilot use IPv6/`AAAA` resolution where supported. Docker must also have functional IPv6 networking, and the container must have a valid IPv6 route to the monitored targets and DNS resolvers.

Verify IPv6 from inside the running container before relying on IPv6 measurements:

```sh
docker compose exec ping-monitor sh
```

Then use the installed network tools to test a known IPv6 destination and resolver. IPv6 operation varies with Docker Engine, Docker Desktop, the host network, and the configured container network.
