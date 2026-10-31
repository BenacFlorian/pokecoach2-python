"""JSONL bridge entrypoint (stdout = protocol only)."""

from __future__ import annotations

import argparse
import sys
import traceback

from pokecoach_vgc_bridge import protocol
from pokecoach_vgc_bridge.runtime import BridgeRuntime


def main() -> int:
    parser = argparse.ArgumentParser(description="PokeCoach VGC bridge")
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    runtime = BridgeRuntime(checkpoint_path=args.checkpoint, manifest_path=args.manifest)
    for line in sys.stdin:
        try:
            req = protocol.parse_request_line(line)
        except Exception as exc:
            sys.stdout.write(
                protocol.encode_response_error(
                    request_id="",
                    code="INVALID_REQUEST",
                    message=str(exc),
                )
            )
            sys.stdout.flush()
            continue
        request_id = req["requestId"]
        mode = req["mode"]
        payload = req["payload"]
        if mode == "shutdown":
            sys.stdout.write(protocol.encode_response_ok(request_id=request_id, result={}))
            sys.stdout.flush()
            return 0
        try:
            if mode == "preflight":
                result = runtime.handle("preflight", payload)
            elif mode == "preview":
                result = runtime.handle("preview", payload)
            elif mode == "first_turn":
                result = runtime.handle("first_turn", payload)
            elif mode == "full_battle":
                result = runtime.handle("full_battle", payload)
            elif mode == "hello":
                result = runtime.handle("hello", payload)
            else:
                raise ValueError(f"unsupported mode {mode}")
            sys.stdout.write(protocol.encode_response_ok(request_id=request_id, result=result))
        except Exception as exc:
            code = str(exc).split(":", 1)[0] if ":" in str(exc) else "BRIDGE_ERROR"
            sys.stdout.write(
                protocol.encode_response_error(
                    request_id=request_id,
                    code=code,
                    message=str(exc),
                )
            )
            traceback.print_exc(file=sys.stderr)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
