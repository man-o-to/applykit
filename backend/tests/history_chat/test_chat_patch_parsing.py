from app.services.chat_patch import PATCH_SENTINEL, safe_emit_length, split_reply_and_patch


def test_split_returns_the_whole_text_as_reply_when_no_sentinel_present():
    reply, patch = split_reply_and_patch("Sure, here's my suggestion.")
    assert reply == "Sure, here's my suggestion."
    assert patch is None


def test_split_separates_reply_text_from_a_valid_patch():
    raw = (
        "I'll make the summary more concise."
        + PATCH_SENTINEL
        + '{"target": {"section": "summary"}, "new_value": "Shorter summary."}'
    )
    reply, patch = split_reply_and_patch(raw)
    assert reply == "I'll make the summary more concise."
    assert patch == {"target": {"section": "summary"}, "new_value": "Shorter summary."}


def test_split_falls_back_to_no_patch_on_malformed_json():
    raw = "Here's an idea." + PATCH_SENTINEL + "{not valid json"
    reply, patch = split_reply_and_patch(raw)
    assert reply == "Here's an idea."
    assert patch is None


def test_split_falls_back_to_no_patch_when_patch_block_is_empty():
    raw = "Just chatting, no edit this turn." + PATCH_SENTINEL + "   "
    reply, patch = split_reply_and_patch(raw)
    assert reply == "Just chatting, no edit this turn."
    assert patch is None


def test_split_falls_back_to_no_patch_when_json_is_not_an_object():
    raw = "Odd response." + PATCH_SENTINEL + '["not", "an", "object"]'
    reply, patch = split_reply_and_patch(raw)
    assert reply == "Odd response."
    assert patch is None


def test_split_handles_a_sentinel_reassembled_from_multiple_chunks():
    """Simulates what the streaming route does: accumulate raw provider
    chunks (which may split the sentinel anywhere) into one buffer, then
    parse the complete buffer once streaming finishes."""
    chunks = ["I'll tighten", " this up.\n%%%PAT", "CH_JSON%%%\n", '{"new_value": "x"}']
    raw_text = "".join(chunks)
    reply, patch = split_reply_and_patch(raw_text)
    assert reply == "I'll tighten this up."
    assert patch == {"new_value": "x"}


# --- safe_emit_length: incremental streaming safety ---


def test_safe_emit_length_allows_the_full_buffer_when_no_partial_sentinel_match():
    assert safe_emit_length("Just some plain reply text") == len("Just some plain reply text")


def test_safe_emit_length_withholds_a_suffix_that_could_start_the_sentinel():
    buffer = "Here is my answer.\n%%%PATCH_"
    safe_len = safe_emit_length(buffer)
    # Nothing withheld should itself be a prefix of the sentinel once more text arrives.
    withheld = buffer[safe_len:]
    assert PATCH_SENTINEL.startswith(withheld)
    assert withheld != ""


def test_safe_emit_length_withholds_only_a_single_newline_when_that_could_start_the_sentinel():
    buffer = "reply text\n"
    safe_len = safe_emit_length(buffer)
    assert buffer[safe_len:] == "\n"


def test_safe_emit_length_full_sentinel_present_still_reports_a_safe_prefix_before_it():
    buffer = "reply" + PATCH_SENTINEL
    safe_len = safe_emit_length(buffer)
    assert buffer[:safe_len] == "reply"


def test_incremental_emission_never_leaks_sentinel_text_across_arbitrary_chunk_splits():
    """Feed the sentinel to safe_emit_length one character at a time (the
    worst-case chunk boundary) and confirm the raw sentinel substring is
    never included in what's reported safe to emit until it's truly gone -
    i.e. replaced by patch content, handled by the caller switching modes."""
    raw = "leading reply" + PATCH_SENTINEL
    buffer = ""
    emitted = ""
    for ch in raw:
        buffer += ch
        safe_len = safe_emit_length(buffer)
        newly_safe = buffer[len(emitted) : safe_len] if safe_len > len(emitted) else ""
        emitted += newly_safe
        assert PATCH_SENTINEL not in emitted
    # Once the full sentinel has arrived, everything before it must have
    # been emitted eventually.
    assert emitted == "leading reply"
