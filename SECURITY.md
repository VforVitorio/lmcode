# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (main) | yes |
| older releases | no |

lmcode is pre-1.0. Only the current `main` branch receives security fixes.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately by emailing the maintainer directly (address in the GitHub profile), or by using GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) feature if enabled on the repo.

Include:
- A clear description of the issue
- Steps to reproduce
- Potential impact
- Any suggested fix (optional but welcome)

You'll receive an acknowledgment within 48 hours and a resolution plan within 7 days.

---

## Security model

lmcode runs locally and is designed for local use. Key things to understand:

**What lmcode does that has security implications:**
- Executes shell commands via the `run_shell` tool (on behalf of the agent)
- Reads and writes files in your working directory
- Makes HTTP requests to `localhost:1234` (LM Studio)
- Optionally makes HTTP requests to external APIs via MCP/OpenAPI connectors

**What lmcode does NOT do by default:**
- Send your code or files to any external server
- Store credentials anywhere other than your local config file
- Authenticate with any remote service (unless you configure an MCP connector that does)

**Permission modes:**
- `ask` (default) — agent asks before running shell commands or writing files
- `auto` — agent acts without confirmation (use only in trusted environments)
- `strict` — read-only mode, no writes or shell execution

**MCP / OpenAPI connectors:**
If you configure lmcode to connect to an external API via `--openapi`, the agent will be able to make real HTTP requests to that API. Only connect to APIs you trust and understand.

---

## Dependencies

lmcode uses a locked dependency tree (`uv.lock`). If a dependency has a known CVE, open an issue and we will update it promptly.
