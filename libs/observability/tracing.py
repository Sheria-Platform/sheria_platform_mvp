# libs/observability/tracing.py
# STATUS: NOT WIRED — configure_tracing() is called in main.py but the
# ConsoleSpanExporter below only logs to stdout.  For production, replace
# ConsoleSpanExporter with OTLPSpanExporter and point it at the OTLP endpoint
# defined in config.py (OTLP_ENDPOINT setting).
#
# TODO: Switch to OTLPSpanExporter when the Jaeger/Grafana Tempo collector is
# provisioned.  See deploy/observability/ for the planned configuration.

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def configure_tracing(service_name: str):
    """Set up OpenTelemetry tracing with a console exporter.

    Currently exports spans to stdout only.  In production this should be
    replaced with an OTLP exporter targeting Jaeger or Grafana Tempo.

    Args:
        service_name: Logical name of the service (e.g. ``"sheria-api"``).

    Returns:
        A tracer instance for the given service name.
    """
    provider = TracerProvider()
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def get_current_span_id():
    """Return the current trace ID for log correlation, or None."""
    span = trace.get_current_span()
    if span:
        return span.get_span_context().trace_id
    return None
