"""Go pack: every pattern in plan §3.1, body expansion and exclusions."""

from __future__ import annotations

from pathlib import Path

import pytest

from vh.scaffold import PACKS, go, render, scan_repo

FIXTURE = Path(__file__).parent / "fixtures" / "scaffold" / "go_app"
MIXED = Path(__file__).parent / "fixtures" / "scaffold" / "mixed"

GO_CASES = [
    ('r.URL.Query().Get("term")', "query param", "term"),
    ('r.Query("raw")', "query param", "raw"),
    ('r.DefaultQuery("page", "1")', "query param", "page"),
    ('r.QueryParam("sort")', "query param", "sort"),
    ('r.PathValue("id")', "path param", "id"),
    ('r.Param("pid")', "path param", "pid"),
    ('chi.URLParam(r, "uid")', "path param", "uid"),
    ('mux.Vars(r)["mid"]', "path param", "mid"),
    ('r.HandleFunc("/users/{id}", h)', "path param", "id"),
    ('r.GET("/items/{itemId:[0-9]+}", h)', "path param", "itemId"),
    ('r.POST("/files/{filePath...}", h)', "path param", "filePath"),
    ('r.DELETE("/legacy/:legacyId", h)', "path param", "legacyId"),
    ('r.Header.Get("Authorization")', "header", "Authorization"),
    ('r.GetHeader("X-Key")', "header", "X-Key"),
    ('r.FormValue("name")', "form field", "name"),
    ('r.PostFormValue("post")', "form field", "post"),
    ('r.PostForm("multi")', "form field", "multi"),
    ('os.Getenv("HOME")', "env var", "HOME"),
    ('os.LookupEnv("SECRET")', "env var", "SECRET"),
    ('flag.String("verbose", false, "")', "cli flag", "--verbose"),
    ('flag.IntVar(&x, "count", 1, "")', "cli flag", "--count"),
    ('cmd.Flags().StringP("out", "o", "", "")', "cli flag", "--out"),
    ('cmd.PersistentFlags().BoolVarP(&b, "debug", "d", false, "")', "cli flag", "--debug"),
    ('v := mux.Vars(r)\n_ = v["tenant"]', "path param", "tenant"),
    (
        'runtime.BindQueryParameterWithOptions("form", true, false, "limit", r.URL.Query(), &p.Limit, o)',
        "query param",
        "limit",
    ),
]


@pytest.mark.parametrize(("snippet", "kind", "variable"), GO_CASES)
def test_each_pattern_row(snippet: str, kind: str, variable: str) -> None:
    rows, _ = go.scan("app.go", snippet)
    assert (kind, variable) in [(row.source_type, row.variable) for row in rows]


def test_body_expansion() -> None:
    result = scan_repo(FIXTURE, PACKS)
    rows = [row for row in result.rows if row.source_type == "body field"]
    pairs = {(row.variable, row.entry_point) for row in rows}
    assert ("username", "handleSearch") in pairs
    assert ("Email", "handleSearch") in pairs
    assert ("Base", "handleSearch (embedded, not expanded)") in pairs
    assert ("Inner", "handleSearch (nested: Inner, not expanded)") in pairs
    assert ("A", "handleSearch") in pairs and ("B", "handleSearch") in pairs
    assert "Pass" not in {row.variable for row in rows}
    assert "<body:unresolved>" in {row.variable for row in rows}
    assert ("Anon", "handleSearch") in pairs
    assert "Deep" not in {row.variable for row in rows}
    assert ("Nested", "handleSearch (nested: Inner, not expanded)") in pairs
    assert "secret" not in {row.variable for row in rows}


def test_comments_ignored() -> None:
    text = '/* r.Query("ghost") */\n// r.Query("lineghost")\n_ = r.Query("real")'
    rows, _ = go.scan("app.go", text)
    assert [row.variable for row in rows] == ["real"]


def test_excluded_files() -> None:
    result = scan_repo(FIXTURE, PACKS)
    files = {row.file for row in result.rows}
    assert not any(name.endswith("_test.go") for name in files)
    assert not any(name.startswith("testdata/") for name in files)
    assert "handlers.go" in files


