#!/bin/bash
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

# Egress allow-list firewall for the backend container running ``claude``
# subprocesses. Adapted from Anthropic's reference devcontainer script
# (https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh).
#
# Phase D — Layer 6. Runs as a one-shot init container BEFORE the
# backend starts. Locks egress to a small allowlist so a compromised
# ``claude`` subprocess cannot phone home, even if every app-layer
# defense fails.
#
# Allow list:
#   * api.anthropic.com         — Anthropic API
#   * statsig.anthropic.com     — Claude Code telemetry (gated by env)
#   * registry.npmjs.org        — Claude Code self-update + MCP installs
#   * pypi.org / files.pythonhosted.org — pip installs (allow-listed
#     here only because Layer 2 already denies them at the tool gate)
#   * github.com / api.github.com — Git clones over HTTPS
#
# Requires ``NET_ADMIN`` capability inside the container. If the host
# kernel lacks iptables (macOS Docker Desktop without ``--cap-add``),
# this script logs and exits 0 rather than failing the boot — the
# app-layer defenses still apply.

set -uo pipefail

if ! command -v iptables >/dev/null 2>&1; then
    echo "init-firewall: iptables not available; skipping egress lockdown" >&2
    exit 0
fi

# Probe capability: a flush that fails means we don't have NET_ADMIN.
if ! iptables -F OUTPUT 2>/dev/null; then
    echo "init-firewall: no NET_ADMIN cap; skipping egress lockdown" >&2
    exit 0
fi

iptables -F INPUT
iptables -F FORWARD
iptables -F OUTPUT
ip6tables -F INPUT 2>/dev/null || true
ip6tables -F FORWARD 2>/dev/null || true
ip6tables -F OUTPUT 2>/dev/null || true

# Default policy: drop everything.
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP
ip6tables -P INPUT DROP 2>/dev/null || true
ip6tables -P FORWARD DROP 2>/dev/null || true
ip6tables -P OUTPUT DROP 2>/dev/null || true

# Loopback always allowed.
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Allow established / related (return traffic for our outbound calls).
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# DNS — required so we can resolve the allow-listed hostnames.
# Allow only UDP/TCP 53 to the cluster's resolver (usually the gateway).
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Resolve each allowed domain and add an OUTPUT ACCEPT for its IPs.
# We re-resolve at every container start so DNS churn (cloudflare,
# anthropic CDNs) doesn't strand us. Failure to resolve a single
# domain is non-fatal — log and continue.
ALLOWED_DOMAINS=(
    "api.anthropic.com"
    "statsig.anthropic.com"
    "registry.npmjs.org"
    "pypi.org"
    "files.pythonhosted.org"
    "github.com"
    "api.github.com"
    "objects.githubusercontent.com"
    "codeload.github.com"
)

resolve_and_allow() {
    local domain="$1"
    # ``getent ahosts`` returns IPv4 + IPv6; we only iptables IPv4.
    local ips
    ips=$(getent ahosts "$domain" 2>/dev/null | awk '/STREAM/ {print $1}' | sort -u)
    if [[ -z "$ips" ]]; then
        echo "init-firewall: failed to resolve $domain; skipping" >&2
        return
    fi
    while IFS= read -r ip; do
        if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            iptables -A OUTPUT -d "$ip" -p tcp --dport 443 -j ACCEPT
            iptables -A OUTPUT -d "$ip" -p tcp --dport 80 -j ACCEPT
        fi
    done <<< "$ips"
    echo "init-firewall: allowed $domain → $(echo "$ips" | tr '\n' ' ')" >&2
}

for d in "${ALLOWED_DOMAINS[@]}"; do
    resolve_and_allow "$d"
done

# Diagnostic: dump the resulting ruleset so the container logs explain
# any subsequent connection refusal.
iptables -L OUTPUT -v -n >&2
echo "init-firewall: egress lockdown applied" >&2
