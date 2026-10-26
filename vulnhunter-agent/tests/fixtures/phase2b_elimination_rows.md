# Phase 2b — elimination rows that reached the wrong verdict (fixture)

Invented verdict rows in the shape Phase 2b produces. Both rows close a
**behavioural** claim — what a browser's URL resolver does with a redirect target —
by reading the helper and citing a test of the helper's own return value. Under the
claim-typing rules both must land in `HOLD-UNVERIFIED`, not `FALSE POSITIVE`.

| Finding | Gates complete? | Production-reachable? | Defenses cover attack? | Severity correct? | Runtime decision | All call sites checked? | Closing claim | Claim type | Evidence | Path reasoned about | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| VULN-001 (NAV-1) `next` open redirect, `login.go:57` | Yes | Yes | **Covers** — `isSafeRedirect` requires a leading `/`, so the target stays on-site | N/A | `static — login.go:57 helper check` | 1/1 | a leading `/` keeps the redirect on this origin | behavioural | static-trace | `login.go:57` → `isSafeRedirect(next)` → `http.Redirect` | FALSE POSITIVE |
| VULN-002 (NAV-2) `returnTo` open redirect, `oauth.go:120` | Yes | Yes | **Covers** — same `isSafeRedirect`; confirmed by `TestSafeRedirectRejectsAbsoluteURL` | N/A | `static — oauth.go:120 helper check` | 1/1 | a leading `/` keeps the redirect on this origin | behavioural | existing-test | `oauth.go:120` → `isSafeRedirect(returnTo)` → `http.Redirect` | FALSE POSITIVE |

## Expected verdicts under the rules

| Row | Expected verdict | Why |
|---|---|---|
| VULN-001 | HOLD-UNVERIFIED | behavioural claim closed by `static-trace` |
| VULN-002 | HOLD-UNVERIFIED | behavioural claim closed by `existing-test` (the test asserts the helper's return value, i.e. intent) |

Probe that would settle both: resolve `//evil.example` and `/\evil.example` against
the site origin with a real WHATWG URL parser and check the resulting host.
