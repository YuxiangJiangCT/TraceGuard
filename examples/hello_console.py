"""Hello World #0 — the most basic OTel trace, printed to the console.

No Claude, no Jaeger, no Docker. The single goal: prove we can stand up an
OpenTelemetry tracer, create one span with a few attributes, and SEE it.

This is the foundation the spike skipped over. Once you understand this,
the spike's RedactingSpanExporter (which wraps a ConsoleSpanExporter) makes
full sense.

Run with:
    uv run --python .venv-spike python examples/hello_console.py
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

# ── Step 1: build the "recording system" ───────────────────────────────
# TracerProvider is the factory that hands out tracers (pens). On its own it
# records nothing useful — we must tell it WHERE finished spans should go.
provider = TracerProvider()

# ConsoleSpanExporter is the "courier" (快递员): its way of delivering a span
# is to print it to the terminal. SimpleSpanProcessor is the belt that hands
# each finished span straight to that courier (no batching, good for demos).
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

# Register our provider as the global one so trace.get_tracer() uses it.
trace.set_tracer_provider(provider)

# ── Step 2: get a "pen" (tracer) ────────────────────────────────────────
tracer = trace.get_tracer("spanredact.hello")

# ── Step 3: draw one span ───────────────────────────────────────────────
# start_as_current_span opens a span; leaving the `with` block ends it,
# which triggers the processor -> exporter -> console print.
with tracer.start_as_current_span("hello-span") as span:
    span.set_attribute("greeting", "hello world")
    span.set_attribute("gen_ai.prompt", "my email is a@b.com")  # planted PII
    # (do some "work" here in a real program)

# Flush anything pending and shut down cleanly.
provider.shutdown()
