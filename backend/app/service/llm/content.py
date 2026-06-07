from __future__ import annotations

import json
from typing import TypeAlias

UserPromptContent: TypeAlias = str | list[dict[str, object]]


def serialize_user_prompt(user_prompt: UserPromptContent) -> str:
    if isinstance(user_prompt, str):
        return user_prompt
    return json.dumps(user_prompt, ensure_ascii=False, sort_keys=True)


def user_prompt_trace_text(user_prompt: UserPromptContent) -> str:
    if isinstance(user_prompt, str):
        return user_prompt
    return serialize_user_prompt(user_prompt)
