"""Hello World #1 — same span, but sent to Jaeger instead of the console.

The ONLY change from hello_console.py is the courier (exporter):
    ConsoleSpanExporter()  ->  OTLPSpanExporter(endpoint="http://localhost:4317")

Everything else — the TracerProvider, the processor, the pen, the span — is
identical. That is the whole point: swapping where spans go is a one-line
change.

Prerequisites:
    1. Jaeger running:  docker compose -f examples/docker-compose.yml up -d
    2. Then run:        uv run --python .venv-spike python examples/hello_jaeger.py
    3. Open the UI:     http://localhost:16686  (service: "spanredact-hello")

What you'll see: a trace whose span carries gen_ai.prompt = "my email is
a@b.com" — IN PLAIN TEXT, on a web page anyone on the team could open. That
is the compliance problem SpanRedact exists to fix.
"""

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

# The new courier: sends spans over the network using OTLP, instead of
# printing them. By default it targets http://localhost:4317 (OTLP gRPC) —
# exactly the port we opened on the Jaeger container.
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# A Resource labels WHICH service these spans belong to. Without it Jaeger
# files everything under "unknown_service". We name ours so it's findable in
# the UI's service dropdown.
resource = Resource.create({"service.name": "spanredact-hello"})

provider = TracerProvider(resource=resource)

# Same processor as before, but wrapping the OTLP courier this time.
provider.add_span_processor(
    SimpleSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True))
)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("spanredact.hello")

with tracer.start_as_current_span("hello-span") as span:
    span.set_attribute("greeting", "hello world")
    span.set_attribute("gen_ai.prompt", "my email is a@b.com")  # planted PII

# Flush the span out to Jaeger before exiting.
provider.shutdown()

print("Sent 1 span to Jaeger. Open http://localhost:16686")
print("Service: spanredact-hello  ->  find the 'hello-span' trace")
