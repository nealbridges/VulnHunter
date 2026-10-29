"""Java input-site pack: line/regex scanning plus one-level body expansion."""

from __future__ import annotations

import re
from pathlib import Path

from .common import Row, _skippable_dir
from .ts import _blank_block_comments, _blank_line_comments, _line_of

NAME = r"[A-Za-z_$][\w$]*"
_EXCLUDED_DIRS = frozenset({"test", "tests"})

_ANNOT = re.compile(
    r"@(?P<a>RequestParam|PathVariable|RequestHeader|CookieValue|RequestBody|RequestPart|Value)\b"
    r"(?P<args>\s*\([^)]*\))?"
)
_PARAM_TAIL = re.compile(r"([A-Za-z_$][\w$.<>\[\], ]*?)\s+(?P<n>[A-Za-z_$][\w$]*)\s*(?=[,)]|$)")
_ENTRY = re.compile(
    r"\b(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?"
    r"[\w$.<>\[\], ]*?[A-Za-z_$][\w$.<>\[\]]*\s+(?P<n>[A-Za-z_$][\w$]*)\s*\("
)
_GETTER = re.compile(r"\.\s*(?:getParameter|getParameterValues|getHeader)\s*\(\s*\"([^\"]+)\"\s*\)")
_ENV = re.compile(r"\bSystem\s*\.\s*getenv\s*\(\s*\"([^\"]+)\"\s*\)")
_ENV_NONLITERAL = re.compile(r"\bSystem\s*\.\s*getenv\s*\(\s*(?!\s*\")")
_MAPPING = re.compile(r"@(?:Get|Post|Put|Delete|Patch|Request)Mapping\s*\((?P<args>[^)]*)\)")
_QUOTED = re.compile(r"\"([^\"]+)\"")
_PATH_VAR = re.compile(r"\{(?P<n>[A-Za-z_$][\w$]*)(?::[^}]*)?\}")
_CLASS = re.compile(r"\b(?:class|record)\s+(?P<t>" + NAME + r")\b")
_RECORD_COMPONENT = re.compile(r"([\w$.<>\[\],\s]+?)\s+(?P<n>" + NAME + r")\s*(?=\s*[,)]|$)")
_GETTER_NONLITERAL = re.compile(
    r"\.\s*(?:getParameter|getParameterValues|getHeader)\s*\(\s*(?!\s*\")"
)
_FIELD = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|transient|volatile)\s+)*"
    r"[\w$.<>\[\], ]*?[A-Za-z_$][\w$.<>\[\]]*\s+(?P<n>" + NAME + r")\s*(?:=[^;]*)?;\s*$"
)


def excluded(relpath: str) -> bool:
    parts = relpath.split("/")
    return parts[:2] == ["src", "test"] or (
        parts[-1].endswith(".java") and any(part in _EXCLUDED_DIRS for part in parts[:-1])
    )


def _entry_forward(text: str, pos: int) -> str:
    match = _ENTRY.search(text, pos)
    return match.group("n") if match else "<module>"


def _entry_point(text: str, pos: int) -> str:
    name = ""
    for match in _ENTRY.finditer(text[:pos]):
        name = match.group("n")
    return name or "<module>"


def _annotation_name(args: str | None) -> str | None:
    if not args:
        return None
    for key in ("name", "value"):
        keyed = re.search(key + r"\s*=\s*\"([^\"]+)\"", args)
        if keyed:
            return keyed.group(1)
    body = args.strip()
    body = body[1:-1] if body.startswith("(") and body.endswith(")") else body
    positional = re.match(r'\s*"([^"]+)"', body)
    return positional.group(1) if positional else None


def _type_and_name(rest: str) -> tuple[str, str] | None:
    match = _PARAM_TAIL.search(rest)
    if not match:
        return None
    return match.group(1).strip(), match.group("n")


def _class_body(text: str, open_pos: int) -> tuple[str, int]:
    depth = 0
    for index in range(open_pos, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_pos:index], _line_of(text, open_pos)
    return text[open_pos:], _line_of(text, open_pos)


