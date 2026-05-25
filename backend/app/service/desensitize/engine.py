from __future__ import annotations

import re

from service.desensitize.errors import DesensitizeError
from service.desensitize.patterns import DESENSITIZE_PATTERNS


def desensitize_text(text: str) -> str:
    if not isinstance(text, str):
        raise DesensitizeError("desensitize_text requires a string input.")
    output = text
    try:
        for pattern in DESENSITIZE_PATTERNS:
            output = pattern.regex.sub(pattern.replacement, output)
    except re.error as exc:
        raise DesensitizeError(f"invalid desensitize regex: {exc}") from exc
    return output
