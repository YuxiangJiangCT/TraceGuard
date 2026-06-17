"""SpanRedact end-to-end demo — real Claude call, PII redacted before Jaeger.

Same as hello_openllmetry.py, but we wrap Traceloop's exporter with
SpanRedactExporter. The prompt deliberately contains an email; after this
runs, inspect Jaeger and the email is [REDACTED] inside gen_ai.input.messages,
while token counts / model name survive.

Prereqs:
    1. .env has a real ANTHROPIC_API_KEY (gitignored)
    2. docker compose -f examples/docker-compose.yml up -d
    3. uv run --python .venv python examples/redaction_demo.py
    4. http://localhost:16686  (service: spanredact-redaction-demo)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

from anthropic import Anthropic
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from traceloop.sdk import Traceloop

from spanredact.policy.modes import Policy
from spanredact.redaction.exporter import SpanRedactExporter

# Wrap the OTLP exporter with SpanRedact redaction, then hand it to OpenLLMetry.
_downstream = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
_policy = Policy.from_str(os.getenv("SPANREDACT_POLICY"), default=Policy.BALANCED)
_guarded = SpanRedactExporter(_downstream, policy=_policy)

Traceloop.init(
    app_name="spanredact-redaction-demo",
    exporter=_guarded,
    disable_batch=True,
)

_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not _API_KEY:
    raise SystemExit("ANTHROPIC_API_KEY is empty. Put it in .env at the project root.")

client = Anthropic(api_key=_API_KEY)
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=64,
    messages=[
        {
            "role": "user",
            "content": "Reply 'ok'. (My email is leak@example.com -- do not repeat it.)",
        }
    ],
)

print("Claude said:", response.content[0].text)
print(f"Policy: {_policy.value}")
print("Sent to Jaeger -> http://localhost:16686  (service: spanredact-redaction-demo)")
print("Check gen_ai.input.messages: the email should be [REDACTED].")
