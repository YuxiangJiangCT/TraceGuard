"""Hello World #2 — REAL OpenLLMetry + Anthropic.

The goal here is NOT to write spans ourselves. It's to let OpenLLMetry
auto-instrument a real Claude call and then inspect Jaeger to discover the
ACTUAL attribute keys it uses for prompt/completion content. Every key in our
earlier spike/hello files (gen_ai.prompt, etc.) was a hand-typed guess — this
is where we replace guesses with ground truth.

Prerequisites:
    1. .env contains a real ANTHROPIC_API_KEY (gitignored).
    2. Jaeger running: docker compose -f examples/docker-compose.yml up -d
    3. Run: uv run --python .venv-spike python examples/hello_openllmetry.py
    4. Inspect: http://localhost:16686  (service: "spanredact-openllmetry-demo")
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env into the process environment BEFORE anything reads env vars.
# Resolve the path relative to the PROJECT ROOT (this file's parent's parent),
# not the current working directory — `uv run` and other launchers may set a
# cwd you don't expect, and a bare load_dotenv() would then silently find
# nothing. Always anchor .env to a known path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# override=True is REQUIRED here: some shells export ANTHROPIC_API_KEY as an
# empty string "", and `uv run` carries that empty value into the subprocess.
# load_dotenv defaults to override=False, which treats "" as "already set" and
# refuses to replace it — so the real key in .env would be silently ignored.
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

from anthropic import Anthropic
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from traceloop.sdk import Traceloop

# Start OpenLLMetry. By passing our OWN exporter pointed at local Jaeger, we
# bypass Traceloop's hosted backend entirely (so the default api_endpoint is
# never actually used). disable_batch=True flushes each span immediately.
Traceloop.init(
    app_name="spanredact-openllmetry-demo",
    exporter=OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True),
    disable_batch=True,
)

# Read the key explicitly and pass it in, rather than relying on Anthropic()
# picking it up from the environment (which proved fragile under `uv run` —
# see the override=True note above).
_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not _API_KEY:
    raise SystemExit(
        "ANTHROPIC_API_KEY is empty. Put it in .env at the project root."
    )

# We do NOT create any span by hand. The instrumentation wraps this call and
# emits the span (with whatever attribute keys OpenLLMetry actually uses).
client = Anthropic(api_key=_API_KEY)

response = client.messages.create(
    model="claude-haiku-4-5-20251001",  # cheapest available model (~fractions of a cent)
    max_tokens=64,
    messages=[
        {"role": "user", "content": "Say hello in exactly 3 words."},
    ],
)

print("Claude said:", response.content[0].text)
print()
print("Span sent to Jaeger. Open http://localhost:16686")
print("Service: spanredact-openllmetry-demo")
print("Then we'll inspect WHICH attribute key holds the prompt/completion.")
