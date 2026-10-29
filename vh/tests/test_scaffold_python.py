"""Python pack: every pattern in plan §3.2, model fields and exclusions."""

from __future__ import annotations

from pathlib import Path

import pytest

from vh.scaffold import PACKS, scan_repo
from vh.scaffold import python as py

FIXTURE = Path(__file__).parent / "fixtures" / "scaffold" / "py_app"

PY_CASES = [
    ('@app.route("/users/<int:uid>")\ndef f():\n    pass', "path param", "uid"),
    ('@router.get("/items/{item_id}")\ndef f():\n    pass', "path param", "item_id"),
    ('path("users/<int:pk>/", view)', "path param", "pk"),
    ('re_path(r"^tags/(?P<slug>[\\w-]+)/$", view)', "path param", "slug"),
    ('request.args.get("name")', "query param", "name"),
    ('request.args["tag"]', "query param", "tag"),
    ('request.query_params.get("q")', "query param", "q"),
    ('request.GET.get("old")', "query param", "old"),
    ('request.GET["old2"]', "query param", "old2"),
    ('request.form.get("form")', "form field", "form"),
    ('request.form["form2"]', "form field", "form2"),
    ('request.POST.get("post")', "form field", "post"),
    ('request.POST["post2"]', "form field", "post2"),
    ('request.headers.get("Authorization")', "header", "Authorization"),
    ('request.headers["X-Key"]', "header", "X-Key"),
    ('request.META.get("HTTP_X_FORWARDED_FOR")', "header", "HTTP_X_FORWARDED_FOR"),
    ('request.cookies.get("session")', "cookie", "session"),
    ('request.COOKIES.get("theme")', "cookie", "theme"),
    ('request.get_json()["email"]', "body field", "email"),
    ('request.get_json().get("phone")', "body field", "phone"),
    ('request.json["role"]', "body field", "role"),
    ('request.json.get("scope")', "body field", "scope"),
    ('request.data["raw"]', "body field", "raw"),
    ("def f(q: str = Query(...)):\n    pass", "query param", "q"),
    ("def f(p: str = Path(...)):\n    pass", "path param", "p"),
    ("def f(h: str = Header(...)):\n    pass", "header", "h"),
    ("def f(c: str = Cookie(...)):\n    pass", "cookie", "c"),
    ("def f(f: str = Form(...)):\n    pass", "form field", "f"),
    ('os.environ["HOME"]', "env var", "HOME"),
    ('os.environ.get("API_KEY")', "env var", "API_KEY"),
    ('os.getenv("TOKEN")', "env var", "TOKEN"),
    ('parser.add_argument("--verbose")', "cli flag", "--verbose"),
    ('parser.add_argument("positional")', "cli flag", "positional"),
    ('@click.option("--flag")\ndef f():\n    pass', "cli flag", "--flag"),
    ('request.args.get("name", "")', "query param", "name"),
    ('os.environ.get("HOME", "")', "env var", "HOME"),
    ('request.json.get("email", None)', "body field", "email"),
    ('path("users/<str:pk>/", view)', "path param", "pk"),
    ('path("t/<slug:slug>/", view)', "path param", "slug"),
]


@pytest.mark.parametrize(("snippet", "kind", "variable"), PY_CASES)
def test_each_pattern_row(snippet: str, kind: str, variable: str) -> None:
    rows, _ = py.PACK.scan("app.py", snippet)
    assert (kind, variable) in [(row.source_type, row.variable) for row in rows]


def test_body_expansion() -> None:
    result = scan_repo(FIXTURE, PACKS)
    body = [row for row in result.rows if row.source_type == "body field"]
    assert {row.variable for row in body} >= {"username", "email", "role", "scope"}
    assert "<body:unresolved>" in {row.variable for row in body}
    model_rows = [
        row for row in body if row.file == "models.py" and row.variable in {"username", "email"}
    ]
    assert {row.entry_point for row in model_rows} == {"login", "optional"}


def test_comments_ignored() -> None:
    text = '# request.args.get("ghost")\nreal = request.args.get("real")'
    rows, _ = py.PACK.scan("app.py", text)
    assert [row.variable for row in rows] == ["real"]


def test_excluded_files() -> None:
    result = scan_repo(FIXTURE, PACKS)
    files = {row.file for row in result.rows}
    assert "handlers_test.py" not in files
    assert "tests/helper.py" not in files
    assert "migrations/0001.py" not in files
    assert "handlers.py" in files


@pytest.mark.parametrize(
    "snippet",
    [
        "request.args.get(name)",
        "request.args[name]",
        "os.environ[name]",
        "os.getenv(name)",
        "path(pattern, view)",
        "@app.route(path)\ndef f():\n    pass",
        "request.get_json().get(name)",
        "request.get_json()[name]",
        "parser.add_argument(name)",
        "@click.option(name)\ndef f():\n    pass",
    ],
)
def test_non_literal_counted_not_rowed(snippet: str) -> None:
    rows, unresolved = py.PACK.scan("app.py", snippet)
    assert rows == []
    assert unresolved == 1


def test_call_form_decorator_and_union_annotations(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "models.py").write_text(
        "from dataclasses import dataclass\n\n"
        "@dataclass(frozen=True)\nclass Login:\n    username: str\n    email: str\n\n"
        "@deco(1)\nclass Plain:\n    pass\n"
    )
    (pkg / "app.py").write_text(
        "from typing import Optional\nfrom models import Login\n\n"
        '@router.post("/login")\ndef login(body: Optional[Login], other: Login | None):\n'
        "    return body\n"
    )
    result = scan_repo(tmp_path, PACKS)
    assert {row.variable for row in result.rows if row.source_type == "body field"} == {
        "username",
        "email",
    }


def test_indirect_model_and_union_annotation(tmp_path: Path) -> None:
    (tmp_path / "models.py").write_text(
        "from pydantic import BaseModel\n\n"
        "class User(BaseModel):\n    username: str\n    email: str\n\n"
        "class UserIn(User):\n    password: str\n"
    )
    (tmp_path / "app.py").write_text(
        "from typing import Union\nfrom models import UserIn\n\n"
        '@router.post("/login")\ndef login(body: Union[UserIn, None]):\n    return body\n'
    )
    result = scan_repo(tmp_path, PACKS)
    assert {row.variable for row in result.rows if row.source_type == "body field"} == {
        "username",
        "email",
        "password",
    }


def test_duplicate_class_names_prefer_model(tmp_path: Path) -> None:
    (tmp_path / "a_plain.py").write_text("class User:\n    pass\n")
    (tmp_path / "b_model.py").write_text(
        "from pydantic import BaseModel\n\nclass User(BaseModel):\n    username: str\n    email: str\n"
    )
    (tmp_path / "app.py").write_text(
        '@router.post("/x")\ndef route(body: User):\n    return body\n'
    )
    result = scan_repo(tmp_path, PACKS)
    assert {row.variable for row in result.rows if row.source_type == "body field"} == {
        "username",
        "email",
    }


def test_non_route_parameter_not_expanded(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "class Session:\n    pass\n\nclass User:\n    pass\n\n"
        "def helper(db: Session, user: User):\n    return db\n"
    )
    result = scan_repo(tmp_path, PACKS)
    assert [row for row in result.rows if row.source_type == "body field"] == []


def test_locations_resolve() -> None:
    result = scan_repo(FIXTURE, PACKS)
    assert result.rows
    for row in result.rows:
        if row.variable.startswith("<"):
            continue
        line = (FIXTURE / row.file).read_text(encoding="utf-8").splitlines()[row.line - 1]
        assert row.variable.lstrip("-") in line, row
