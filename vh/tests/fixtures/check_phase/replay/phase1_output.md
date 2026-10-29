### Recon Output

#### Input Inventory

2 inputs across 1 entry points

| # | Source Type | Location | Variable | Entry Point | Trust Level |
|---|---|---|---|---|---|
| 1 | query param | app/a.go:10 | `q` | handler | unauth |
| 2 | body field | app/a.go:11 | `name` | handler | unauth |

#### Threat Model

| Entry-point group | App-layer auth enforcement |
|---|---|
| x | y |
