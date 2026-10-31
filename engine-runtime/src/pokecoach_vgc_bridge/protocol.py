"""Copy of protocol v1 for the bridge subprocess (keep in sync with pokecoach_python.engine.protocol)."""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 8 * 1024 * 1024


def parse_request_line(line: str) -> dict[str, Any]:
    raw = line.strip()
    if not raw:
        raise ValueError("empty request line")
    data = json.loads(raw)
    if data.get("protocolVersion") != PROTOCOL_VERSION:
        raise ValueError("unsupported protocol version")
    if not isinstance(data.get("requestId"), str):
        raise ValueError("requestId required")
    return data


def encode_response_ok(*, request_id: str, result: dict[str, Any]) -> str:
    body = {
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": True,
        "result": result,
    }
    return json.dumps(body, separators=(",", ":")) + "\n"


def encode_response_error(*, request_id: str, code: str, message: str) -> str:
    body = {
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": False,
        "error": {"code": code, "message": message},
    }
    return json.dumps(body, separators=(",", ":")) + "\n"
