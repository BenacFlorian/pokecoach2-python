"""Tests for JSONL engine protocol parsing."""

from __future__ import annotations

import pytest

from pokecoach_python.engine.protocol import (
    PROTOCOL_VERSION,
    encode_request,
    encode_response_error,
    encode_response_ok,
    parse_request_line,
    parse_response_line,
)


def test_encode_parse_request_roundtrip():
    line = encode_request(request_id="abc", mode="hello", payload={})
    data = parse_request_line(line)
    assert data["requestId"] == "abc"
    assert data["mode"] == "hello"
    assert data["protocolVersion"] == PROTOCOL_VERSION


def test_response_request_id_mismatch():
    line = encode_response_ok(request_id="one", result={})
    with pytest.raises(ValueError, match="requestId mismatch"):
        parse_response_line(line, expected_request_id="two")


def test_error_response_shape():
    line = encode_response_error(request_id="x", code="FAIL", message="nope")
    data = parse_response_line(line, expected_request_id="x")
    assert data["ok"] is False
    assert data["error"]["code"] == "FAIL"
