from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Sensitivity


_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("government_id", re.compile(r"\b(?:ssn|social security|passport|driver'?s license|tax file number)\b", re.I)),
    ("financial", re.compile(r"\b(?:bank account|credit card|card number|routing number|iban|swift)\b", re.I)),
    ("credential", re.compile(r"\b(?:password|passcode|api key|secret token|private key|recovery phrase)\b", re.I)),
    ("health", re.compile(r"\b(?:diagnosed|diagnosis|medication|therapy|therapist|psychiatrist|medical)\b", re.I)),
    ("legal", re.compile(r"\b(?:lawsuit|criminal record|restraining order|attorney|lawyer)\b", re.I)),
    (
        "precise_address",
        re.compile(
            r"\b\d{1,6}\s+[\w .'-]{2,60}\b(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|court|ct|place|pl|way|boulevard|blvd)\b|"
            r"\b(?:home address|residential address)\b|"
            r"(?:家庭住址|详细地址|门牌号|住址|我住在[^。！？\n]{0,40}\d{1,6}[^。！？\n]{0,40}(?:号|室|街|路|巷|弄|st|street|road|rd|ave|avenue))",
            re.I,
        ),
    ),
)

_RESTRICTED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("raw_secret", re.compile(r"\b(?:-----BEGIN [A-Z ]+PRIVATE KEY-----|sk-[A-Za-z0-9_-]{16,})\b")),
    ("seed_phrase", re.compile(r"\b(?:seed phrase|recovery phrase)\b", re.I)),
)

_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_instructions", re.compile(r"\bignore (?:all |any |previous |prior )?(?:instructions|rules|messages)\b", re.I)),
    ("system_prompt", re.compile(r"\b(?:system prompt|developer message|hidden prompt|policy)\b", re.I)),
    ("tool_override", re.compile(r"\b(?:always|never) (?:call|use|refuse|bypass) (?:the )?(?:tool|tools|memory|policy)\b", re.I)),
    ("jailbreak", re.compile(r"\b(?:jailbreak|do anything now|DAN mode|bypass safety)\b", re.I)),
)


@dataclass(frozen=True, slots=True)
class SensitivityDecision:
    sensitivity: Sensitivity
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InjectionDecision:
    is_injection: bool
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoreSafetyDecision:
    allow_store: bool
    outcome: str
    sensitivity: Sensitivity
    injection_risk: float
    reason: str
    summary_only: bool = False
    confirmation_options: tuple[str, ...] = ()


def detect_sensitivity(content: str) -> SensitivityDecision:
    text = content or ""
    restricted = [name for name, pattern in _RESTRICTED_PATTERNS if pattern.search(text)]
    if restricted:
        return SensitivityDecision(Sensitivity.RESTRICTED, tuple(restricted))

    sensitive = [name for name, pattern in _SENSITIVE_PATTERNS if pattern.search(text)]
    if sensitive:
        return SensitivityDecision(Sensitivity.SENSITIVE, tuple(sensitive))

    return SensitivityDecision(Sensitivity.NORMAL, ())


def detect_prompt_injection(content: str) -> InjectionDecision:
    text = content or ""
    reasons = tuple(name for name, pattern in _INJECTION_PATTERNS if pattern.search(text))
    score = min(1.0, 0.35 * len(reasons))
    return InjectionDecision(bool(reasons), score, reasons)


def needs_confirmation(content: str, *, explicit_user_request: bool = False) -> bool:
    decision = detect_sensitivity(content)
    return decision.sensitivity is not Sensitivity.NORMAL and not explicit_user_request


def should_reject_for_injection(content: str) -> bool:
    return detect_prompt_injection(content).is_injection


def evaluate_store_safety(content: str, *, explicit_user_request: bool = False) -> StoreSafetyDecision:
    injection = detect_prompt_injection(content)
    sensitivity = detect_sensitivity(content)

    if injection.is_injection:
        return StoreSafetyDecision(
            allow_store=False,
            outcome="declined",
            sensitivity=sensitivity.sensitivity,
            injection_risk=injection.score,
            reason="Memory-injection risk detected; content must remain data and will not be stored.",
        )

    if sensitivity.sensitivity is not Sensitivity.NORMAL and not explicit_user_request:
        return StoreSafetyDecision(
            allow_store=False,
            outcome="needs_confirmation",
            sensitivity=sensitivity.sensitivity,
            injection_risk=injection.score,
            reason="Sensitive life information requires explicit long-term storage confirmation.",
            summary_only=True,
            confirmation_options=("do_not_store", "store_summary", "store_full"),
        )

    if sensitivity.sensitivity is not Sensitivity.NORMAL:
        raw_storage_allowed = "precise_address" in sensitivity.reasons
        return StoreSafetyDecision(
            allow_store=True,
            outcome="success",
            sensitivity=sensitivity.sensitivity,
            injection_risk=injection.score,
            reason=(
                "Explicit request allows sensitive storage; restricted content remains summary-only "
                "and precise address content may be stored verbatim with sensitive metadata."
            ),
            summary_only=not raw_storage_allowed,
        )

    return StoreSafetyDecision(
        allow_store=True,
        outcome="success",
        sensitivity=Sensitivity.NORMAL,
        injection_risk=injection.score,
        reason="No sensitive or injection risk detected.",
    )


def safe_content_for_storage(content: str, sensitivity: Sensitivity) -> str:
    if sensitivity is Sensitivity.RESTRICTED:
        return "[Restricted sensitive content omitted; summary-only storage required.]"
    if sensitivity is Sensitivity.SENSITIVE:
        lower = content.lower()
        sensitivity_decision = detect_sensitivity(content)
        if "precise_address" in sensitivity_decision.reasons:
            return content
        if any(term in lower for term in ("therapy", "medical", "medication", "diagnosed", "diagnosis")):
            return "[Sensitive health information: therapy or medical schedule stored as summary only.]"
        if any(term in lower for term in ("bank", "credit card", "routing", "iban")):
            return "[Sensitive financial information stored as summary only.]"
        return "[Sensitive life information stored as summary only.]"
    return content
