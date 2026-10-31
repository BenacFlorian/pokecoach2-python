"""Spawn and talk to the VGC bridge over JSONL stdin/stdout."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.errors import EngineBridgeError, EngineProtocolError
from pokecoach_python.engine.protocol import (
    BridgeMode,
    encode_request,
    parse_response_line,
)

logger = logging.getLogger(__name__)

_STDERR_MAX_BYTES = 64_000


class VgcSubprocessClient:
    """Persistent bridge process for sequential simulations."""

    def __init__(
        self,
        settings: Settings,
        *,
        argv: Sequence[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._proc: subprocess.Popen[str] | None = None
        self._stderr_buf: list[str] = []
        self._stderr_thread: threading.Thread | None = None
        self._argv = list(argv) if argv is not None else self._default_argv(settings)
        self._env = dict(env) if env is not None else self._default_env(settings)
        self._started = False

    @staticmethod
    def _default_argv(settings: Settings) -> list[str]:
        if settings.vgc_bridge_argv:
            return list(settings.vgc_bridge_argv)
        python = settings.resolved_vgc_bridge_python()
        manifest = settings.default_bridge_manifest_path()
        checkpoint = settings.vgc_checkpoint_path or ""
        return [
            python,
            "-m",
            "pokecoach_vgc_bridge.server",
            "--checkpoint",
            checkpoint,
            "--manifest",
            manifest,
        ]

    @staticmethod
    def _default_env(settings: Settings) -> dict[str, str]:
        env = os.environ.copy()
        env["POKECOACH_SHOWDOWN_SERVER"] = settings.showdown_server_url
        env["POKECOACH_REGULATION_MAP"] = settings.regulation_showdown_map_json()
        if os.environ.get("POKECOACH_BRIDGE_FIXTURE") == "1":
            env["POKECOACH_BRIDGE_FIXTURE"] = "1"
        if settings.vgc_checkpoint_sha256:
            env["POKECOACH_CHECKPOINT_SHA256"] = settings.vgc_checkpoint_sha256
        root = Path(__file__).resolve().parents[3]
        bridge_src = root / "engine-runtime" / "src"
        if bridge_src.is_dir():
            prev = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                f"{bridge_src}{os.pathsep}{prev}" if prev else str(bridge_src)
            )
        return env

    def _ensure_started(self) -> subprocess.Popen[str]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        if self._started and self._proc is not None:
            raise EngineBridgeError("BRIDGE_DEAD", "bridge process exited")
        self._started = True
        try:
            self._proc = subprocess.Popen(
                self._argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=self._env,
                start_new_session=True,
            )
        except OSError as exc:
            raise EngineBridgeError("BRIDGE_START_FAILED", str(exc)) from exc
        assert self._proc.stderr is not None
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(self._proc.stderr,),
            daemon=True,
        )
        self._stderr_thread.start()
        return self._proc

    def _drain_stderr(self, stream: Any) -> None:
        total = 0
        for line in stream:
            self._stderr_buf.append(line)
            total += len(line.encode("utf-8", errors="replace"))
            if total >= _STDERR_MAX_BYTES:
                self._stderr_buf.append("… stderr truncated …\n")
                break

    def request(
        self,
        mode: BridgeMode,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        proc = self._ensure_started()
        request_id = str(uuid.uuid4())
        assert proc.stdin is not None
        assert proc.stdout is not None
        try:
            proc.stdin.write(encode_request(request_id=request_id, mode=mode, payload=payload))
            proc.stdin.flush()
        except OSError as exc:
            raise EngineBridgeError("BRIDGE_WRITE_FAILED", str(exc)) from exc
        try:
            line = proc.stdout.readline()
        except OSError as exc:
            raise EngineBridgeError("BRIDGE_READ_FAILED", str(exc)) from exc
        if not line:
            code = proc.poll()
            raise EngineBridgeError(
                "BRIDGE_EOF",
                f"bridge closed stdout (exit={code})",
            )
        try:
            data = parse_response_line(line, expected_request_id=request_id)
        except (ValueError, json.JSONDecodeError) as exc:
            raise EngineProtocolError(str(exc)) from exc
        if not data.get("ok"):
            err = data.get("error") or {}
            raise EngineBridgeError(
                str(err.get("code") or "BRIDGE_ERROR"),
                str(err.get("message") or "bridge error"),
            )
        result = data.get("result")
        if not isinstance(result, dict):
            raise EngineProtocolError("result must be an object")
        return result

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None:
                try:
                    self.request("shutdown", {}, timeout_seconds=5.0)
                except EngineBridgeError:
                    pass
        finally:
            if self._proc.poll() is None:
                try:
                    os.killpg(self._proc.pid, 15)
                except ProcessLookupError:
                    pass
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self._proc.pid, 9)
                    except ProcessLookupError:
                        pass
            self._proc = None
