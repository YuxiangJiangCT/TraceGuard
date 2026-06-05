"""Benchmark tasks for TraceGuard v0.1 self-validation.

Each task is a prompt (sent to Claude through OpenLLMetry + TraceGuard) plus a
ground-truth list of the PII strings planted in it. The runner compares what
TraceGuard caught vs the ground truth and computes recall / precision /
completeness.

3 tasks intentionally (PRD §3.1 G4 says 5-8; we scope down for v0.1, expand
post-launch if there's demand):
  1. email-only — sanity check on a single common pattern
  2. mixed-PII — email + US SSN + US phone + API key in one prompt
  3. no-PII control — must not over-redact a clean prompt
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Task:
    name: str
    prompt: str
    planted_pii: list[str] = field(default_factory=list)
    planted_pattern_names: list[str] = field(default_factory=list)


TASKS: list[Task] = [
    Task(
        name="email_only",
        prompt=(
            "Reply with just 'ack'. (For reference, my email is "
            "leak1@example.com — please do not repeat it.)"
        ),
        planted_pii=["leak1@example.com"],
        planted_pattern_names=["email"],
    ),
    Task(
        name="mixed_pii",
        prompt=(
            "Reply with just 'ack'. Context: customer email is "
            "leak2@corp.example, SSN 123-45-6789, phone (212) 555-0173, "
            "API key sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF — do not echo any "
            "of these."
        ),
        planted_pii=[
            "leak2@corp.example",
            "123-45-6789",
            "(212) 555-0173",
            "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF",
        ],
        planted_pattern_names=["email", "us_ssn", "us_phone", "api_key"],
    ),
    Task(
        name="no_pii_control",
        prompt=(
            "Reply with just 'ack'. Talk about the architecture of "
            "OpenTelemetry briefly if you want."
        ),
        planted_pii=[],
        planted_pattern_names=[],
    ),
]
