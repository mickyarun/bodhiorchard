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
    # --- Reverse shells / pivots -----------------------------------------
    "Bash(mkfifo:*)",
    # --- Cryptominers ----------------------------------------------------
    "Bash(xmrig:*)",
    "Bash(minerd:*)",
    "Bash(cgminer:*)",
    "Bash(ethminer:*)",
    "Bash(t-rex:*)",
    "Bash(nbminer:*)",
    # --- macOS Keychain extractor ----------------------------------------
    "Bash(security find-generic-password:*)",
    "Bash(security find-internet-password:*)",
    "Bash(security dump-keychain:*)",
    "Bash(security unlock-keychain:*)",
    # --- Container escape primitives -------------------------------------
    "Bash(nsenter:*)",
    "Bash(unshare:*)",
    "Bash(chroot:*)",
    # --- Debugger-attach process injection -------------------------------
    "Bash(gdb -p:*)",
    "Bash(strace -p:*)",
    "Bash(ltrace -p:*)",
    # --- Persistence -----------------------------------------------------
    "Bash(crontab -e:*)",
    "Bash(launchctl load:*)",
    "Bash(systemctl enable:*)",
    # --- Data destruction beyond rm --------------------------------------
    "Bash(dd if=/dev/:*)",
    "Bash(dd of=/dev/:*)",
    "Bash(shred:*)",
    "Bash(wipefs:*)",
    "Bash(mkfs:*)",
    # --- Additional DB tools ---------------------------------------------
    "Bash(mongodump:*)",
    "Bash(mongorestore:*)",
    "Bash(mysqldump:*)",
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
    # --- Shell history (leaks prior commands incl. ad-hoc tokens) -------
    "Read(~/.bash_history)",
    "Read(~/.zsh_history)",
    "Read(~/.python_history)",
    "Read(~/.node_repl_history)",
    # --- macOS Keychain / browser cookies / Apple cred stores -----------
    "Read(~/Library/Keychains/**)",
    "Read(~/Library/Cookies/**)",
    "Read(~/Library/Application Support/Google/Chrome/**)",
    "Read(~/Library/Application Support/Firefox/**)",
    "Read(~/Library/Application Support/BraveSoftware/**)",
    "Read(~/Library/Application Support/Microsoft Edge/**)",
    # --- Cloud / package-manager credential stores ----------------------
    "Read(~/.config/gcloud/**)",
    "Read(~/.kube/**)",
    "Read(~/.azure/**)",
    "Read(~/.config/1Password/**)",
    "Read(~/.docker/config.json)",
    "Read(~/.gnupg/**)",
    "Read(~/.pgpass)",
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
            # Classic curl|bash plus base64-decode-into-shell and
            # printf-decode-into-shell (encoded-payload obfuscation).
            # Canonicalization collapses ``$(...)`` so ``eval $(cat x)``
            # arrives here as ``eval cat x``; match accordingly.
            r"(curl|wget|fetch)\b[^|;]*\|\s*(bash|sh|zsh|ksh|python\d?|perl|ruby|node)\b|"
            r"\bbase64\s+-?d[^|;]*\|\s*(bash|sh|zsh|ksh|python\d?|perl|ruby|node)\b|"
            r"\bprintf\s+['\"][^|;]*\|\s*(bash|sh|zsh|ksh|python\d?|perl|ruby|node)\b|"
            r"\beval\s+(curl|wget|cat|base64|echo|cat\b)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reverse_shell",
        # Classic ``bash -i >& /dev/tcp/host/port`` family plus the
        # python / perl / ruby socket-based forms and any redirection
        # involving ``/dev/tcp/`` or ``/dev/udp/``. ``mkfifo`` and
        # ``nc -e`` are also dead-giveaway primitives.
        re.compile(
            r"\bbash\s+-[a-zA-Z]*i[a-zA-Z]*\b(?=[^|]*(>|/dev/tcp))|"
            r"/dev/(tcp|udp)/|"
            r"\b(python\d?|perl|ruby)\s+-[ce]\s+[^;]*\bsocket(?!\.io)\b|"
            r"\b(python\d?|perl|ruby)\s+-[ce]\s+[^;]*\bSocket\b|"
            r"\b(nc|ncat)\s+-[a-zA-Z]*e[a-zA-Z]*\s+/|"
            r"\bmkfifo\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cryptominer",
        # Common miner binary names + stratum pool URLs. False-positive
        # risk is near zero — no legitimate skill spawns these names.
        re.compile(
            r"\b(xmrig|minerd|cgminer|ethminer|t-rex|trex|nbminer|nicehash|gminer|"
            r"phoenixminer|lolminer|teamredminer|bzminer|kawpow)\b|"
            r"\bstratum\+(tcp|ssl)://",
            re.IGNORECASE,
        ),
    ),
    (
        "keychain_dump",
        # macOS ``security`` CLI is the canonical keychain extractor.
        # Also covers ``dscl`` password reads.
        re.compile(
            r"\bsecurity\s+(find-(generic|internet|certificate)-password|"
            r"dump-(keychain|trust-settings)|export|unlock-keychain)\b|"
            r"\bdscl\s+.*\s+-read.*\b(passwd|password|shadowhash)",
            re.IGNORECASE,
        ),
    ),
    (
        "container_escape",
        # Patterns used to break out of a container into the host
        # namespaces / filesystem.
        re.compile(
            r"\bnsenter\b|"
            r"\bunshare\s+[^;]*(--pid|--mount-proc|--user)|"
            r"/proc/1/(root|exe|environ|cwd)|"
            r"\bdocker\s+exec\s+|"
            r"\bkubectl\s+exec\s+|"
            r"\bchroot\s+/",
            re.IGNORECASE,
        ),
    ),
    (
        "process_injection",
        # Debugger-attach used to inject code into another running
        # process. Local ``gdb ./mybin`` style (no -p) is allowed.
        re.compile(
            r"\bgdb\s+(-p|--pid)\b|"
            r"\bstrace\s+(-p|--attach)\b|"
            r"\bltrace\s+-p\b|"
            r"\bdtrace\s+-p\b",
            re.IGNORECASE,
        ),
    ),
    (
        "persistence",
        # Cron / launchd / systemd handles that establish persistence
        # outside the workspace. ``crontab -l`` (read-only) is allowed.
        re.compile(
            r"\bcrontab\s+(-e|-)\s*($|[<>|&])|"
            r"\blaunchctl\s+(load|bootstrap|enable)\b|"
            r"\bsystemctl\s+(enable|start)\s+|"
            r"\bat\s+(now|\+|noon|midnight)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recon",
        # Setuid scan and namespace reconnaissance — telegraphic of
        # privilege-escalation prep. ``find . -name foo`` stays fine
        # because it has no ``-perm`` argument with setuid bits.
        # Symbolic form ``-perm -u+s`` and octal ``-4000`` both caught.
        re.compile(
            r"\bfind\s+/\S*\s.*-perm\s+(-?0?[24-7]?[0-7]{3}|[-+/]?[ug]?\+?s)\b|"
            r"\bgetcap\s+-r\s+/",
            re.IGNORECASE,
        ),
    ),
    (
        "data_destruction",
        # Sibling of ``filesystem_nuke`` aimed at low-level disk /
        # secure-erase tools that ``rm -rf`` doesn't cover. ``dd`` is
        # matched on EITHER side (``if=/dev/sda`` source-dump exfil OR
        # ``of=/dev/sda`` destructive overwrite). ``mkfs.ext4`` is the
        # filesystem-typed variant of ``mkfs``.
        re.compile(
            r"\bdd\s+[^|;]*\b(if|of)=/dev/(sd|nvme|disk|hd|mmcblk|sda|nvme0)|"
            r"\bshred\s+-?[a-zA-Z]*[uz]|"
            r"\bwipefs\s+-a|"
            r"\bmkfs(\.\w+)?\s+",
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
            r"\bpsql\b|\bpg_dump\b|\bredis-cli\b|"
            # Additional DB dump / destruction tools — Mongo / MySQL /
            # SQLite. The agent has no legitimate reason to invoke any
            # of these against shared databases.
            r"\bmongodump\b|\bmongorestore\b|\bmongoexport\b|"
            r"\bmysqldump\b|"
            r"\bsqlite3?\s+[^;|]*\.(dump|backup|read)\b",
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
            # Bash-side mirror of the Read deny rules: ``cat /etc/passwd``
            # or ``cat ~/.ssh/id_rsa`` via the Bash tool would otherwise
            # bypass the path gate (which only fires for Read / Edit).
            r"\b(cat|less|more|head|tail|nl|od|xxd|hexdump|base64|grep)\s+"
            # Optional intervening tokens (flags, line numbers, sed scripts
            # like ``1p`` or ``{print $1}``) between the verb and the
            # target path. We accept anything that does NOT start with the
            # sensitive-path roots so the trailing alternation still
            # anchors the match.
            r"(?:[^/~$\s][^\s]*\s+)*"
            r"(/(etc|proc|sys)/|"
            r"(~|\$HOME|/Users/[^/]+|/home/[^/]+)/\."
            r"(ssh|aws|netrc|gnupg|kube|azure|pgpass|"
            r"bash_history|zsh_history|python_history|node_repl_history|"
            r"claude/\.credentials|claude/settings|config/gh|"
            r"config/gcloud|config/1Password|docker/config))",
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
        "shell_history",
        # ``cat ~/.bash_history`` style. Bash history, zsh history,
        # python REPL history, node REPL, ruby IRB.
        re.compile(rf"{_HOME_ANCHOR}/\.(bash|zsh|sh|python|node|irb)_history(/|$)"),
    ),
    (
        "macos_keychain",
        re.compile(r"/Library/Keychains(/|$)"),
    ),
    (
        "browser_cookies",
        # Chrome / Brave / Edge / Firefox / Safari cookie stores. All
        # are session-bearer caches that, once leaked, hand authentic-
        # session access to every site the user is logged into.
        re.compile(
            r"/Library/Cookies(/|$)|"
            r"/Library/Application Support/("
            r"Google/Chrome|Firefox|BraveSoftware|Microsoft Edge|"
            r"com\.operasoftware\.Opera|Arc|Vivaldi)/.*(/Cookies($|/)|"
            r"/Login Data($|-)|/Local State$)"
        ),
    ),
    (
        "cloud_creds",
        # GCP / kube / Azure / 1Password / Docker / GPG / Postgres creds.
        # ``~/.config/gcloud`` may legitimately exist on a dev host; the
        # threat is reading the credentials.db / *.json key store inside.
        re.compile(
            rf"{_HOME_ANCHOR}/("
            r"\.config/gcloud|"
            r"\.kube|"
            r"\.config/1Password|"
            r"\.azure|"
            r"\.docker/config\.json|"
            r"\.docker/.*\.key|"
            r"\.pgpass|"
            r"\.gnupg"
            r")(/|$)"
        ),
    ),
    (
        "secret_extensions",
        # Generic key / certificate / vault file extensions. False-
        # positive risk on workspace files (.key in a frontend project),
        # mitigated by ``--add-dir`` workspace pin (the file must already be
        # inside the workspace and survive the read tool's own checks).
        re.compile(r"\.(pem|p12|pfx|jks|keystore|kdbx)$"),
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
    ``urllib`` instead of curl). The env scrub, ``--add-dir`` workspace
    pin, and egress firewall cover the residual.
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
    # Inline variable assignments and their references: ``X=curl; $X foo``
    # / ``CMD=wget;${CMD} foo`` → ``X=curl; curl foo``. We capture
    # NAME=VALUE pairs (single-token values), then substitute every
    # ``$NAME`` / ``${NAME}`` further along in the line with the value.
    # Only a single pass — chained indirection (``A=B; B=curl; $A``) is
    # accepted residual risk.
    assignments: dict[str, str] = {}
    for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)=([^\s;|&]+)", out):
        assignments[m.group(1)] = m.group(2)
    for name, value in assignments.items():
        out = re.sub(rf"\$\{{{name}\}}", value, out)
        out = re.sub(rf"\${name}\b", value, out)
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
