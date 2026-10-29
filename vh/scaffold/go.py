"""Go input-site pack: line/regex scanning plus one-level body expansion."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .common import Row, _skippable_dir
from .ts import _blank_block_comments, _blank_line_comments, _line_of

NAME = r"[A-Za-z_]\w*"
_STRING = r"[\"`]([^\"`]+)[\"`]"
_FLAG_TYPES = "String|Int|Int64|Uint|Uint64|Bool|Float64|Duration|Func"

_TYPE_DECL = re.compile(
    r"\b(?:var\s+(?P<n1>" + NAME + r")\s+(?P<t1>[A-Za-z_][\w.]*)"
    r"|(?P<n2>" + NAME + r")\s*:=\s*&?(?P<t2>[A-Za-z_][\w.]*)\s*\{)"
)
_STRUCT = re.compile(r"\btype\s+(?P<t>" + NAME + r")\s+struct\s*\{")
_ENTRY = re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?(?P<n>" + NAME + r")\s*\(")
_DECODE = re.compile(
    r"(?:json\s*\.\s*NewDecoder\s*\((?P<src>[^)]*)\)\s*\.\s*Decode|\.\s*"
    r"(?:ShouldBindJSON|BindJSON|ShouldBind|Bind))\s*\(\s*&\s*(?P<v>" + NAME + r")\s*\)"
)
_QUERY = re.compile(
    r"(?:(?:\.\s*URL\s*\.\s*Query\s*\(\s*\)\s*\.\s*Get)"
    r"|\.\s*(?:Query|DefaultQuery|QueryParam))\s*\(\s*" + _STRING
)
_RESPONSE = re.compile(r"\b(?:resp|res|response)\s*\.\s*Body\b")
_ALIAS = re.compile(
    r"^\s*(?:type\s+)?(?P<a>" + NAME + r")\s*=\s*\*?(?P<b>[A-Za-z_][\w.]*)\s*$", re.M
)
_BIND_QUERY = re.compile(r"BindQueryParameter\w*\s*\(\s*\"[^\"]*\"\s*,[^,]+,[^,]+,\s*" + _STRING)
_PATH = re.compile(r"\.\s*(?:PathValue|Param)\s*\(\s*" + _STRING)
_CHI = re.compile(r"chi\s*\.\s*URLParam\s*\(\s*[^,]+,\s*" + _STRING)
_MUX_VARS = re.compile(r"mux\s*\.\s*Vars\s*\(\s*[^)]*\)\s*\[\s*" + _STRING)
_VARS_ASSIGN = re.compile(r"(?P<v>" + NAME + r")\s*:=\s*mux\s*\.\s*Vars\s*\(")
_ROUTE_CALL = re.compile(
    r"\.\s*(?:HandleFunc|Handle|GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete)"
    r"\s*\(\s*[\"`](/[^\"`]*)[\"`]"
)
_ROUTE_PARAM = re.compile(
    r"(?<!:):(?!:)(?P<c>" + NAME + r")|\{(?P<b>" + NAME + r")(?::[^}]*)?(?:\.\.\.)?\}"
)
_HEADER = re.compile(r"\.\s*(?:Header\s*\.\s*Get|GetHeader)\s*\(\s*" + _STRING)
_FORM = re.compile(r"\.\s*(?:FormValue|PostFormValue|PostForm)\s*\(\s*" + _STRING)
_ENV = re.compile(r"\bos\s*\.\s*(?:Getenv|LookupEnv)\s*\(\s*" + _STRING)
_FLAG_FIRST = re.compile(
    r"(?:flag\s*\.|\.\s*(?:Flags|PersistentFlags)\s*\(\s*\)\s*\.)\s*"
    r"(?:" + _FLAG_TYPES + r")(?:P)?\s*\(\s*" + _STRING
)
_FLAG_VAR = re.compile(
    r"(?:flag\s*\.|\.\s*(?:Flags|PersistentFlags)\s*\(\s*\)\s*\.)\s*"
    r"(?:" + _FLAG_TYPES + r")(?:Var|VarP)\s*\(\s*[^,]+,\s*" + _STRING
)
_FIELD = re.compile(
    r"^\s*(?P<names>" + NAME + r"(?:\s*,\s*" + NAME + r")*)\s+(?P<type>[^\s`]+)"
    r"(?:\s+`(?P<tag>[^`]*)`)?\s*$"
)
_EMBEDDED = re.compile(r"^\s*\*?(?P<t>" + NAME + r")(?:\s+`[^`]*`)?\s*$")
_TYPE_GROUP = re.compile(r"\btype\s*\(")
_NONLITERALS = (
    re.compile(
        r"\.\s*(?:Query|DefaultQuery|QueryParam|PathValue|Param|FormValue|PostFormValue|PostForm"
        r"|GetHeader|Header\s*\.\s*Get)\s*\(\s*(?!\s*[\"`])(?!\s*\))"
    ),
    re.compile(r"\.\s*URL\s*\.\s*Query\s*\(\s*\)\s*\.\s*Get\s*\(\s*(?!\s*[\"`])"),
    re.compile(r"chi\s*\.\s*URLParam\s*\(\s*[^,]+,\s*(?!\s*[\"`])"),
    re.compile(r"mux\s*\.\s*Vars\s*\(\s*[^)]*\)\s*\[\s*(?!\s*['\"])"),
    re.compile(r"\bos\s*\.\s*(?:Getenv|LookupEnv)\s*\(\s*(?!\s*[\"`])"),
    re.compile(
        r"(?:flag\s*\.|\.\s*(?:Flags|PersistentFlags)\s*\(\s*\)\s*\.)\s*"
        r"(?:" + _FLAG_TYPES + r")(?:P)?\s*\(\s*(?!\s*[\"`])"
    ),
    re.compile(
        r"(?:flag\s*\.|\.\s*(?:Flags|PersistentFlags)\s*\(\s*\)\s*\.)\s*"
        r"(?:" + _FLAG_TYPES + r")(?:Var|VarP)\s*\(\s*[^,]+,\s*(?!\s*[\"`])"
    ),
    re.compile(r"\.\s*(?:HandleFunc|Handle|GET|POST|PUT|PATCH|DELETE)\s*\(\s*(?!\s*[\"`])"),
)
_ANON = re.compile(r"^(?P<names>" + NAME + r"(?:\s*,\s*" + NAME + r")*)\s+struct\s*\{")


def excluded(relpath: str) -> bool:
    return relpath.endswith("_test.go") or "testdata" in relpath.split("/")[:-1]


def _entry_point(text: str, pos: int) -> str:
    name = ""
    for match in _ENTRY.finditer(text[:pos]):
        name = match.group("n")
    return name or "<module>"


def _base_type(value: str) -> str:
    while True:
        value = value.lstrip("*")
        if value.startswith("[]"):
            value = value[2:]
            continue
        mapped = re.match(r"map\[[^\]]*\]\s*(.+)", value)
        if not mapped:
            return value
        value = mapped.group(1)


def _close_brace(text: str, open_pos: int) -> int:
    depth = 0
    for index in range(open_pos, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _fields(body: str, base_line: int) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    depth = 1
    body = body.replace(";", "\n")
    for offset, raw in enumerate(body.splitlines()):
        line = raw.split("//")[0].strip()
        if offset == 0:
            line = line.split("{", 1)[1].strip() if "{" in line else ""
        if depth > 1:
            depth += line.count("{") - line.count("}")
            continue
        if not line:
            continue
        anonymous = _ANON.match(line)
        if anonymous:
            for name in (part.strip() for part in anonymous.group("names").split(",")):
                out.append((base_line + offset, name, "struct"))
            depth = 1 + line.count("{") - line.count("}")
            continue
        embedded = _EMBEDDED.match(line)
        if embedded:
            out.append((base_line + offset, embedded.group("t"), "embedded"))
            continue
        field = _FIELD.match(line)
        if not field:
            continue
        tag = re.search(r'json:"([^"]*)"', field.group("tag") or "")
        for name in (part.strip() for part in field.group("names").split(",")):
            variable = name
            if tag:
                first = tag.group(1).split(",")[0]
                if first == "-":
                    continue
                variable = first or name
            out.append((base_line + offset, variable, field.group("type")))
    return out


class _Pack:
    name = "go"
    extensions: tuple[str, ...] = (".go",)

    def __init__(self) -> None:
        self.structs: dict[tuple[str, str], tuple[str, list[tuple[int, str, str]]]] = {}
        self.aliases: dict[tuple[str, str], str] = {}

    def prepare(self, repo: Path) -> None:
        self.structs, self.aliases = {}, {}
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if not _skippable_dir(d)]
            root_path = Path(root)
            rel_dir = "/".join(root_path.relative_to(repo).parts)
            for name in files:
                rel = f"{rel_dir}/{name}" if rel_dir else name
                if not name.endswith(".go") or excluded(rel):
                    continue
                try:
                    text = (root_path / name).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                # `type A = B` (oapi-codegen request bodies); also bare members of `type (...)`.
                for alias in _ALIAS.finditer(text):
                    line = text[alias.start() : alias.end()].lstrip()
                    in_group = text.rfind("type (", 0, alias.start()) > text.rfind(
                        "\n)", 0, alias.start()
                    )
                    if line.startswith("type ") or in_group:
                        self.aliases[(rel_dir, alias.group("a"))] = alias.group("b").rsplit(".", 1)[
                            -1
                        ]
                for struct in _STRUCT.finditer(text):
                    open_pos = text.find("{", struct.start())
                    end = _close_brace(text, open_pos)
                    if end < 0:
                        continue
                    fields = _fields(text[open_pos:end], _line_of(text, open_pos))
                    if fields:
                        self.structs[(rel_dir, struct.group("t"))] = (rel, fields)
                for group in _TYPE_GROUP.finditer(text):
                    close = text.find("\n)", group.end())
                    if close < 0:
                        close = len(text)
                    for member in re.finditer(
                        r"^\s*(?P<t>" + NAME + r")\s+struct\s*\{",
                        text[group.end() : close],
                        re.MULTILINE,
                    ):
                        open_pos = group.end() + text[group.end() + member.start() :].find("{")
                        end = _close_brace(text, open_pos)
                        if end < 0:
                            continue
                        fields = _fields(text[open_pos:end], _line_of(text, open_pos))
                        if fields:
                            self.structs[(rel_dir, member.group("t"))] = (rel, fields)

    def excluded(self, relpath: str) -> bool:
        return excluded(relpath)

    def _body_rows(self, relpath: str, entry: str, line: int, type_name: str) -> list[Row]:
        dirname = relpath.rsplit("/", 1)[0] if "/" in relpath else ""
        type_name = self.aliases.get((dirname, type_name), type_name)
        found = self.structs.get((dirname, type_name))
        if found is None:
            return [Row("body field", relpath, line, "<body:unresolved>", entry, "http")]
        struct_file, fields = found
        rows = []
        for field_line, variable, ftype in fields:
            suffix = ""
            if ftype == "embedded":
                suffix = " (embedded, not expanded)"
            elif (dirname, _base_type(ftype)) in self.structs:
                suffix = f" (nested: {_base_type(ftype)}, not expanded)"
            rows.append(
                Row("body field", struct_file, field_line, variable, entry + suffix, "http")
            )
        return rows

    def scan(self, relpath: str, text: str) -> tuple[list[Row], int]:
        clean = _blank_line_comments(_blank_block_comments(text))
        rows: list[Row] = []
        unresolved = sum(len(pattern.findall(clean)) for pattern in _NONLITERALS)

        def emit(pos: int, kind: str, variable: str, trust: str = "http") -> None:
            rows.append(
                Row(kind, relpath, _line_of(clean, pos), variable, _entry_point(clean, pos), trust)
            )

        for pattern, kind in (
            (_QUERY, "query param"),
            (_BIND_QUERY, "query param"),
            (_PATH, "path param"),
            (_CHI, "path param"),
            (_MUX_VARS, "path param"),
            (_HEADER, "header"),
            (_FORM, "form field"),
            (_ENV, "env var"),
        ):
            for match in pattern.finditer(clean):
                emit(match.start(1), kind, match.group(1), "env" if kind == "env var" else "http")
        for match in _FLAG_FIRST.finditer(clean):
            emit(match.start(1), "cli flag", "--" + match.group(1).lstrip("-"))
        for match in _FLAG_VAR.finditer(clean):
            emit(match.start(1), "cli flag", "--" + match.group(1).lstrip("-"))
        for match in _ROUTE_CALL.finditer(clean):
            for param in _ROUTE_PARAM.finditer(match.group(1)):
                emit(
                    match.start(1) + param.start(),
                    "path param",
                    param.group("c") or param.group("b"),
                )
        for assign in _VARS_ASSIGN.finditer(clean):
            var = assign.group("v")
            chunk = clean[assign.end() :].split("\nfunc ", 1)[0]
            for match in re.finditer(r"\b" + re.escape(var) + r'\s*\[\s*"([^"]+)"\s*\]', chunk):
                emit(assign.end() + match.start(1), "path param", match.group(1))
            unresolved += sum(
                1 for _ in re.finditer(r"\b" + re.escape(var) + r"\s*\[\s*(?!\s*\")", chunk)
            )
        for match in _DECODE.finditer(clean):
            if _RESPONSE.search(match.group("src") or ""):
                continue  # decoding an outbound call's response, not request input
            var = match.group("v")
            decl = None
            func_start = clean.rfind("\nfunc ", 0, match.start())
            scope = clean[func_start if func_start >= 0 else 0 : match.start()]
            for candidate in _TYPE_DECL.finditer(scope):
                if var in (candidate.group("n1"), candidate.group("n2")):
                    decl = candidate
            type_name = ""
            if decl:
                type_name = (decl.group("t1") or decl.group("t2")).rsplit(".", 1)[-1]
            entry = _entry_point(clean, match.start())
            rows.extend(self._body_rows(relpath, entry, _line_of(clean, match.start()), type_name))
        return rows, unresolved


def scan(relpath: str, text: str) -> tuple[list[Row], int]:
    return PACK.scan(relpath, text)


PACK = _Pack()
