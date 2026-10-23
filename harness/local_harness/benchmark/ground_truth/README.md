# Benchmark Ground Truth

This directory holds the benchmark corpus: one JSON file per target repository,
each containing an array of known findings the scanner is expected to detect.

The repo ships a starter corpus of six findings across three public,
deliberately-vulnerable apps, each pinned to a real commit with file:line
detail:

| File | Findings |
|------|----------|
| `juice-shop.json` | `JUICE-001` SQL injection in `routes/login.ts:34`; `JUICE-002` DOM XSS in `search-result.component.ts:143` |
| `WebGoat.json` | `WEBGOAT-001` path traversal via `fullName` in `ProfileUploadBase.java:51`; `WEBGOAT-002` Zip Slip in `ProfileZipSlip.java:79` |
| `NodeGoat.json` | `NODEGOAT-001` `$where` injection in `allocations-dao.js:78-79`; `NODEGOAT-002` IDOR in `allocations.js:16-18` |

Add your own `<repo-name>.json` files here. `EXAMPLE.json.template` documents
the schema but uses placeholder commit hashes; it is **not** loaded (only
`*.json` files are). Copy and rename it to start a new entry. A file still
named `EXAMPLE.json` is skipped with a warning for the same reason.

## Schema

Each file is a JSON array of finding objects:

```json
[
  {
    "finding_id": "JUICE-001",
    "type": "SQLInjection",
    "source_code": "https://github.com/your-org/example-vulnerable-app/tree/<commit_hash>",
    "description": "Human-readable description of the vulnerability, ideally with file paths, function names, and line numbers so the LLM judge can match the scanner's output."
  }
]
```

| Field | Meaning |
|-------|---------|
| `finding_id` | Stable identifier, **unique across the entire corpus** (not just within one file). Judgments and history are keyed by this id, so a collision silently overwrites results. Prefix with the app name (`NODEGOAT-001`, `JUICE-002`, …). |
| `type` | Vulnerability class (free-form label used in the per-type scorecard). |
| `source_code` | `https://github.com/{org}/{repo}/tree/{commit_hash}` — the benchmark clones the repo at exactly this commit (`git fetch --depth=1 origin <hash>`, full-clone fallback). The commit must be 7–40 hex characters. |
| `description` | The detail the judge compares the scanner's findings against. Be specific. |

The runner validates every file **before any clone**: JSON array of objects,
required fields non-empty, globally unique `finding_id`, well-formed
`source_code` URL. Failures print every problem and exit 1.

## Notes

- Multiple findings that share the same `{org}/{repo}/{commit_hash}` are scanned
  together (one scan per unique repo+commit).
- Runtime output (`benchmark_repos/`, `benchmark_results/`, `finding_history.json`)
  is gitignored and never committed.
