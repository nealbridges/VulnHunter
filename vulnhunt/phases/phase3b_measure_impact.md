# Phase 3b: Measure Impact

> **Context**: The working PoC is built (Phase 3a) and has executed in the
> finding's recorded `Runtime:` — or produced its static trace. This phase
> extracts the **measured delta**, in the unit natural to the vulnerability
> class, and writes it onto the finding. It is the difference between
> "the vulnerability is there" (Phase 2b) and "here is what an attacker
> gains, numerically" (this phase).

## The rule

An impact statement without a number is a claim, not a measurement. "The
attacker can dump the table" is a claim. "3/20 payloads returned
victim-tenant rows; 17 rejected fail-closed" is a measurement. Every
Confirmed finding MUST carry its measurement before Phase 4.

## Impact-unit table

Measure in the unit natural to the vulnerability class. If the class is not
listed, define the unit in the PoC wrapper (one sentence: "impact is measured
in X") and measure in it — do not leave the unit implicit.

| Class | Measured impact unit |
|---|---|
| CWE-639 / IDOR | "N rows from tenant B returned to tenant A's caller" |
| CWE-400 / amplification | "1 request → N× allocation / N subscriptions / N bytes retained" |
| CWE-404 / credential lifecycle | "N keys stranded × TTL = X key-hours live with no consumer" |
| CWE-943 / injection | "N of M payloads leak rows; K rejected fail-closed" |
| CWE-295 / transport | "token + ciphertext captured inplaintext by in-segment MITM" (or "N/A — compensated") |
| Prompt injection (CWE-1427) | "directive obeyed: YES/NO + the action taken" |
| CWE-22 / path traversal | "N files read outside the base dir; deepest path reached" |
| CWE-78 / command injection | "commands executed: N; output returned to attacker: YES/NO" |
| CWE-79 / XSS | "payload rendered unescaped in response: YES/NO; contexts: N" |
| CWE-502 / deserialization | "arbitrary class instantiated: YES/NO; gadget chain depth: N" |
| CWE-287 / auth bypass | "protected resources reachable without auth: N of M attempted" |
| CWE-200 / info exposure | "extra data fields exposed: N; sensitivity tier: LOW/MED/HIGH" |
| Access control (authz) | "privileged actions as another user: N of M attempted" |
| Race condition | "inconsistent states produced in N of K concurrent attempts" |
| Open redirect | "redirects to attacker domain: YES/NO" |
| SSRF | "requests reaching unintended endpoint: N; internal targets hit: N" |
| Crypto weakness | "attackers can decrypt/forge: YES/NO; keys affected: N" |
| Mass assignment | "fields settable beyond authorization: N; escalation achieved: YES/NO" |
| Confused deputy | "downstream actions with elevated credentials: N; attacker-controlled inputs carried: N" |
| Conditional validation bypass | "requests succeeding without the bypassed checks: N of M; resources exposed: N" |

## How to measure

1. **Run the working PoC** in the recorded runtime and capture its output.
2. **Reduce the output to the unit**: the PoC may print raw response data;
   the measurement is the count, ratio, or YES/NO in the unit above — derived
   from the output, not restating it.
3. **Bound the measurement**: N of M attempted, not just N. A number without
   its denominator ("3 payloads leaked") hides the trial size ("3 of 20").
4. **Record negatives**: what the defense blocked is part of the measurement
   ("17 rejected fail-closed" is as informative as "3 leaked").
5. **Static findings**: measure from the trace — the number of reachable
   sinks, reachable identities, or exposed values the trace establishes.
   State the basis ("static trace; unexecuted").

## What to write on the finding

Append to `poc/VULN-NNN_*.md` a **Measured Impact** block:

```
## Measured Impact

Unit: <the unit from the table, or the newly-defined one>
Result: <the number/ratio/verdict>
Basis: executed in <runtime> / static trace
Denominator: N of M <what was attempted>
Negative space: <what the defense blocked, with the count>
```

Example:

```
## Measured Impact

Unit: rows from tenant B returned to tenant A's caller
Result: 3 of 20 payloads returned victim-tenant rows
Basis: executed in docker:python:3.12-slim@sha256:... against the live service
Denominator: 20 payload variants attempted
Negative space: 17 rejected fail-closed at the tenant filter (src/filters.go:88)
```

## Verdict interaction

| Measurement outcome | Action |
|---|---|
| Impact measured, non-zero | Finding keeps its Phase 2b severity; the number joins the report row. |
| Impact measured, zero | The exploit executes but the attacker gains nothing. Downgrade to Code Smell — the mechanism is real, the impact is absent. |
| Impact larger than severity implied | Escalate the severity tier with the number as the argument — the measurement argues the tier. |
| Unit undefined for the class | Define it in the wrapper first (one sentence), then measure. Never report an implicit unit. |
| PoC and measurement disagree | Fix the PoC, re-run, re-measure. Never reinterpret the output to fit the claim. |

## Severity is self-arguing now

It is hard to call something High when the measured impact is "one 200KB body
allocates in one worker" and easy when it is "cross-tenant, 3 sinks,
unauthenticated-adjacent." The numbers argue the tier, which reduces the
inter-run severity spread directly. If you find yourself arguing for a tier
without a number, you are missing the measurement — go get it.

## Hand-off

A finding is ready for Phase 3c (fixes) when it has: a working PoC (Phase 3a),
a measured impact block, and an exploit test whose result matches the
measurement. Only findings with PASS results proceed to Phase 3c.
