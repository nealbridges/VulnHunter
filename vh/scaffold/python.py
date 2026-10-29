"""Python input-site pack: stdlib `ast`, no regex for syntax."""

import ast
import re
from pathlib import Path

from .common import Row, _skippable_dir

_DIRS = ("tests", "test", "venv", ".venv", "site-packages", "migrations")
_ROUTE = frozenset({"route", "get", "post", "put", "patch", "delete", "api_route"})
_PARAM_NAMES = ("Query", "Path", "Header", "Cookie", "Form")
_PARAM_KINDS = ("query param", "path param", "header", "cookie", "form field")
_SEG = re.compile(r"<(?:(?P<c>[a-z]+):)?(?P<a>\w+)>|\{(?P<b>\w+)\}|\(\?P<(?P<n>\w+)>")
_REQ = {
    **dict.fromkeys(("args", "query_params", "GET"), "query param"),
    **dict.fromkeys(("form", "POST"), "form field"),
    **dict.fromkeys(("headers", "META"), "header"),
    **dict.fromkeys(("cookies", "COOKIES"), "cookie"),
    **dict.fromkeys(("json", "data"), "body field"),
}


def excluded(relpath: str) -> bool:
    parts = relpath.split("/")
    name = parts[-1]
    skipped = name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py")
    return skipped or any(part in _DIRS for part in parts[:-1])


def _string(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _chain(node):
    out = []
    while isinstance(node, ast.Attribute):
        out.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        out.append(node.id)
    return out[::-1]


def _anno(node):
    if isinstance(node, ast.BinOp):
        return next((n for n in map(_anno, (node.left, node.right)) if n and n != "None"), "")
    if isinstance(node, ast.Subscript):
        return _anno(node.slice.elts[0]) if isinstance(node.slice, ast.Tuple) else _anno(node.slice)
    return (_chain(node) or [""])[-1]


def _prepare(repo: Path):
    classes = {}
    for path in sorted(repo.rglob("*.py")):
        rel = path.relative_to(repo).as_posix()
        if excluded(rel) or any(_skippable_dir(p) for p in rel.split("/")[:-1]):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef):
                bases = {(_chain(b) or [""])[-1] for b in n.bases}
                decs = [
                    (_chain(d.func if isinstance(d, ast.Call) else d) or [""])[-1]
                    for d in n.decorator_list
                ]
                if n.name not in classes or "dataclass" in decs or "BaseModel" in bases:
                    members = [
                        (i.lineno, i.target.id)
                        for i in n.body
                        if isinstance(i, ast.AnnAssign) and isinstance(i.target, ast.Name)
                    ]
                    classes[n.name] = (rel, members, bases, decs)
    fields: dict[str, tuple[str, list[tuple[int, str]]]] = {}
    for _ in range(len(classes)):
        for name, (rel, members, bases, decs) in list(classes.items()):
            if "dataclass" in decs or "BaseModel" in bases or any(b in fields for b in bases):
                inherited = [m for b in bases for m in fields.get(b, (rel, []))[1]]
                fields[name] = (rel, inherited + members)
                classes.pop(name)
    return fields


