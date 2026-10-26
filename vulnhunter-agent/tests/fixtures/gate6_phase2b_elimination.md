# Gate 6 Phase 2b — verbatim elimination rows (fixture)

Captured verbatim from the Gate 6 swarm run's `phase2b_output.md` (2026-10-19,
outside this repo) so the A2 replay test runs in CI without reaching outside it.
The original path is not reproduced here to keep the requirement register free of
client-specific directory names.

These are the REAL verdict rows from the run that lost the `escapeVisibility`
High. The replay test feeds them through A2's classification rules and requires
the outcome Phase 2b should have produced. Do not edit these rows to make a test
pass — they are the historical record.

**Column note.** The original table's columns were exactly: `Finding`, `Gates
complete?`, `Production-reachable?`, `Defenses cover attack?`, `Severity
correct?`, `All call sites checked?`, `Verdict`. There was **no** "Runtime
decision" column — that is A2's new column (§3.1), and it appears in this fixture
only as the `Runtime decision` column added for the replay. The final cell of each
verbatim row above is the *original* `All call sites checked?` content (`1/1`,
`2/2 verified`), preserved unchanged. Do not "fix" those cells: they are call-site
counts, not runtimes, and their presence is the historical fact A2 §3.1 addresses.

| Finding | Gates complete? | Production-reachable? | Defenses cover attack? | Severity correct? | Runtime decision | All call sites checked? | Verdict |
|---|---|---|---|---|---|---|---|
| VULN-001 (SG-1 INJ-1) `id` query inj, `tenancy.go:91` | Yes | Yes | **Covers** — `escapeVisibility` doubles `'`; the only string-literal escape vector. Non-quote metacharacters (`*`, `(`, `)`, space) remain bound inside the `'...'` literal in Temporal's SQL-like grammar and cannot terminate the literal. `ownedByTenant` also interpolates the same tenant (server-derived) AND-conjoined. Injection cannot drop the `QueryaiTenantId` clause → tenant isolation preserved. | High if real, but the escape neutralizes the escape path. | 1/1 (`ownedByTenant` is the sole caller of this query shape) | **FALSE POSITIVE** — quote-doubling fully neutralizes; no non-quote char can close the literal; tenant clause always enforced. |
| VULN-002 (SG-1 INJ-3) `scheduleId` query inj, `investigations.go:199` | Yes | Yes | **Covers** — same `escapeVisibility` on `*params.ScheduleId`. Confirmed by existing test `TestInvestigationListQueryEscapesScheduleID` (`investigations_test.go:175-180`): input `x' OR '1'='1` yields `TemporalScheduledById = 'x'' OR ''1''=''1'` — literal stays closed. Full query `WorkflowType='x' AND QueryaiTenantId='tenant' AND TemporalScheduledById='<sched>'`; the tenant clause is always present and AND-conjoined. To break tenant scoping the attacker must close the string literal, which requires `'` (escaped). No other token can. | High if real, but escape path neutralized. | 1/1 (`investigationListQuery` is the only builder; always passed `tenantFilterFor(tenant)` + `WorkflowType` clause — verified at `investigations.go:50`) | **FALSE POSITIVE** — same as VULN-001. The candidate's non-quote metacharacter theory fails: characters inside the literal only vary the glob/suffix match, not the clause structure; tenant scope remains. |

## Why these rows are the canonical replay case

Both rows are **behavioural** claims: each asserts what `escapeVisibility` and the
Temporal query parser *do* with a value. Neither ran a probe.

- VULN-002's cited evidence is `TestInvestigationListQueryEscapesScheduleID`,
  which asserts a **built string** (`... = 'x'' OR ''1''=''1'`). That is
  `existing-test` — evidence of the author's intent, not of parser behaviour.
- The real defect is the trailing backslash: `sqlparser` treats `\` as an escape,
  so a `scheduleId` ending in `\` closes the quote early and `OR WorkflowId IS
  NOT NULL` lands outside the literal. A test asserting the emitted string cannot
  see this, because the string looks correct.
- Under A2 this must land in `HOLD-UNVERIFIED`, not `FALSE POSITIVE`.

Also note the `Runtime decision` column here reads `1/1` (call-site count) rather
than a runtime — the historical table's columns did not match their headers,
which is why A2 §3.1 redefines them.
