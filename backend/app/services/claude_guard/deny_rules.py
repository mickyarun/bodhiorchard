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

"""Single source of truth for Claude subprocess deny rules.

Two consumers read this module:

* ``inline_settings`` — emits the ``permissions.deny`` list inside the
  inline ``--settings`` JSON. Claude evaluates these natively via its
  prefix matcher. Fast, declarative, but bypassable via quoting / env
  indirection — treat as a usability filter, not a hard boundary.

* ``pretool_guard`` — the PreToolUse hook script. Receives the
  fully-rendered command on stdin, applies regex matchers below, and
  vetoes the call. This is the *real* gate. Regex patterns canonicalize
  ``$(...)``, backticks, ``\\xHH`` escapes, and variable expansions so
  obfuscated payloads still match.

Eight attack classes are covered, each based on a documented 2025 CVE or
public incident:

1. env exfiltration  ``printenv``, ``env``, ``cat /proc/self/environ``
2. network exfil     ``curl``, ``wget``, ``nc``, ``ping``, ``dig``, ``nslookup`` (CVE-2025-55284)
3. pipe-to-shell     ``curl x | bash``
4. DB destruction    ``DROP TABLE``, ``TRUNCATE``, ``DELETE … WHERE 1=1``
5. git destruction   ``git push --force``, ``git reset --hard origin``
6. filesystem nuke   ``rm -rf /``, ``rm -rf ~``
7. symlink plant     ``ln -s /etc /tmp/x`` (CVE-2026-39861 class)
8. package poison    ``npm install evil-pkg``, ``pip install x``
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Claude-native deny list, fed into ``permissions.deny`` in --settings JSON.
#
# Claude's prefix matcher syntax:
#   ``Bash(cmd:*)``  — any Bash command whose argv starts with ``cmd``
#   ``Read(path)``  — file reads under the given path / glob
#   ``Edit(path)``  — file writes under the given path / glob
#
# Reference: https://code.claude.com/docs/en/settings#permission-rules
# ---------------------------------------------------------------------------
INLINE_DENY_LIST: list[str] = [
    # --- Network bash (CVE-2025-55284 DNS-exfil class) ------------------
    "Bash(curl:*)",
    "Bash(wget:*)",
    "Bash(nc:*)",
    "Bash(ncat:*)",
    "Bash(socat:*)",
    "Bash(ping:*)",
    "Bash(nslookup:*)",
    "Bash(dig:*)",
    "Bash(host:*)",
    "Bash(ssh:*)",
    "Bash(scp:*)",
    "Bash(sftp:*)",
    "Bash(rsync:*)",
    "Bash(telnet:*)",
    # --- Env exfiltration -----------------------------------------------
    "Bash(env)",
    "Bash(env:*)",
    "Bash(printenv:*)",
    # --- DB destruction --------------------------------------------------
    "Bash(psql:*)",
    "Bash(pg_dump:*)",
    "Bash(pg_restore:*)",
    "Bash(redis-cli:*)",
    "Bash(mongo:*)",
    "Bash(mysql:*)",
    # --- Git destruction -------------------------------------------------
    "Bash(git push --force:*)",
    "Bash(git push -f:*)",
    "Bash(git push --force-with-lease:*)",
    "Bash(git reset --hard origin:*)",
    "Bash(git update-ref -d:*)",
    # --- Filesystem nuke -------------------------------------------------
    "Bash(rm -rf /:*)",
    "Bash(rm -rf ~:*)",
    "Bash(rm -rf $HOME:*)",
    "Bash(rm -rf ..:*)",
    "Bash(sudo:*)",
    "Bash(chmod 777:*)",
    "Bash(chown:*)",
    # --- Package poisoning -----------------------------------------------
    "Bash(npm install:*)",
    "Bash(npm i:*)",
    "Bash(pnpm add:*)",
    "Bash(yarn add:*)",
    "Bash(pip install:*)",
    "Bash(pip3 install:*)",
    "Bash(uvx:*)",
    "Bash(pipx install:*)",
    # --- Secret reads ----------------------------------------------------
    "Read(./.env)",
    "Read(./.env.*)",
    "Read(./secrets/**)",
    "Read(./credentials*)",
    "Read(./id_rsa*)",
    "Read(~/.aws/**)",
    "Read(~/.ssh/**)",
    "Read(~/.netrc)",
    "Read(~/.claude/**)",
    "Read(~/.config/gh/**)",
    "Read(~/.docker/config.json)",
    "Read(/etc/**)",
    "Read(/proc/**)",
    "Read(/sys/**)",
    # --- Engine-config writes (hook persistence — CVE-2026-25725 class) -
    "Edit(.git/**)",
    "Edit(.husky/**)",
    "Edit(.claude/settings*.json)",
    "Edit(.claude/hooks/**)",
    "Edit(.github/workflows/**)",
    # --- Blanket: no outbound HTTP fetches (lethal-trifecta class) ------
    "WebFetch",
]


# ---------------------------------------------------------------------------
# Regex matchers used by the PreToolUse hook. These are the real gate —
# they canonicalize the command first (collapse ``$()``, backticks, hex
# escapes) so obfuscated payloads still match.
#
# Each entry is (class_name, compiled_pattern). class_name is reported back
# in the deny reason for forensics.
# ---------------------------------------------------------------------------
BASH_DENY_RULES: list[tuple[str, re.Pattern[str]]] = [
    # Order matters: more specific patterns first. ``pipe_to_shell`` must
    # come before ``network_exfil`` since the latter would otherwise claim
    # ``curl x | bash`` as a generic network call and hide the more
    # dangerous fetch-and-execute pattern.
    (
        "pipe_to_shell",
        re.compile(
            r"(curl|wget|fetch)\b[^|;]*\|\s*(bash|sh|zsh|ksh|python\d?|perl|ruby|node)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "env_exfil",
        re.compile(
            r"(^|[\s;&|])(printenv|env)(\s*$|\s|/)|"
            r"cat\s+/proc/self/environ|"
            r"\$\{[A-Z_]*(TOKEN|KEY|SECRET|PASSWORD|PASSWD|CREDENTIAL)[A-Z_]*\}|"
            r"\$\(\s*(env|printenv)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "network_exfil",
        # Leading boundary includes ``/`` so absolute-path variants
        # (``/usr/bin/curl ...``) are caught. ``host`` is intentionally
        # absent — too many legitimate commands use it as an argument
        # (``docker host``, ``git remote add host:foo``); DNS exfil is
        # already covered by ``dig`` and ``nslookup``.
        re.compile(
            r"(^|[\s;&|`(/])(curl|wget|nc|ncat|socat|ping|nslookup|dig|"
            r"telnet|ssh|scp|sftp|rsync|ftp|tftp)(\s|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "db_destruction",
        re.compile(
            r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX)\b|"
            r"\bTRUNCATE\s+(TABLE\s+)?\w+|"
            r"\bDELETE\s+FROM\s+\w+\s+WHERE\s+1\s*=\s*1\b|"
            r"\bpsql\b|\bpg_dump\b|\bredis-cli\b",
            re.IGNORECASE,
        ),
    ),
    (
        "git_destruction",
        # ``git branch -D`` is NOT in this rule — devs routinely run
        # ``git branch -D feature/old`` for local cleanup, and reflog
        # makes it recoverable. We only deny force-pushes (network-
        # observable, hard-to-undo) and hard resets of remote-tracking
        # branches.
        re.compile(
            r"\bgit\s+push\s+(--force|-f|--force-with-lease)\b|"
            r"\bgit\s+reset\s+--hard\s+(origin|upstream)\b|"
            r"\bgit\s+update-ref\s+-d\b",
            re.IGNORECASE,
        ),
    ),
    (
        "filesystem_nuke",
        re.compile(
            r"\brm\s+-[a-zA-Z]*[rfRF][a-zA-Z]*\s+(/(\s|$)|/\*|~|\$HOME|\.\./)|"
            r"\bsudo\b|"
            r"\bchmod\s+777\b|"
            # Bash-side mirror of the Read deny rule: ``cat /etc/passwd``
            # via the Bash tool would otherwise bypass the path gate.
            r"\b(cat|less|more|head|tail|nl|od|xxd|hexdump)\s+/(etc|proc|sys)/",
            re.IGNORECASE,
        ),
    ),
    (
        "symlink_plant",
        re.compile(
            r"\bln\s+-[a-zA-Z]*s[a-zA-Z]*\s+(/etc|/home|/root|/proc|/sys|/var)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "package_poison",
        re.compile(
            r"\b(npm|pnpm|yarn|bun)\s+(install|i|add)\s+[^-\s]|"
            r"\b(pip|pip3|uv|uvx|pipx)\s+(install|add)\s+[^-\s]",
            re.IGNORECASE,
        ),
    ),
]


# Read/Edit deny: file paths that must never be touched even if the
# subprocess somehow holds a workspace-internal path that ``realpath``
# expands to one of these. The hook canonicalizes with ``os.path.realpath``
# before matching.
# Home-dir-anchored prefix used by credential-store patterns. A bare
# ``.claude/`` substring elsewhere (e.g. our own ``.claude/worktrees/``
# project directory) must NOT match — only the user's actual home
# credentials matter.
_HOME_ANCHOR = r"^(/Users/[^/]+|/home/[^/]+|/root|~)"

READ_DENY_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "dotenv",
        re.compile(r"(^|/)\.env(\.|$)"),
    ),
    (
        "ssh_keys",
        re.compile(rf"{_HOME_ANCHOR}/\.ssh(/|$)|/id_rsa(\.|$)|/id_ed25519(\.|$)"),
    ),
    (
        "aws_creds",
        re.compile(rf"{_HOME_ANCHOR}/\.aws(/|$)"),
    ),
    (
        "claude_creds",
        # Anchor to specific sensitive files under ``~/.claude`` —
        # NOT the whole directory (legitimate tooling reads
        # ``~/.claude/projects/<id>`` transcripts; only the credential
        # store and global settings warrant blocking).
        re.compile(
            rf"{_HOME_ANCHOR}/\.claude/(\.credentials|settings)",
        ),
    ),
    (
        "gh_creds",
        re.compile(rf"{_HOME_ANCHOR}/\.config/gh(/|$)"),
    ),
    (
        "netrc",
        re.compile(rf"{_HOME_ANCHOR}/\.netrc(/|$)"),
    ),
    (
        "system_paths",
        re.compile(r"^/(etc|proc|sys)(/|$)"),
    ),
]


def canonicalize_bash(command: str) -> str:
    """Normalize a Bash command string before matching.

    Collapses common obfuscation tricks so payloads like ``$(echo curl)``,
    backticks, and ``\\x63url`` / ``\\u0063url`` escapes still match the
    plain-text regex rules. The order matters: decode escapes BEFORE
    stripping backslashes, and resolve command substitution BEFORE quote
    removal so ``$(echo "curl")`` still flattens correctly.

    The point is *not* to faithfully evaluate Bash — that would require
    a parser — but to defeat obvious payload-hiding. Determined attackers
    can still bypass with multi-stage indirection (write a script, then
    chmod+exec it; alias a variable with IFS; use ``python -c`` /
    ``urllib`` instead of curl). Layer 4 (env scrub), Layer 5
    (``--add-dir`` pin) and Layer 6 (egress firewall) cover the residual.
    """
    out = command
    # Decode \xHH hex escapes
    out = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), out)
    # Decode \uHHHH unicode escapes
    out = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), out)
    # Collapse $(...) → inner
    out = re.sub(r"\$\(([^)]*)\)", r"\1", out)
    # Collapse backticks → inner
    out = re.sub(r"`([^`]*)`", r"\1", out)
    # Strip remaining backslashes (escapes that didn't decode)
    out = out.replace("\\", "")
    # Drop wrapping single/double quotes around individual tokens
    out = re.sub(r"['\"]", "", out)
    # Squeeze multi-spaces
    return re.sub(r"\s+", " ", out).strip()


def match_bash_deny(command: str) -> tuple[str, str] | None:
    """Return (rule_name, matched_substring) if the command is denied."""
    canonical = canonicalize_bash(command)
    for rule_name, pattern in BASH_DENY_RULES:
        m = pattern.search(canonical)
        if m:
            return rule_name, m.group(0)
    return None


def match_path_deny(path: str) -> tuple[str, str] | None:
    """Return (rule_name, matched_substring) if the path is denied."""
    for rule_name, pattern in READ_DENY_RULES:
        m = pattern.search(path)
        if m:
            return rule_name, m.group(0)
    return None
