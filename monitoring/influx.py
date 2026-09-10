from __future__ import annotations

import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import TypeAlias

from .models import InfluxConfig, Sample, Scalar


InfluxValue: TypeAlias = Scalar


def require_http_url(url: str) -> None:
    if urllib.parse.urlparse(url).scheme not in {"http", "https"}:
        raise ValueError(f"Only http and https URLs are supported: {url}")


def escape(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(" ", "\\ ")
        .replace(",", "\\,")
        .replace("=", "\\=")
    )


def field(value: InfluxValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value}i"
    if isinstance(value, float):
        return repr(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_line_protocol(measurement: str, sample: Sample) -> str:
    tags = ",".join(
        f"{escape(key)}={escape(value)}"
        for key, value in sorted(sample.tags.items())
        if value not in {None, ""}
    )
    measurement = escape(measurement)
    head = measurement + (f",{tags}" if tags else "")
    fields = ",".join(
        f"{escape(key)}={field(value)}" for key, value in sorted(sample.fields.items())
    )
    return f"{head} {fields} {sample.timestamp_ns}"


class InfluxV1:
    def __init__(self, config: InfluxConfig) -> None:
        self.url = config.url.rstrip("/")
        self.database = config.database
        self.username = config.username
        self.password = config.password
        self.measurement = config.measurement
        self.verify_tls = config.verify_tls

    def write(self, samples: list[Sample]) -> None:
        if not samples:
            return
        payload = "\n".join(
            to_line_protocol(self.measurement, item) for item in samples
        ).encode("utf-8")
        params = {"db": self.database, "precision": "ns"}
        if self.username:
            params.update(u=self.username, p=self.password)
        endpoint = f"{self.url}/write?{urllib.parse.urlencode(params)}"
        require_http_url(endpoint)
        request = urllib.request.Request(endpoint, data=payload, method="POST")
        context = None
        if endpoint.startswith("https://") and not self.verify_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(
                request, timeout=10, context=context
            ) as response:  # nosec B310
                if response.status >= 300:
                    raise RuntimeError(f"InfluxDB returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            message = exc.read().decode(errors="replace")
            raise RuntimeError(f"InfluxDB returned HTTP {exc.code}: {message}") from exc
