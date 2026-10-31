"""JSONL protocol v1 between PokeCoach and the VGC bridge subprocess."""

from __future__ import annotations

import json
from typing import Any, Literal

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 8 * 1024 * 1024

BridgeMode = Literal[
    "hello",
    "preflight",
    "preview",
    "first_turn",
    "full_battle",
    "shutdown",
]


def encode_request(
    *,
    request_id: str,
    mode: BridgeMode,
    payload: dict[str, Any],
) -> str:
    body = {
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "mode": mode,
        "payload": payload,
    }
    line = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    if len(line.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("request exceeds maximum message size")
    return line + "\n"


def parse_request_line(line: str) -> dict[str, Any]:
    raw = line.strip()
    if not raw:
        raise ValueError("empty request line")
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("request exceeds maximum message size")
    data = json.loads(raw)
    if data.get("protocolVersion") != PROTOCOL_VERSION:
        raise ValueError("unsupported protocol version")
    if not isinstance(data.get("requestId"), str) or not data["requestId"]:
        raise ValueError("requestId required")
    mode = data.get("mode")
    if mode not in (
        "hello",
        "preflight",
        "preview",
        "first_turn",
        "full_battle",
        "shutdown",
    ):
        raise ValueError("invalid mode")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return data


def encode_response_ok(*, request_id: str, result: dict[str, Any]) -> str:
    body = {
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": True,
        "result": result,
    }
    line = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    if len(line.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("response exceeds maximum message size")
    return line + "\n"


def encode_response_error(*, request_id: str, code: str, message: str) -> str:
    body = {
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": False,
        "error": {"code": code, "message": message},
    }
    line = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    return line + "\n"


def parse_response_line(line: str, *, expected_request_id: str) -> dict[str, Any]:
    raw = line.strip()
    if not raw:
        raise ValueError("empty response line")
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("response exceeds maximum message size")
    data = json.loads(raw)
    if data.get("protocolVersion") != PROTOCOL_VERSION:
        raise ValueError("unsupported protocol version")
    if data.get("requestId") != expected_request_id:
        raise ValueError("response requestId mismatch")
    return data
