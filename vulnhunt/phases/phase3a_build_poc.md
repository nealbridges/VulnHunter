# Phase 3a: Build the Working PoC

> **Context**: You have completed Phase 2b (Verification) and have CONFIRMED
> findings only. The orchestrator's Operating Principles and Investigation
> Discipline are in effect. The runtime to use was decided in Phase 2b and
> recorded on the finding as its `Runtime:` line (see
> `skills/runtime-provisioner/SKILL.md`) — execute in that runtime, never
> outside it.

> **Universal Auth Gap (Phase 2b §9)**: for `VULN-PLATFORM-AUTHN` or
> `VULN-PLATFORM-AUTHZ`, produce ONE PoC against ONE representative
> endpoint and ONE exploit test. Do NOT generate per-endpoint PoCs or
> tests for `SUBSUMED-BY: VULN-PLATFORM-*` findings — the platform
> PoC stands in.

## Output destinations

Write artifacts to these exact locations under `${VULNHUNT_DIR}` — do NOT
name files after a prompt (`phase3c_fixes.md`, `phase3a_build_poc.md`,
etc.):

- PoCs: `${VULNHUNT_DIR}/poc/VULN-NNN_*.md` (one per finding)
- Executable PoC scripts: alongside the `.md` wrapper, in the runtime's
  language (`.py`, `.sh`, `.scala`, …) — the `.md` documents and links it
- Exploit tests: `${VULNHUNT_DIR}/exploit_tests/test_vuln_NNN_*.py`
- Phase summary (VULN-NNN assignment table from the completeness check
  below + per-finding fix strategies from `phase3c_fixes.md`):
  `${VULNHUNT_DIR}/phase3_output.md` — that exact filename, at the
  results-dir top level.

## Pre-Phase 3 Completeness Check (MANDATORY)

Before writing any PoC, produce a VULN-NNN assignment table mapping every
CONFIRMED finding from Phase 2b (High and Medium severity) to a sequential ID:

| VULN-NNN | Phase 2b # | Title | Severity | Runtime |
|---|---|---|---|---|

Row count MUST equal the total High + Medium CONFIRMED findings in Phase 2b.
If fewer: you dropped findings — add them. Every row MUST receive a PoC and
exploit test by end of phase. A CONFIRMED finding cannot be removed without an
explicit FAIL verdict from its exploit test. The `Runtime` column copies the
`Runtime:` line recorded in Phase 2b — a finding with no Runtime line returns
to Phase 2b (the runtime decision was skipped, not deferred).

## What counts as a Working PoC

An **executable artifact**, not a markdown narrative. A real request against a
real (containerized) server, or a real function invocation in the provisioned
runtime — per the finding's recorded `Runtime:` line. The `poc/VULN-NNN.md`
file remains, but as a wrapper *around* the executable artifact: it documents
the PoC, links to the script, and records its output. It does not replace it.

A static-trace-only finding (recorded `Runtime: static — <justification>`) is
the one exception: its "executable artifact" is the concrete data-flow trace
below, and its measured impact in Phase 3b comes from the trace, not a run.

## Choose the format by context

### Runnable PoC (when the runtime executes — the default for Medium+)

Write the PoC as a script in the project's language (or shell) that performs
the attack for real, in the recorded runtime:

```bash
#!/bin/bash
# Working PoC for [VULN-NNN]: [Title]
# Runtime: docker:<image>@<tag>   (copied from the finding's Runtime line)
# Preconditions: [what needs to be running]

curl -X POST http://localhost:8080/api/endpoint \
  -H "Content-Type: application/json" \
  -d '{"field": "malicious_payload_here"}'
```

```python
# Working PoC for VULN-NNN — executes in the recorded runtime
# (in-process harness example)
payload = build_payload_from_poc("VULN-NNN")   # EXACT payload from the PoC doc
result = invoke_vulnerable_function(payload)
print(observed_outcome(result))                # what the attacker gained
```

The script MUST print the observed outcome in a form Phase 3b can measure
(rows returned, bytes amplified, keys stranded, payloads leaked — the unit is
chosen in Phase 3b's impact-unit table).

### Static Data Flow Trace (only when the finding records `Runtime: static`)

When the recorded runtime is static, demonstrate exploitability with a concrete
step-by-step data flow trace showing exactly how attacker input reaches the sink:

```
[VULN-NNN] Static PoC: [Title]

1. ENTRY: Attacker sends POST /api/search with body {"q": "' OR 1=1 --"}
   -> src/handlers/search.go:42  SearchHandler.Handle()
   -> parameter `q` assigned to variable `query`

2. PROPAGATION: `query` passed to buildFilter() without sanitization
   -> src/handlers/search.go:58  buildFilter(query)
   -> src/db/filters.go:23      buildFilter receives `query` as `input` param

3. SINK: `input` concatenated into SQL string
   -> src/db/filters.go:31      sql := "SELECT * FROM items WHERE name = '" + input + "'"
   -> Concrete payload: SELECT * FROM items WHERE name = '' OR 1=1 --'

4. IMPACT: Full table dump. Attacker retrieves all rows from `items` table.
   With UNION injection, can read arbitrary tables including `users`.
```

Requirements for static PoCs:
- Concrete attacker-controlled input value at step 1 (not abstract "malicious input")
- File:line at every step showing exactly where the data flows
- The literal dangerous string/value that reaches the sink
- Concrete impact statement — the same one Phase 3b will measure

### What the PoC wrapper (.md) must contain

1. The attack: goal, payload, request/invocation
2. The exact code path (file:line) the input takes
3. A link to the executable script and its recorded output
4. The impact statement in the class's impact unit (Phase 3b defines it) — the
   mechanism sentence and the impact sentence are different sentences, and the
   wrapper must contain both, labeled as such

## Phase 3a Validation

After writing each PoC:
1. **Save the PoC to a file**: `${VULNHUNT_DIR}/poc/VULN-NNN_short_description.md`
   This is required — the report links to this file. If there is no file, the
   finding cannot be reported as Confirmed.
2. **Execute it in the recorded runtime** (or record the static trace if
   `Runtime: static`), and paste the output into the wrapper `.md`
3. Verify the call chain from input source to sink using the forward trace
   already performed — use Grep to confirm any steps you're uncertain about
4. Confirm the printed/observed outcome matches the wrapper's impact statement.
   If the run shows a different outcome than the PoC predicted, the PoC was
   wrong — fix the PoC, do not reinterpret the output.
