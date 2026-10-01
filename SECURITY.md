# Security Policy

## Reporting

Please report vulnerabilities privately through
[GitHub security advisories](https://github.com/Yashjindal11/adversi/security/advisories/new).
Do not open public issues for security problems. You can expect an acknowledgement within
7 days. Only the latest minor release receives fixes during the 0.x series.

## Threat model and built-in safeguards

AdverSI sends untrusted text (user questions, documents, web pages) to language models
and lets models call tools. Treat every model output as untrusted input.

| Risk | Safeguard | Your responsibility |
|---|---|---|
| Prompt injection via documents or web pages | Tool outputs are data, not instructions; citations are verified against source text; models cannot create sources | Do not give agents tools with side effects you would not let an untrusted user trigger |
| SSRF via `fetch_url` | http(s) only; hosts resolving to private, loopback, link-local, reserved or multicast addresses are refused on every redirect hop; size and content-type limits | DNS can change between check and connect (rebinding). Expose AdverSI to untrusted users only behind network egress controls |
| Code execution | `calculator` parses an AST whitelist, never `eval`; bounded exponents and magnitudes. No Python execution tool ships in the core | Run any code-execution tool in a real sandbox (container, gVisor, Firecracker) |
| Credential leakage | API keys are read from environment variables only; the config schema rejects key fields; `Model.settings()` and run metadata never include credentials; request `metadata` is never sent to providers | Do not log raw HTTP traffic in production |
| Web server exposure | Binds to `127.0.0.1` by default; warns otherwise; request size limits; server-side tool allow-list; output HTML is escaped | The server has **no authentication**. Put it behind an authenticating reverse proxy before exposing it |
| Cost exhaustion | `Budget` limits tokens, cost and calls per run; server caps concurrent runs | Set provider-side spending limits |
| Custom tools | Arguments validated against the signature schema; timeouts; errors contained | A timed-out *synchronous* tool keeps running in its worker thread; prefer async tools for I/O |

## Out of scope

Model outputs being wrong. AdverSI makes claims, evidence and uncertainty inspectable; it
does not make any model output trustworthy by itself.