def _fields(body: str, base: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    depth = 1
    for offset, raw in enumerate(body.splitlines()):
        line = raw.split("//")[0].strip()
        if offset == 0:
            line = line.split("{", 1)[1] if "{" in line else line
        if depth == 1:
            for part in line.split(";"):
                plain = re.sub(r"@\w+(?:\([^)]*\))?", " ", part).strip()
                match = _FIELD.match(plain + ";") if plain else None
                if match:
                    out.append((base + offset, match.group("n")))
        depth += line.count("{") - line.count("}")
    return out


def _prepare_classes(repo: Path) -> dict[str, list[tuple[str, list[tuple[int, str]]]]]:
    classes: dict[str, list[tuple[str, list[tuple[int, str]]]]] = {}
    for path in sorted(repo.rglob("*.java")):
        rel = path.relative_to(repo).as_posix()
        if excluded(rel) or any(_skippable_dir(p) for p in rel.split("/")[:-1]):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for declaration in _CLASS.finditer(text):
            tail = text[declaration.start() :]
            record = re.match(r"record\s+" + NAME + r"\s*\((?P<args>[^)]*)\)", tail, re.DOTALL)
            if record:
                fields = [
                    (
                        _line_of(text, declaration.start() + record.start("args") + m.start("n")),
                        m.group("n"),
                    )
                    for m in _RECORD_COMPONENT.finditer(record.group("args"))
                ]
            else:
                body = _class_body(text, text.find("{", declaration.start()))
                fields = _fields(body[0], body[1])
            classes.setdefault(declaration.group("t"), []).append((rel, fields))
    return classes


class _Pack:
    name = "java"
    extensions: tuple[str, ...] = (".java",)
    classes: dict[str, list[tuple[str, list[tuple[int, str]]]]] = {}

    def prepare(self, repo: Path) -> None:
        self.classes = _prepare_classes(repo)

    excluded = staticmethod(excluded)

    def _body_rows(self, relpath: str, entry: str, line: int, type_name: str) -> list[Row]:
        matches = self.classes.get(type_name, [])
        if len(matches) != 1:
            return [Row("body field", relpath, line, "<body:unresolved>", entry, "http")]
        model_file, fields = matches[0]
        return [
            Row("body field", model_file, field_line, field_name, entry, "http")
            for field_line, field_name in fields
        ]

    def scan(self, relpath: str, text: str) -> tuple[list[Row], int]:
        clean = _blank_line_comments(_blank_block_comments(text))
        rows: list[Row] = []
        unresolved = len(_GETTER_NONLITERAL.findall(clean)) + len(_ENV_NONLITERAL.findall(clean))

        def emit(pos: int, kind: str, variable: str, trust: str = "http") -> None:
            rows.append(
                Row(kind, relpath, _line_of(clean, pos), variable, _entry_point(clean, pos), trust)
            )

        for match in _GETTER.finditer(clean):
            kind = "header" if "Header" in match.group(0) else "query param"
            emit(match.start(1), kind, match.group(1))
        for match in _ENV.finditer(clean):
            emit(match.start(1), "env var", match.group(1), "env")
        for mapping in _MAPPING.finditer(clean):
            for literal in _QUOTED.finditer(mapping.group("args")):
                if not literal.group(1).startswith("/"):
                    continue
                for segment in _PATH_VAR.finditer(literal.group(1)):
                    entry = _entry_forward(clean, mapping.end())
                    rows.append(
                        Row(
                            "path param",
                            relpath,
                            _line_of(
                                clean, mapping.start("args") + literal.start(1) + segment.start()
                            ),
                            segment.group("n"),
                            entry,
                            "http",
                        )
                    )
        for match in _ANNOT.finditer(clean):
            annotation = match.group("a")
            rest = clean[match.end() : match.end() + 200].lstrip()
            named = _annotation_name(match.group("args"))
            if annotation == "Value":
                if named and named.startswith("${"):
                    emit(match.start(), "config", named.strip("${}"), "env")
                continue
            if annotation == "RequestBody":
                resolved = _type_and_name(rest)
                if resolved is None:
                    unresolved += 1
                    continue
                type_name = resolved[0].rsplit(".", 1)[-1].strip("*")
                entry = _entry_point(clean, match.start())
                rows.extend(
                    self._body_rows(relpath, entry, _line_of(clean, match.start()), type_name)
                )
                continue
            parameter = named
            if parameter is None:
                resolved = _type_and_name(rest)
                if resolved is None:
                    unresolved += 1
                    continue
                parameter = resolved[1]
            if "MultipartFile" in rest.split(parameter)[0]:
                emit(match.start(), "file upload", parameter)
                continue
            kind = {
                "RequestParam": "query param",
                "RequestPart": "form field",
                "PathVariable": "path param",
                "RequestHeader": "header",
                "CookieValue": "cookie",
            }[annotation]
            emit(match.start(), kind, parameter)
        return rows, unresolved


def scan(relpath: str, text: str) -> tuple[list[Row], int]:
    return PACK.scan(relpath, text)


PACK = _Pack()
