#!/usr/bin/env python3
"""MCP stdio bridge — translates MCP JSON-RPC (stdio) to FlowDev REST API calls.

Claude Code spawns this script as a subprocess. It reads JSON-RPC requests
from stdin, forwards tool calls to the FlowDev backend via HTTP, and writes
JSON-RPC responses to stdout.

Register with Claude Code CLI:
    claude mcp add flowdev -s user \\
        -e FLOWDEV_BACKEND_URL=http://localhost:8000 \\
        -e FLOWDEV_MCP_TOKEN_FILE=~/.flowdev/mcp_token \\
        -- python /path/to/stdio_bridge.py

Environment variables:
    FLOWDEV_BACKEND_URL: Backend base URL (e.g. http://localhost:8000)
    FLOWDEV_MCP_TOKEN: Bearer token for MCP authentication (direct)
    FLOWDEV_MCP_TOKEN_FILE: Path to file containing the token (preferred, refreshable)
    FLOWDEV_MCP_TOOLS: Comma-separated tool names to expose (optional, all if empty)
"""

import json
import os
import sys
import urllib.request

BACKEND_URL = os.environ.get("FLOWDEV_BACKEND_URL", "http://localhost:8000")
MCP_TOOLS_FILTER = os.environ.get("FLOWDEV_MCP_TOOLS", "")


def _get_token() -> str:
    """Read MCP token from file (preferred) or env var.

    Token file is re-read on every call so the scan pipeline can
    refresh it without re-registering the MCP server.
    """
    token_file = os.environ.get("FLOWDEV_MCP_TOKEN_FILE", "")
    if token_file:
        expanded = os.path.expanduser(token_file)
        if os.path.isfile(expanded):
            with open(expanded) as f:
                return f.read().strip()
    return os.environ.get("FLOWDEV_MCP_TOKEN", "")


def _api_request(method: str, path: str, body: dict | None = None) -> dict:
    """Make an HTTP request to the FlowDev backend."""
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _get_tools() -> list[dict]:
    """Fetch tool definitions from the FlowDev backend."""
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
    """Execute a tool call via the FlowDev backend."""
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
                        "serverInfo": {"name": "flowdev-mcp", "version": "1.0.0"},
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
