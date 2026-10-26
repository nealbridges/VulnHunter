# Phase 2b — elimination rows that reached the wrong verdict (fixture)

Verdict rows in the shape Phase 2b produces, used by the replay test to prove that
the classification rules close a behavioural claim as `HOLD-UNVERIFIED` rather than
eliminating it.

Provenance, stated plainly: these rows are MODELLED ON a real run's elimination table
-- the structure, the column set, the reasoning shape and the mistake are that run's
-- but every noun has been replaced. Function names, test names, file names and the
run's own label are generic (`quoteEscape`, `listBuilder`, `store.go`, "the field
run"), so a reader needs no knowledge of any engagement to follow the argument, and
no identifier from any one codebase appears. Nothing here names a specific scan.

The defect they encode was observed in the field: a defense whose adequacy depends
on what a downstream parser does with a value was closed by citing a test that
asserts the value the code *emitted*. That test proves intent. It does not prove
the parser agrees. The rules must turn that elimination into a HOLD.

Each row has these columns: `Finding`, `Gates complete?`, `Production-reachable?`,
`Defenses cover attack?`, `Severity correct?`, `Runtime decision`, `All call sites
checked?`, `Verdict`. The `Runtime decision` column here holds call-site counts
(`1/1`, `2/2`) rather than runtimes — a column whose header and contents disagree,
which is the historical mismatch the spec fixes. Do not "fix" these cells.

| Finding | Gates complete? | Production-reachable? | Defenses cover attack? | Severity correct? | Runtime decision | All call sites checked? | Verdict |
|---|---|---|---|---|---|---|---|
| VULN-001 (INJ-1) `name` argument injected, `store.go:91` | Yes | Yes | **Covers** — `quoteEscape` doubles `'`; the only string-literal escape vector. Other metacharacters (`*`, `(`, `)`, space) stay inside the `'...'` literal in the grammar and cannot close it. A fixed scope clause is AND-conjoined, so injection cannot drop it and isolation is preserved. | High if real, but the escape neutralizes the escape path. | 1/1 (`scopeClause` is the sole caller of this shape) | **FALSE POSITIVE** — quote-doubling fully neutralizes; no other char can close the literal; scope clause always enforced. |
| VULN-002 (INJ-2) `key` argument injected, `handlers.go:199` | Yes | Yes | **Covers** — same `quoteEscape` on `*params.Key`. Confirmed by existing test `TestListBuilderEscapesKeys` (`handlers_test.go:175-180`): input `x' OR '1'='1` yields `Key = 'x'' OR ''1''=''1'` — the literal stays closed. The full statement is `Kind='x' AND ScopeId='scope' AND Key='<key>'`; the scope clause is always present and AND-conjoined. To break scoping the attacker must close the string literal, which requires `'` (escaped). No other token can. | High if real, but escape path neutralized. | 1/1 (`listBuilder` is the only builder; always passed `scopeFor(scope)` + `Kind` clause — verified at `handlers.go:50`) | **FALSE POSITIVE** — same as VULN-001. The candidate's non-quote metacharacter theory fails: characters inside the literal only vary the glob/suffix match, not the clause structure; scope remains. |

## Why these rows are the canonical replay case

Both rows are **behavioural** claims: each asserts what `quoteEscape` and the
grammar *do* with a value. Neither ran a probe.

- VULN-002's cited evidence is `TestListBuilderEscapesKeys`, which asserts a
  **built string** (`... = 'x'' OR ''1''=''1'`). That is `existing-test` — evidence
  of the author's intent, not of parser behaviour.
- The real defect is a trailing backslash: the grammar treats `\` as an escape, so
  a key ending in `\` closes the quote early and a trailing predicate lands outside
  the literal. A test asserting the emitted string cannot see this, because the
  string looks correct.
- Under the spec this must land in `HOLD-UNVERIFIED`, not `FALSE POSITIVE`.
