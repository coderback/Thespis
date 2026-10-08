"""OpenTelemetry traces: a span for each /v1 request, each session call, each line's model call through the Mind,
each model call through the gateway, and each claim check, so one trace shows where a slow line spent its time.

The core uses only OpenTelemetry's API, which does nothing until an SDK is configured; without the API installed it
does nothing at all. `thespis serve` configures the SDK when OTEL_EXPORTER_OTLP_ENDPOINT is set and the
`thespis[otel]` extra is installed, and exports over OTLP/HTTP to that endpoint (the standard OTEL_* variables
apply). A line's model call runs after the request that asked for it has answered: its span still joins the
request's trace, because the session carries the context across.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

log = logging.getLogger("thespis.tracing")

try:
    from opentelemetry import trace as _trace
except ImportError:  # pragma: no cover - the API comes with the serve extra's FastAPI
    _trace = None


class _NoSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: Mapping[str, Any]) -> None:
        pass


NO_SPAN = _NoSpan()


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """A span named `name` around the block, with the attributes that aren't None. Yields it, to add more."""
    if _trace is None:
        yield NO_SPAN
        return
    tracer = _trace.get_tracer("thespis")
    with tracer.start_as_current_span(name, attributes={k: v for k, v in attributes.items() if v is not None}) as s:
        yield s


def configure(service: str = "thespis", env: Mapping[str, str] | None = None) -> bool:
    """Export traces over OTLP/HTTP when OTEL_EXPORTER_OTLP_ENDPOINT is set. True if it was set up."""
    env = os.environ if env is None else env
    if not env.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning("OTEL_EXPORTER_OTLP_ENDPOINT is set but the thespis[otel] extra isn't installed: no traces")
        return False
    assert _trace is not None
    provider = TracerProvider(resource=Resource.create({"service.name": env.get("OTEL_SERVICE_NAME", service)}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    _trace.set_tracer_provider(provider)
    return True
