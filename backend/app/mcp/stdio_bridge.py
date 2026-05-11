#!/usr/bin/env python3
# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MCP stdio bridge — translates MCP JSON-RPC (stdio) to Bodhiorchard REST API calls.

Claude Code spawns this script as a subprocess. It reads JSON-RPC requests
from stdin, forwards tool calls to the Bodhiorchard backend via HTTP, and writes
JSON-RPC responses to stdout.

Register with Claude Code CLI:
    claude mcp add bodhiorchard -s user \\
        -e BODHIORCHARD_BACKEND_URL=http://localhost:8000 \\
        -e BODHIORCHARD_MCP_TOKEN_FILE=~/.bodhiorchard/mcp_token \\
        -- python /path/to/stdio_bridge.py

Environment variables:
    BODHIORCHARD_BACKEND_URL: Backend base URL (e.g. http://localhost:8000)
    BODHIORCHARD_MCP_TOKEN: Bearer token for MCP authentication (preferred, direct)
    BODHIORCHARD_MCP_TOKEN_FILE: Path to file containing the token (fallback for
        global registration)
    BODHIORCHARD_MCP_TOOLS: Comma-separated tool names to expose (optional, all if empty)
"""

import contextlib
import json
import os
import sys
import urllib.error
import urllib.request

BACKEND_URL = os.environ.get("BODHIORCHARD_BACKEND_URL", "http://localhost:8000")
MCP_TOOLS_FILTER = os.environ.get("BODHIORCHARD_MCP_TOOLS", "")


def _log(msg: str) -> None:
    """Write a diagnostic line to stderr (visible in Claude CLI logs)."""
    print(f"[bodhiorchard-bridge] {msg}", file=sys.stderr, flush=True)


def _get_token() -> str:
    """Read MCP token from env var (preferred) or file fallback.

    Direct token takes precedence because per-subprocess configs pass
    it explicitly.  File-based tokens are a fallback for global
    ``claude mcp add`` registrations where the token refreshes on disk.
    """
    direct = os.environ.get("BODHIORCHARD_MCP_TOKEN", "")
    if direct:
        _log(f"token_source=env token_prefix={direct[:8]}")
        return direct
    token_file = os.environ.get("BODHIORCHARD_MCP_TOKEN_FILE", "")
    if token_file:
        expanded = os.path.expanduser(token_file)
        if os.path.isfile(expanded):
            with open(expanded) as f:
                token = f.read().strip()
            _log(f"token_source=file path={expanded} token_prefix={token[:8]}")
            return token
        _log(f"token_source=file path={expanded} (file not found)")
    _log("token_source=none (no token available)")
    return ""


def _api_request(method: str, path: str, body: dict | None = None) -> dict:
    """Make an HTTP request to the Bodhiorchard backend.

    Returns a structured error dict on HTTP failures (e.g. 401) so that
    Claude sees a clean MCP error instead of a raw exception traceback.
    """
    url = f"{BACKEND_URL}{path}"
    data = json.dumps(body).encode() if body else None
    token = _get_token()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = ""
        with contextlib.suppress(Exception):
            detail = exc.read().decode()[:200]
        _log(f"http_error status={exc.code} url={url} detail={detail[:120]}")
        return {"error": f"Backend returned HTTP {exc.code}", "status": exc.code, "detail": detail}


def _get_tools() -> list[dict]:
    """Fetch tool definitions from the Bodhiorchard backend."""
    _log("tools/list requested")
    tools = _api_request("GET", "/mcp/tools")
    allowed = (
        {t.strip() for t in MCP_TOOLS_FILTER.split(",") if t.strip()} if MCP_TOOLS_FILTER else None
    )
    result = []
    for tool in tools:
        if allowed and tool["name"] not in allowed:
            continue
        result.append(
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["input_schema"],
            }
        )
    return result


def _call_tool(name: str, arguments: dict) -> dict:
    """Execute a tool call via the Bodhiorchard backend."""
    _log(f"tools/call name={name}")
    return _api_request("POST", f"/mcp/tools/{name}", {"params": arguments})


def _send(msg: dict) -> None:
    """Write a JSON-RPC message to stdout."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _send_result(req_id: int | str, result: dict) -> None:
    """Send a JSON-RPC success response."""
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _send_error(req_id: int | str | None, code: int, message: str) -> None:
    """Send a JSON-RPC error response."""
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def main() -> None:
    """Main loop: read JSON-RPC from stdin, dispatch, respond on stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send_error(None, -32700, "Parse error")
            continue

        req_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        try:
            if method == "initialize":
                _send_result(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "bodhiorchard-mcp", "version": "1.0.0"},
                    },
                )
            elif method == "notifications/initialized":
                # Client acknowledgment — no response needed
                pass
            elif method == "tools/list":
                tools = _get_tools()
                _send_result(req_id, {"tools": tools})
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = _call_tool(tool_name, arguments)
                _send_result(
                    req_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    },
                )
            elif method == "ping":
                _send_result(req_id, {})
            else:
                _send_error(req_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            _send_error(req_id, -32603, str(exc))


if __name__ == "__main__":
    main()
