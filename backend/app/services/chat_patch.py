"""Parsing for the chat edit mode's sentinel-delimited patch block.

The model is instructed to end its reply with a fixed sentinel line
followed by a raw JSON object describing a proposed edit (or nothing, if it
has no edit to propose this turn). Two concerns this module exists for:

1. After the full reply has streamed in, split it into the conversational
   text and the optional patch (`split_reply_and_patch`) - never raising on
   malformed input, since a bad patch should degrade to "no patch
   proposed," not break the turn.
2. While the reply is still streaming, decide how much of the buffer so far
   is safe to forward to the client as visible text (`safe_emit_length`),
   so a sentinel split across two provider chunks is never partially
   leaked into the chat bubble.
"""

from __future__ import annotations

import json
from typing import Any

PATCH_SENTINEL = "\n%%%PATCH_JSON%%%\n"


def split_reply_and_patch(raw_text: str) -> tuple[str, dict[str, Any] | None]:
    """Split a full reply into (conversational_text, patch_or_none)."""
    if PATCH_SENTINEL not in raw_text:
        return raw_text, None

    reply, _, patch_text = raw_text.partition(PATCH_SENTINEL)
    patch_text = patch_text.strip()
    if not patch_text:
        return reply, None

    try:
        patch = json.loads(patch_text)
    except (json.JSONDecodeError, TypeError):
        return reply, None

    if not isinstance(patch, dict):
        return reply, None

    return reply, patch


def safe_emit_length(buffer: str) -> int:
    """How many leading characters of `buffer` can be safely forwarded as
    reply text right now. A pure function of the buffer's current
    content - callers can call it repeatedly as more text arrives without
    tracking any state of their own.

    If the sentinel has fully arrived, everything from its start onward is
    withheld (whatever follows it is patch content, not reply text, no
    matter how much more accumulates after it). Otherwise, any trailing
    suffix that could be the start of an in-progress sentinel match is
    withheld too, so a sentinel split across two provider chunks is never
    partially leaked before the rest of it arrives."""
    sentinel_pos = buffer.find(PATCH_SENTINEL)
    if sentinel_pos != -1:
        return sentinel_pos

    max_suffix = min(len(PATCH_SENTINEL) - 1, len(buffer))
    for length in range(max_suffix, 0, -1):
        if PATCH_SENTINEL.startswith(buffer[-length:]):
            return len(buffer) - length
    return len(buffer)
