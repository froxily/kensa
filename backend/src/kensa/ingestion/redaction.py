"""Secret redaction. Runs on every log before it is stored or sent to a model.

Invariant: redaction never adds or removes newlines, so line numbers (and citations) stay valid.
Pure hex strings (commit SHAs, digests) and UUIDs are deliberately kept: they are evidence.
"""

import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

Replacer = Callable[[re.Match[str]], str]


def _marker(kind: str) -> str:
    return f"[REDACTED:{kind}]"


def _keep_newlines(kind: str) -> Replacer:
    return lambda m: _marker(kind) + "\n" * m.group(0).count("\n")


def _whole(kind: str) -> Replacer:
    return lambda m: _marker(kind)


_PLACEHOLDER_VALUES = {"***", "true", "false", "null", "none", "required", "redacted"}
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _connection_password(m: re.Match[str]) -> str:
    if m.group("pw") in _PLACEHOLDER_VALUES or m.group("pw").startswith("[REDACTED"):
        return m.group(0)
    return f"{m.group('scheme')}{m.group('user')}:{_marker('password')}@"


def _key_value(m: re.Match[str]) -> str:
    value = m.group("val")
    # Keep obvious non-secrets: masked values, numbers, booleans and variable *names*
    # ("Missing secret: API_TOKEN" is evidence, not a leak).
    if (
        value.lower() in _PLACEHOLDER_VALUES
        or value.isdigit()
        or _ENV_NAME.match(value)
        or value.startswith(("${", "$", "[REDACTED"))
    ):
        return m.group(0)
    return f"{m.group('key')}{m.group('sep')}{m.group('q')}{_marker('secret')}{m.group('q')}"


_HEX = re.compile(r"^[0-9a-fA-F]+$")
# Integrity hashes and digests ("sha512-…", "sha256:…") are evidence, not secrets. The prefix can
# sit just before the candidate token or, because "-" is a token character, inside it.
_DIGEST_PREFIX = re.compile(r"(?:sha(?:1|256|384|512)[:-])$", re.IGNORECASE)
_DIGEST_TOKEN = re.compile(r"^sha(?:1|256|384|512)[:-]", re.IGNORECASE)


def _entropy(token: str) -> float:
    counts = Counter(token)
    return -sum(c / len(token) * math.log2(c / len(token)) for c in counts.values())


def _high_entropy(m: re.Match[str]) -> str:
    token = m.group(0)
    prefix = m.string[max(0, m.start() - 8) : m.start()]
    bare = token.replace("-", "")
    if (
        _HEX.match(bare)
        or _DIGEST_PREFIX.search(prefix)
        or _DIGEST_TOKEN.match(token)
        or token.count("/") >= 2
        or not (any(c.isdigit() for c in token) and any(c.isupper() for c in token))
        or not any(c.islower() for c in token)
        or _entropy(token) < 4.3
    ):
        return token
    return _marker("high_entropy")


_RULES: list[tuple[str, re.Pattern[str], Replacer]] = [
    (
        "private_key",
        re.compile(
            r"-----BEGIN ([A-Z0-9 ]*)PRIVATE KEY-----.*?-----END \1PRIVATE KEY-----", re.DOTALL
        ),
        _keep_newlines("private_key"),
    ),
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----(?:\n[A-Za-z0-9+/=]{16,})*"),
        _keep_newlines("private_key"),
    ),
    (
        "password",
        re.compile(
            r"(?P<scheme>\b[a-zA-Z][a-zA-Z0-9+.-]{1,20}://)(?P<user>[^\s:/@]{1,100}):"
            r"(?P<pw>[^\s@/]{1,200})@"
        ),
        _connection_password,
    ),
    (
        "bearer",
        re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{16,}"),
        _whole("bearer"),
    ),
    (
        "github_token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{20,255})\b"),
        _whole("github_token"),
    ),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), _whole("aws_key")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"), _whole("slack_token")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), _whole("google_api_key")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b"), _whole("stripe_key")),
    ("api_key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}\b"), _whole("api_key")),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"), _whole("npm_token")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"),
        _whole("jwt"),
    ),
    (
        "secret",
        re.compile(
            r"(?i)(?P<key>\b[A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|"
            r"access[_-]?key|private[_-]?key|credentials?)[A-Za-z0-9_.-]*)"
            r"(?P<sep>\s*[:=]\s*)(?P<q>[\"']?)(?P<val>[^\s\"'`,;]{6,})(?P=q)"
        ),
        _key_value,
    ),
    ("high_entropy", re.compile(r"[A-Za-z0-9+/=_-]{32,}"), _high_entropy),
]


@dataclass(frozen=True)
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str) -> RedactionResult:
    counts: Counter[str] = Counter()
    for kind, pattern, replacer in _RULES:

        def counting(m: re.Match[str], kind: str = kind, replacer: Replacer = replacer) -> str:
            replacement = replacer(m)
            if replacement != m.group(0):
                counts[kind] += 1
            return replacement

        text = pattern.sub(counting, text)
    return RedactionResult(text=text, counts=dict(counts))
