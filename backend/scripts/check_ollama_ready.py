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

"""Check whether a machine can run bodhiorchard's Ollama provider.

Run this BEFORE deploying the Ollama provider to a restricted machine. It is
deliberately self-contained — standard library only, no venv, no pip install,
no bodhiorchard imports, one file — because the machines this targets often
block all of those. Copy it over, run it, send back the output.

    python3 check_ollama_ready.py [--base-url URL] [--model NAME]

Two checks are gates: at least one model advertising the ``tools`` capability,
and a live tool call. Every agent feature is driven through tool calls, so
without them the integration cannot work. Exits 0 only when both gates pass.
"""

# Keeps ``X | None`` annotations lazy so this imports on Python 3.7+. Anything
# evaluated at RUNTIME must still use the oldest supported syntax — this import
# does not make PEP 585 subscripts (``dict[str, Any]``) safe outside an
# annotation; those need 3.9+. Verified against a real 3.8 interpreter.
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Annotation-only alias. Defining it at runtime would break Python 3.8,
    # where builtins are not subscriptable.
    Json = dict[str, Any]

TIMEOUT_S = 600  # CPU-only inference on a cold model is genuinely this slow.

# Provokes a LONG answer. Latency tracks output tokens, so a trivial prompt
# would report a flattering number that says nothing about the slow path.
PROSE_PROMPT = "Who invented computing?"
TOOL_PROMPT = "List the features in repo 'bodhi'. Use the tool."
JSON_PROMPT = 'Return JSON only: {"optimistic":2,"likely":5,"pessimistic":9}'
PULL_HINT = "Install a tool-capable model: `ollama pull qwen3`."
TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_features",
            "description": "List features in a repository",
            "parameters": {
                "type": "object",
                "properties": {"repo": {"type": "string", "description": "repo name"}},
                "required": ["repo"],
            },
        },
    }
]

# A variable annotation, so PEP 563 keeps it unevaluated — safe on 3.8.
results: list[tuple[bool, str]] = []


def say(line: str = "") -> None:
    """Print immediately.

    Output is block-buffered when redirected (``> out.txt``), which is how this
    gets sent back to us. Without flushing, a multi-minute run shows nothing and
    reads as a hang — and a Ctrl-C would discard the buffer entirely.
    """
    print(line, flush=True)


