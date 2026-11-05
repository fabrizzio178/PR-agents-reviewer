"""Strip likely secrets from job logs before they leave for the model provider.

GitLab already masks masked variables in job logs; this is the second layer for
everything else a script might print (a token in a URL, a password in an error).
It errs on the side of redacting too much: the logs are evidence, not data.
"""

from __future__ import annotations

import re

_REDACTED = "[REDACTED]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Private key blocks.
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        _REDACTED,
    ),
    # Provider-specific token formats.
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), _REDACTED),
    (re.compile(r"\bglpat-[0-9A-Za-z_-]{20,}"), _REDACTED),
    (re.compile(r"\bgh[pousr]_[0-9A-Za-z]{30,}"), _REDACTED),
    (re.compile(r"\bgithub_pat_[0-9A-Za-z_]{30,}"), _REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), _REDACTED),
    (re.compile(r"\bdckr_pat_[0-9A-Za-z_-]{20,}"), _REDACTED),
    (re.compile(r"\bsk-[0-9A-Za-z_-]{20,}"), _REDACTED),
    # JSON Web Tokens.
    (re.compile(r"\beyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}"), _REDACTED),
    # Credentials inside URLs: scheme://user:password@host
    (re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"), _REDACTED),
    # Authorization headers.
    (re.compile(r"(?i)(\b(?:bearer|basic)\s+)[0-9A-Za-z._~+/=-]{8,}"), r"\1" + _REDACTED),
    # key=value or key: value where the key names a secret.
    (
        re.compile(
            r"(?i)\b([\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)"
            r"[\w.-]*\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
        ),
        r"\1" + _REDACTED,
    ),
]


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
