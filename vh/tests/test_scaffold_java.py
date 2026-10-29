"""Java pack: every pattern in plan §3.3, body expansion and exclusions."""

from __future__ import annotations

from pathlib import Path

import pytest

from vh.scaffold import PACKS, java, scan_repo

FIXTURE = Path(__file__).parent / "fixtures" / "scaffold" / "java_app"

JAVA_CASES = [
    ('@RequestParam("a") String a', "query param", "a"),
    ('@RequestParam(value = "b") String b', "query param", "b"),
    ('@RequestParam(name = "c") String c', "query param", "c"),
    ("@RequestParam String d", "query param", "d"),
    ('request.getParameter("e")', "query param", "e"),
    ('request.getParameterValues("f")', "query param", "f"),
    ('@PathVariable("g") String g', "path param", "g"),
    ('@GetMapping("/x/{h}")', "path param", "h"),
    ('@PostMapping(value = "/y/{i}")', "path param", "i"),
    ('@RequestMapping(path = "/z/{j}")', "path param", "j"),
    ('@RequestHeader("k") String k', "header", "k"),
    ('request.getHeader("l")', "header", "l"),
    ('@CookieValue("m") String m', "cookie", "m"),
    ('@RequestParam("n") MultipartFile n', "file upload", "n"),
    ('System.getenv("HOME")', "env var", "HOME"),
    ('@Value("${cfg.key}")', "config", "cfg.key"),
    ('@RequestParam(defaultValue = "0", value = "page") String page', "query param", "page"),
    ('@RequestParam(defaultValue = "0", name = "page") String page', "query param", "page"),
    ('@GetMapping("/files/{name:.+}")', "path param", "name"),
    ('@RequestParam(defaultValue = "0") String page', "query param", "page"),
    ('@RequestParam("fullName", required = false) String name', "query param", "fullName"),
    ('@RequestHeader("X-Request-Id", required = false) String id', "header", "X-Request-Id"),
]


@pytest.mark.parametrize(("snippet", "kind", "variable"), JAVA_CASES)
def test_each_pattern_row(snippet: str, kind: str, variable: str) -> None:
    rows, _ = java.scan("Api.java", snippet)
    assert (kind, variable) in [(row.source_type, row.variable) for row in rows]


def test_body_expansion() -> None:
    result = scan_repo(FIXTURE, PACKS)
    body = [row for row in result.rows if row.source_type == "body field"]
    assert {(row.file, row.variable) for row in body} >= {
        ("LoginBody.java", "username"),
        ("LoginBody.java", "email"),
        ("Payload.java", "role"),
        ("Payload.java", "scope"),
    }
    assert "<body:unresolved>" in {row.variable for row in body}


def test_comments_ignored() -> None:
    text = '// @RequestParam("ghost") String g\n/* request.getHeader("ghost2") */\nrequest.getParameter("real");'
    rows, _ = java.scan("Api.java", text)
    assert [row.variable for row in rows] == ["real"]


def test_excluded_files() -> None:
    result = scan_repo(FIXTURE, PACKS)
    files = {row.file for row in result.rows}
    assert "test/ApiTest.java" not in files
    assert "Api.java" in files


@pytest.mark.parametrize(
    "snippet", ["@RequestParam", "request.getParameter(name)", "System.getenv(name)"]
)
def test_non_literal_counted_not_rowed(snippet: str) -> None:
    rows, unresolved = java.scan("Api.java", snippet)
    assert rows == []
    assert unresolved == 1


def test_mapping_entry_point() -> None:
    rows, _ = java.scan(
        "Api.java", '@GetMapping("/users/{userId}")\npublic String users() {\n    return null;\n}'
    )
    assert [(row.variable, row.entry_point) for row in rows] == [("userId", "users")]


def test_next_line_request_body(tmp_path: Path) -> None:
    (tmp_path / "Body.java").write_text("public class Body {\n    private String username;\n}\n")
    (tmp_path / "Api.java").write_text(
        'public class Api {\n    public String login(@RequestBody\n        Body body) {\n        return "";\n    }\n}\n'
    )
    rows = [row for row in scan_repo(tmp_path, PACKS).rows if row.source_type == "body field"]
    assert [(row.file, row.variable) for row in rows] == [("Body.java", "username")]


def test_multiple_mapping_literals() -> None:
    rows, _ = java.scan("Api.java", '@GetMapping({"/a/{id}", "/b/{other}"})')
    assert {row.variable for row in rows} == {"id", "other"}


def test_src_test_boundary(tmp_path: Path) -> None:
    for sub in ("src/test", "src/testing"):
        directory = tmp_path / sub
        directory.mkdir(parents=True)
        (directory / "A.java").write_text('class A { String x = request.getParameter("q"); }\n')
    result = scan_repo(tmp_path, PACKS)
    assert {row.variable for row in result.rows} == {"q"}
    assert {row.file for row in result.rows} == {"src/testing/A.java"}


def test_locations_resolve() -> None:
    result = scan_repo(FIXTURE, PACKS)
    assert result.rows
    for row in result.rows:
        if row.variable.startswith("<"):
            continue
        line = (FIXTURE / row.file).read_text(encoding="utf-8").splitlines()[row.line - 1]
        assert row.variable in line, row
