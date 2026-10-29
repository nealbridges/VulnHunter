"""JS/TS pack: every pattern in plan §3.2 against an invented app."""

from __future__ import annotations

from pathlib import Path

import pytest

from vh.scaffold import PACKS, scan_repo, ts

FIXTURE = Path(__file__).parent / "fixtures" / "scaffold" / "js_app"

PATTERN_CASES = [
    ("req.query.q", "query param", "q", "http"),
    ("req.params.id", "path param", "id", "http"),
    ("req.body.email", "body field", "email", "http"),
    ("req.headers.authorization", "header", "authorization", "http"),
    ('req.get("referer")', "header", "referer", "http"),
    ('req.header("x-api-key")', "header", "x-api-key", "http"),
    ("req.cookies.session", "cookie", "session", "http"),
    ("req.signedCookies.user", "cookie", "user", "http"),
    ("app.get('/users/:id', handler);", "path param", "id", "http"),
    ("const { a } = req.query;", "query param", "a", "http"),
    ("const { b } = req.body;", "body field", "b", "http"),
    ("create(req.body);", "body field", "<body:whole>", "http"),
    ("process.env.SECRET", "env var", "SECRET", "env"),
    ("const { REGION } = process.env;", "env var", "REGION", "env"),
    ("route.queryParams.q", "client query param", "q", "client"),
    ('route.snapshot.queryParamMap.get("term")', "client query param", "term", "client"),
    ('route.snapshot.searchParams.get("filter")', "client query param", "filter", "client"),
    ('new URLSearchParams(loc).get("page")', "client query param", "page", "client"),
    ('route.queryParams["q"]', "client query param", "q", "client"),
    ('route.queryParamMap?.get("term")', "client query param", "term", "client"),
    ('u.searchParams?.get("q")', "client query param", "q", "client"),
    (
        'new URLSearchParams(new URL(s).search).get("q")',
        "client query param",
        "q",
        "client",
    ),
    ('u.searchParams.get("per-page")', "client query param", "per-page", "client"),
]


@pytest.mark.parametrize(("snippet", "source_type", "variable", "trust"), PATTERN_CASES)
def test_each_pattern_row(snippet: str, source_type: str, variable: str, trust: str) -> None:
    rows, _ = ts.scan("app.js", snippet)
    assert [(r.source_type, r.variable, r.trust_hint) for r in rows] == [
        (source_type, variable, trust)
    ]


def test_multiline_destructuring() -> None:
    text = "const {\n  a,\n  b: c,\n  d = 1,\n  ...rest\n} = req.body"
    rows, unresolved = ts.scan("app.js", text)
    assert [(r.variable, r.line) for r in rows] == [("a", 2), ("b", 3), ("d", 4)]
    assert unresolved == 1


def test_route_literal_params() -> None:
    rows, _ = ts.scan("app.js", 'app.get("/users/:id", h);\napp.get("http://host:8080", h);')
    assert [r.variable for r in rows] == ["id"]


def test_whole_object() -> None:
    rows, _ = ts.scan("app.js", "create(req.body);")
    assert [r.variable for r in rows] == ["<body:whole>"]


def test_comments_ignored() -> None:
    text = "/*\nreq.query.ghost\n*/\nconst s = '*/*';\nconst real = req.query.real;"
    rows, _ = ts.scan("app.js", text)
    assert [r.variable for r in rows] == ["real"]


def test_method_call_not_a_site() -> None:
    rows, _ = ts.scan("app.js", "route.queryParams.subscribe(x => x);\nreq.body = {};")
    assert rows == []


def test_non_literal_counted_not_rowed() -> None:
    rows, unresolved = ts.scan("app.js", "const v = req.query[key];")
    assert rows == []
    assert unresolved == 1


def test_entry_point() -> None:
    text = (
        "const top = req.query.top;\n"
        "function namedOne (req, res) { const a = req.query.a; }\n"
        "namedTwo(req, res) { const b = req.body.b; }\n"
        "const namedThree = (req) => { const c = req.query.c; };\n"
        "async function namedFour(req) { const d = req.query.d; }\n"
        "this.namedFive = (req, res) => { const e = req.query.e; };\n"
    )
    rows, _ = ts.scan("app.js", text)
    assert {r.variable: r.entry_point for r in rows} == {
        "top": "<module>",
        "a": "namedOne",
        "b": "namedTwo",
        "c": "namedThree",
        "d": "namedFour",
        "e": "namedFive",
    }


def test_locations_resolve() -> None:
    result = scan_repo(FIXTURE, PACKS)
    assert result.rows
    for row in result.rows:
        if row.variable.startswith("<"):
            continue
        line = (FIXTURE / row.file).read_text(encoding="utf-8").splitlines()[row.line - 1]
        assert row.variable in line, row


def test_excluded_files() -> None:
    result = scan_repo(FIXTURE, PACKS)
    files = {row.file for row in result.rows}
    assert not any(name.endswith((".spec.ts", ".d.ts")) for name in files)
    assert "node_modules/dep/index.js" not in files
    assert "test/helper.js" not in files
    assert "crlf.js" in files
    assert {"server.js", "routes/search.js", "client/search.component.ts"} <= files
