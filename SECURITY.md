# Security Policy

Thank you for helping keep Bodhiorchard and its users safe.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

Bodhiorchard is in early public release. Only the latest `0.1.x` line receives security fixes.

## Reporting a Vulnerability

**Please do not report security issues through public GitHub issues, pull requests, or discussions.**

The preferred channel is GitHub's private vulnerability reporting:

➡️  **[Report a vulnerability](https://github.com/mickyarun/bodhiorchard/security/advisories/new)**

If GitHub Security Advisories are not an option for you, email **mickyarunr@gmail.com** with the subject line `SECURITY:` and a clear description of the issue.

Please include, where possible:

- The component or file path involved (backend, frontend, multiplayer, MCP server, etc.)
- A description of the impact (what an attacker could do)
- Steps to reproduce, a proof-of-concept, or a minimal patch
- Your name / handle for credit (optional)

## What to expect

- **Acknowledgement** within 48 hours of your report.
- A triage update within 7 days with a severity assessment and proposed timeline.
- Coordinated disclosure: we will not file a public issue or push a public fix that names the vulnerability until a patched release is available, and we will credit reporters who wish to be named.

## Scope

In scope:

- The code in this repository (backend, frontend, multiplayer, shared libraries, MCP server)
- Default Docker and Hybrid deployment configurations

Out of scope:

- Issues in third-party dependencies — please report those upstream first; we will track and bump versions when fixes land.
- Self-inflicted misconfigurations (exposing the dev stack to the public internet without auth, committing secrets, etc.)
- Findings that require physical access to a developer's machine or a compromised LLM API key.

## Safe harbour

We will not pursue legal action against researchers who:

- Make a good-faith effort to avoid privacy violations, data destruction, and service degradation
- Report through the channels above
- Give us reasonable time to remediate before any public disclosure

Thank you.