class _Visitor(ast.NodeVisitor):
    def __init__(self, relpath, models):
        self.relpath = relpath
        self.models = models
        self.rows, self.unresolved, self.ancestors = [], 0, {}

    def _emit(self, node, kind, variable, trust="http"):
        owner = self.ancestors.get(node)
        while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = self.ancestors.get(owner)
        entry = owner.name if owner is not None else "<module>"
        self.rows.append(Row(kind, self.relpath, node.lineno, variable, entry, trust))

    def _arg(self, node):
        literal = _string(node.args[0]) if node.args else None
        if node.args and literal is None:
            self.unresolved += 1
        return literal

    def generic_visit(self, node):
        for child in ast.iter_child_nodes(node):
            self.ancestors[child] = node
        super().generic_visit(node)

    def _function(self, node):
        for child in ast.iter_child_nodes(node):
            self.ancestors[child] = node
        plain = node.args.args[-len(node.args.defaults) :]
        defaults = {a.arg: d for a, d in zip(plain, node.args.defaults, strict=False)}
        for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False):
            if d is not None:
                defaults[a.arg] = d
        route = False
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            chain = _chain(dec.func)
            attr = chain[-1] if chain else ""
            route = route or attr in _ROUTE
            if attr in _ROUTE or attr in ("path", "re_path"):
                literal = _string(dec.args[0]) if dec.args else None
                if literal is None and dec.args:
                    self.unresolved += 1
                if literal:
                    for segment in [
                        m.group("a") or m.group("b") or m.group("n") for m in _SEG.finditer(literal)
                    ]:
                        self.rows.append(
                            Row("path param", self.relpath, dec.lineno, segment, node.name, "http")
                        )
        for arg in [*node.args.args, *node.args.kwonlyargs]:
            self._parameter(node, arg, defaults.get(arg.arg), route)
        self.generic_visit(node)

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def _parameter(self, node, arg, default, route):
        if isinstance(default, ast.Call):
            chain = _chain(default.func)
            if chain and chain[-1] in _PARAM_NAMES:
                self.rows.append(
                    Row(
                        _PARAM_KINDS[_PARAM_NAMES.index(chain[-1])],
                        self.relpath,
                        arg.lineno,
                        arg.arg,
                        node.name,
                        "http",
                    )
                )
        if arg.annotation is None:
            return
        simple = _anno(arg.annotation)
        model = self.models.get(simple) if route else None
        if model is not None:
            model_file, fields = model
            self.rows.extend(
                Row("body field", model_file, line, name, node.name, "http")
                for line, name in fields
            )
        elif route and simple[:1].isupper():
            self.rows.append(
                Row("body field", self.relpath, arg.lineno, "<body:unresolved>", node.name, "http")
            )
            self.unresolved += 1

    def visit_Call(self, node):
        chain = _chain(node.func)
        attr = chain[-1] if chain else ""
        owner = node.func.value if isinstance(node.func, ast.Attribute) else None
        if (
            attr == "get"
            and isinstance(owner, ast.Call)
            and _chain(owner.func)[-1:] == ["get_json"]
        ):
            literal = self._arg(node)
            if literal:
                self._emit(node, "body field", literal)
        elif attr == "get" and node.args:
            literal = _string(node.args[0])
            if literal is not None:
                receiver = chain[:-1]
                if receiver[-2:] == ["os", "environ"] or receiver == ["os"]:
                    self._emit(node, "env var", literal, "env")
                elif len(receiver) >= 2 and receiver[-2] == "request":
                    kind = _REQ.get(receiver[-1])
                    if kind:
                        self._emit(node, kind, literal)
            elif (len(chain) >= 3 and chain[-3] == "request") or chain[-3:-1] == ["os", "environ"]:
                self.unresolved += 1
        elif attr == "getenv" and chain[:-1] == ["os"]:
            literal = self._arg(node)
            if literal:
                self._emit(node, "env var", literal, "env")
        elif attr in ("add_argument", "option"):
            literal = self._arg(node)
            if literal:
                self._emit(node, "cli flag", literal)
        elif attr in ("path", "re_path"):
            literal = self._arg(node)
            if literal:
                for segment in [
                    m.group("a") or m.group("b") or m.group("n") for m in _SEG.finditer(literal)
                ]:
                    self._emit(node, "path param", segment)
        self.generic_visit(node)

    def visit_Subscript(self, node):
        literal = _string(node.slice)
        chain = _chain(node.value)
        is_json = isinstance(node.value, ast.Call) and _chain(node.value.func)[-1:] == ["get_json"]
        if literal is None:
            unknown = (
                is_json or chain[-1:] == ["environ"] or (len(chain) >= 2 and chain[-2] == "request")
            )
            self.unresolved += unknown
            self.generic_visit(node)
            return
        kind = (
            "env var"
            if chain[-1:] == ["environ"]
            else _REQ.get(chain[-1] if len(chain) >= 2 and chain[-2] == "request" else "")
        )
        trust = "env" if kind == "env var" else "http"
        if is_json:
            kind = "body field"
        if kind:
            self._emit(node, kind, literal, trust)
        self.generic_visit(node)


class _Pack:
    name = "python"
    extensions: tuple[str, ...] = (".py",)
    models: dict = {}

    def prepare(self, repo):
        self.models = _prepare(repo)

    excluded = staticmethod(excluded)

    def scan(self, relpath, text):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return [], 1
        visitor = _Visitor(relpath, self.models)
        visitor.visit(tree)
        return visitor.rows, visitor.unresolved


PACK = _Pack()