@pytest.mark.parametrize(
    "snippet",
    [
        "r.QueryParam(name)",
        "r.Header.Get(name)",
        "chi.URLParam(r, name)",
        "mux.Vars(r)[name]",
        'flag.String(name, "", "")',
        "r.URL.Query().Get(name)",
        "r.HandleFunc(path, h)",
        "r.GET(path, h)",
        "v := mux.Vars(r)\n_ = v[name]",
    ],
)
def test_non_literal_counted_not_rowed(snippet: str) -> None:
    rows, unresolved = go.scan("app.go", snippet)
    assert rows == []
    assert unresolved == 1


def test_grouped_and_tagged_structs(tmp_path: Path) -> None:
    (tmp_path / "types.go").write_text(
        'package p\n\ntype (\n\tLogin struct {\n\t\tBase `json:"base"`\n\t\tName string `json:"name"`\n\t}\n)\n'
    )
    (tmp_path / "handler.go").write_text(
        "package p\n\nfunc handle(r *http.Request) {\n\tvar v Login\n\tjson.NewDecoder(r.Body).Decode(&v)\n}\n"
    )
    rows = [row for row in scan_repo(tmp_path, PACKS).rows if row.source_type == "body field"]
    assert {row.variable for row in rows} == {"Base", "name"}


def test_one_line_anonymous_struct(tmp_path: Path) -> None:
    (tmp_path / "types.go").write_text(
        'package p\n\ntype T struct { Meta struct{ A string }; B string `json:"b"`; C string `json:"c"` }\n'
    )
    (tmp_path / "handler.go").write_text(
        "package p\n\nfunc handle(r *http.Request) {\n\tvar v T\n\tjson.NewDecoder(r.Body).Decode(&v)\n}\n"
    )
    rows = [row for row in scan_repo(tmp_path, PACKS).rows if row.source_type == "body field"]
    assert {row.variable for row in rows} == {"Meta", "b", "c"}


def test_one_line_struct(tmp_path: Path) -> None:
    (tmp_path / "types.go").write_text(
        'package p\n\ntype Tiny struct { A string `json:"a"`; B string `json:"b"` }\n'
    )
    (tmp_path / "handler.go").write_text(
        "package p\n\nfunc handle(r *http.Request) {\n\tvar v Tiny\n\tr.BindJSON(&v)\n}\n"
    )
    rows = [row for row in scan_repo(tmp_path, PACKS).rows if row.source_type == "body field"]
    assert {row.variable for row in rows} == {"a", "b"}


def test_alias_body_resolved_and_response_skipped(tmp_path: Path) -> None:
    (tmp_path / "types.go").write_text(
        "package p\n\ntype AddItemJSONRequestBody = AddItemRequest\n\ntype (\n\tRenameBody = RenameRequest\n)\n\n"
        'type AddItemRequest struct { Title string `json:"title"` }\n\n'
        'type RenameRequest struct { Label string `json:"label"` }\n'
    )
    (tmp_path / "handler.go").write_text(
        "package p\n\nfunc add(r *http.Request) {\n\tvar body AddItemJSONRequestBody\n"
        "\tjson.NewDecoder(r.Body).Decode(&body)\n}\n\nfunc rename(r *http.Request) {\n"
        "\tvar body RenameBody\n\tjson.NewDecoder(r.Body).Decode(&body)\n}\n\n"
        "func fetch(resp *http.Response) {\n\tvar out AddItemRequest\n"
        "\tjson.NewDecoder(resp.Body).Decode(&out)\n}\n"
    )
    rows = [row for row in scan_repo(tmp_path, PACKS).rows if row.source_type == "body field"]
    assert sorted((row.variable, row.entry_point) for row in rows) == [
        ("label", "rename"),
        ("title", "add"),
    ]


def test_literal_query_not_counted() -> None:
    rows, unresolved = go.scan("app.go", 'r.URL.Query().Get("term")')
    assert [row.variable for row in rows] == ["term"]
    assert unresolved == 0


def test_locations_resolve() -> None:
    result = scan_repo(FIXTURE, PACKS)
    assert result.rows
    for row in result.rows:
        if row.variable.startswith("<"):
            continue
        line = (FIXTURE / row.file).read_text(encoding="utf-8").splitlines()[row.line - 1]
        assert row.variable.lstrip("-") in line, row


def test_mixed_repo_lists_all_packs() -> None:
    result = scan_repo(MIXED, PACKS)
    assert result.packs == ["ts", "go", "python", "java"]
    assert "Packs: ts, go, python, java" in render(result)
