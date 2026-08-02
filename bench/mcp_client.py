"""Minimal MCP stdio client — no external SDK.

MCP stdio transport (FastMCP 3.x) = one JSON-RPC 2.0 message per line.
Spawns the memo server as a subprocess and talks to it over pipes.
"""

import json
import os
import select
import subprocess


class MCPClient:
    def __init__(self, python: str, workdir: str, env_extra: dict | None = None):
        self._python, self._workdir = python, workdir
        env = dict(os.environ)
        env.update(env_extra or {})
        self._env = env
        self.proc = subprocess.Popen(
            [python, "-u", "-c", "from memo.server import main; main()"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, cwd=workdir,
        )
        self._id = 1
        self._initialize()

    def respawn(self) -> None:
        """Kill and restart the server (same object, fresh process)."""
        try:
            self.proc.kill()
        except ProcessLookupError:
            pass
        self.proc = subprocess.Popen(
            [self._python, "-u", "-c", "from memo.server import main; main()"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=self._env, cwd=self._workdir,
        )
        self._id = 1
        self._initialize()

    def _send(self, obj: dict) -> None:
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        self.proc.stdin.flush()

    def _recv(self, timeout: float) -> dict:
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError(f"no response in {timeout:.0f}s")
        line = self.proc.stdout.readline()
        if not line:
            raise EOFError("server closed")
        return json.loads(line)

    def _initialize(self) -> None:
        self._send({"jsonrpc": "2.0", "id": self._id, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "bench", "version": "1.0"}}})
        self._id += 1
        init = self._recv(60)
        if "error" in init:
            raise RuntimeError(f"initialize failed: {init['error']}")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, name: str, arguments: dict, timeout: float = 40.0):
        self._send({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}})
        self._id += 1
        while True:
            msg = self._recv(timeout)
            if "id" not in msg:
                continue  # server notification (logging), not our response
            if "error" in msg:
                raise RuntimeError(f"{name}: {msg['error']}")
            res = msg.get("result", {})
            if res.get("isError"):
                raise RuntimeError(f"{name} isError: {json.dumps(res.get('content'))[:200]}")
            sc = res.get("structuredContent")  # FastMCP 3.x: parsed args -> return value
            if isinstance(sc, dict) and "result" in sc:
                return sc["result"]
            text = next((c["text"] for c in res.get("content", [])
                         if c.get("type") == "text"), None)
            if text is None:
                return None
            return json.loads(text)  # text = JSON string of the return value

    def close(self) -> None:
        try:
            self.proc.kill()
        except ProcessLookupError:
            pass