def record(ok: bool, label: str, detail: str, remedy: str = "") -> bool:
    """Print one check line, remember it for the summary, return ``ok``."""
    say(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    if not ok and remedy:
        say(f"         -> {remedy}")
    results.append((ok, label))
    return ok


def call(base: str, path: str, payload: Json | None = None) -> tuple[Json | None, float, str]:
    """Return (json, elapsed_seconds, error). Never raises."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.load(resp)
            return (body if isinstance(body, dict) else None), time.time() - start, ""
    except urllib.error.HTTPError as exc:
        return None, time.time() - start, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, time.time() - start, f"cannot connect ({exc.reason})"
    except (OSError, ValueError) as exc:
        # OSError covers socket/timeout failures; ValueError covers JSON decode.
        return None, time.time() - start, f"{type(exc).__name__}: {exc}"


def chat(base: str, model: str, content: str, **extra: Any) -> tuple[Json | None, float, str]:
    """POST /api/chat with one user message; ``extra`` adds top-level keys."""
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [{"role": "user", "content": content}],
    }
    body.update(extra)
    out, secs, err = call(base, "/api/chat", body)
    msg = out.get("message") if out else None
    return (msg if isinstance(msg, dict) else None), secs, err


def bad_model_remedy(model: str, err: str) -> str:
    """Remedy for a chat call that failed outright.

    A model that cannot do tools makes Ollama reject the request (HTTP 400)
    rather than reply in text. Saying "retry" there is a dead end for a
    non-developer, so name the real cause.
    """
    if "400" in err:
        return f"{model} rejected the request — it likely cannot do this. {PULL_HINT}"
    return "Check that Ollama is still running, then retry."


def check_reachable(base: str) -> bool:
    out, _, err = call(base, "/api/version")
    if out is None:
        return record(False, "Ollama reachable", err, "Start Ollama; it must listen on " + base)
    version = out.get("version", "?")
    return record(True, "Ollama reachable", f"version {version}")


def check_models(base: str) -> list[str]:
    out, _, err = call(base, "/api/tags")
    if out is None:
        record(False, "Models installed", err, "Check the Ollama service is running.")
        return []
    names = [m.get("name", "") for m in out.get("models", []) if m.get("name")]
    if not names:
        record(False, "Models installed", "none", PULL_HINT)
        return []
    shown = ", ".join(names[:5])
    record(True, "Models installed", f"{len(names)} ({shown})")
    return names


def check_tool_models(base: str, names: list[str]) -> list[str]:
    """GATE: which installed models advertise the `tools` capability.

    Distinguishes "no model reports tools" from "this Ollama is too old to
    report capabilities at all" — the latter would otherwise fail every model
    and send the user to reinstall a model they already have.
    """
    capable = []
    any_reported = False
    for name in names:
        out, _, _ = call(base, "/api/show", {"model": name})
        caps = (out or {}).get("capabilities")
        if caps:
            any_reported = True
            if "tools" in caps:
                capable.append(name)
    if capable:
        record(True, "Tool-capable models [GATE]", ", ".join(capable))
        return capable
    if not any_reported:
        record(
            False,
            "Tool-capable models [GATE]",
            "this Ollama does not report model capabilities",
            "Your Ollama is too old to advertise tool support. Upgrade Ollama "
            "(https://ollama.com) and re-run this check.",
        )
    else:
        record(
            False,
            "Tool-capable models [GATE]",
            "none of the installed models support tools",
            PULL_HINT + " Models without `tools` cannot run bodhiorchard agents.",
        )
    return []


def check_json_mode(base: str, model: str) -> bool:
    msg, secs, err = chat(base, model, JSON_PROMPT, format="json")
    if msg is None:
        return record(False, "JSON mode", err or "no response", bad_model_remedy(model, err))
    try:
        json.loads(msg.get("content") or "")
    except (ValueError, TypeError):
        return record(
            False,
            "JSON mode",
            "model did not return valid JSON",
            "Estimation and attribution need strict JSON. Try a different model.",
        )
    return record(True, "JSON mode", f"valid JSON in {secs:.1f}s")


def check_tool_call(base: str, model: str) -> bool:
    """GATE: a real tool call, not hallucinated tool-call text."""
    msg, secs, err = chat(base, model, TOOL_PROMPT, tools=TOOL_SCHEMA)
    if msg is None:
        return record(
            False, "Tool calling [GATE]", err or "no response", bad_model_remedy(model, err)
        )
    calls = msg.get("tool_calls") or []
    if not calls:
        return record(
            False,
            "Tool calling [GATE]",
            "model replied with text instead of calling the tool",
            f"{model} cannot drive bodhiorchard agents. {PULL_HINT}",
        )
    first = calls[0]
    if not isinstance(first, dict):
        # Never trust the shape: a false PASS here green-lights the whole
        # project on bad evidence.
        return record(
            False,
            "Tool calling [GATE]",
            "malformed tool_calls in response",
            f"{model} returned a tool call we cannot parse. {PULL_HINT}",
        )
    name = first.get("function", {}).get("name", "?")
    return record(True, "Tool calling [GATE]", f"called {name}() in {secs:.1f}s")


def measure_latency(base: str, model: str) -> None:
    """Time the shapes that decide timeouts and whether the UX is usable."""
    say(f'\nLatency — prose prompt "{PROSE_PROMPT}" can take minutes on CPU. Please wait.')
    rows = []
    for label, think in (("prose, thinking ON", True), ("prose, thinking OFF", False)):
        payload = {"model": model, "stream": False, "think": think, "prompt": PROSE_PROMPT}
        out, secs, err = call(base, "/api/generate", payload)
        rows.append((label, secs, (out or {}).get("eval_count") or 0, err))
    msg, secs, err = chat(base, model, TOOL_PROMPT, tools=TOOL_SCHEMA)
    rows.append(("tool call", secs, 0, err))

    say("\n  {:<22} {:>9} {:>11}".format("shape", "seconds", "out tokens"))
    for label, secs, tokens, err in rows:
        detail = "  failed: " + err if err else f"{secs:9.1f} {tokens:11}"
        say(f"  {label:<22}{detail}")
    say(
        "\n  Latency tracks OUTPUT TOKENS, not the endpoint. Tool calls emit only a"
        "\n  few tokens, so they stay fast even on slow hardware. Long prose answers"
        "\n  dominate — that decides whether chat-style features are usable here,"
        "\n  and whether thinking is worth its cost."
    )


def resolve_base_url(raw: str) -> str:
    """Add a scheme if missing.

    Users pointing at another box naturally type ``10.0.0.5:11434``. urllib
    raises "unknown url type" on that, which reads as "Ollama is down" and
    sends them restarting a service that was never the problem.
    """
    if not raw.startswith(("http://", "https://")):
        return "http://" + raw
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Ollama readiness for bodhiorchard.")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--model", default="", help="Model to test (default: first tool-capable)")
    args = parser.parse_args()
    base = resolve_base_url(args.base_url)

    say(f"\nbodhiorchard Ollama readiness check -> {base}")
    # Echo the environment: if this script itself fails, its interpreter and
    # platform are the first things we need from the report.
    say(
        "  python {} on {} {} | {}\n".format(
            platform.python_version(),
            platform.system(),
            platform.machine(),
            time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    )

    if not check_reachable(base):
        say("\nRESULT: NOT READY - Ollama is not reachable.\n")
        return 1
    names = check_models(base)
    if not names:
        say("\nRESULT: NOT READY - no models installed.\n")
        return 1
    capable = check_tool_models(base, names)
    if not capable:
        say("\nRESULT: NOT READY - no tool-capable model.\n")
        return 1

    model = args.model or capable[0]
    if args.model and args.model not in capable:
        say(f"  [WARN] {args.model} is not tool-capable; testing it anyway.")
    say(f"\nTesting model: {model}\n")

    check_json_mode(base, model)
    tools_ok = check_tool_call(base, model)
    # Only worth minutes of inference if the config could actually be used.
    if tools_ok:
        measure_latency(base, model)

    failed = [label for ok, label in results if not ok]
    say("\n" + "=" * 60)
    if tools_ok and not failed:
        say(f"RESULT: READY. Use model '{model}'.")
    elif tools_ok:
        say("RESULT: USABLE with caveats. Failed: {}".format(", ".join(failed)))
    else:
        say("RESULT: NOT READY - tool calling does not work.")
    say("=" * 60)
    say("Please send everything above back to the bodhiorchard team.\n")
    return 0 if tools_ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("\nInterrupted.")
        sys.exit(1)
