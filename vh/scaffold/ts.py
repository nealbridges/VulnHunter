"""JS/TS input-site pack: line/regex scanning in pure Python (plan D1)."""

from __future__ import annotations

import re

from .common import Row

NAME = r"[A-Za-z_$][\w$]*"
# Not a prefix of a longer identifier, so `.subscribe(` cannot backtrack to `subscrib`.
NAMEWORD = NAME + r"(?![A-Za-z0-9_$])"
RECV = r"(?:\breq\b|\brequest\b|\bctx\s*\.\s*request\b)"
ACCESS = r"\s*(?:\.|\?\.)\s*"
_OBJECTS = {
    "query": ("query param", "http"),
    "params": ("path param", "http"),
    "body": ("body field", "http"),
    "headers": ("header", "http"),
    "cookies": ("cookie", "http"),
    "signedCookies": ("cookie", "http"),
}
_EXCLUDED_SEGMENTS = frozenset(
    {"test", "tests", "__tests__", "e2e", "cypress", "dist", "build", "coverage"}
)
_RESERVED = frozenset({"if", "for", "while", "switch", "catch", "with", "function", "return"})

_EP_PATTERNS = (
    re.compile(r"\bfunction\s+(?P<n>" + NAME + r")\s*\("),
    re.compile(r"(?<![\w$.])(?P<n>" + NAME + r")\s*\([^)]*\)\s*(?::\s*[^{};=]+)?\{"),
    re.compile(
        r"\b(?:const|let|var)\s+(?P<n>" + NAME + r")\s*=\s*(?:async\s+)?"
        r"(?:function|\([^)]*\)\s*=>|" + NAME + r"\s*=>)"
    ),
    re.compile(r"\.\s*(?P<n>" + NAME + r")\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)"),
)
_DESTRUCT_HEAD = re.compile(r"\b(?:const|let|var)\s*\{")
_DESTRUCT_TARGET = re.compile(
    r"\s*=\s*(?:(?P<env>process\s*\.\s*env)|(?P<recv>" + RECV + r")\s*(?:\.|\?\.)\s*"
    r"(?P<obj>query|params|body|headers|cookies)(?!\s*[.\[]))"
)
_DECLARATION = re.compile(r"(?P<name>" + NAME + r")\s*(?::|=(?!=))?\s*")


def _property(obj: str, source_type: str, trust: str) -> re.Pattern[str]:
    prop = (
        r"(?:(?:\.|\?\.)\s*(?P<name>"
        + NAMEWORD
        + r")(?!\s*\()|\[\s*(?P<q>['\"])(?P<bname>[^'\"\n]+)(?P=q)\s*\])"
    )
    return re.compile(RECV + ACCESS + obj + r"\s*" + prop)


_PROPERTY_PATTERNS = [(_property(obj, *spec), spec) for obj, spec in _OBJECTS.items()]
_SITE_PATTERNS = [
    (
        re.compile(
            RECV + ACCESS + r"(?:get|header)\s*\(\s*(?P<q>['\"])(?P<name>[^'\"\n]+)(?P=q)\s*\)"
        ),
        "header",
        "http",
    ),
    (
        re.compile(r"\bprocess\s*\.\s*env\s*\.\s*(?P<name>" + NAME + r")(?!\s*\()"),
        "env var",
        "env",
    ),
    (
        re.compile(
            ACCESS
            + r"queryParams\s*(?:(?:\.|\?\.)\s*(?P<name>"
            + NAMEWORD
            + r")(?!\s*\()|\[\s*(?P<q>['\"])(?P<bname>[^'\"\n]+)(?P=q)\s*\])"
        ),
        "client query param",
        "client",
    ),
    (
        re.compile(
            ACCESS
            + r"(?:queryParamMap|searchParams)\s*(?:\.|\?\.)\s*get\s*\(\s*(?P<q>['\"])"
            + r"(?P<name>[^'\"\n]+)(?P=q)\s*\)"
        ),
        "client query param",
        "client",
    ),
    (
        re.compile(
            r"new\s+URLSearchParams\s*\([^;\n]*?\)\s*\.\s*get\s*\(\s*(?P<q>['\"])"
            + r"(?P<name>[^'\"\n]+)(?P=q)\s*\)"
        ),
        "client query param",
        "client",
    ),
]
_ROUTE_CALL = re.compile(
    r"(?<![\w$.])(?P<ident>" + NAME + r")\s*\.\s*(?:get|post|put|patch|delete|all|use|route)"
    r"\s*\(\s*(?P<q>['\"`])(?P<path>/[^'\"`]*)(?P=q)"
)
_ROUTE_PARAM = re.compile(r"(?<!:):(?!:)(?P<name>" + NAME + r")")
_WHOLE = re.compile(RECV + r"\s*(?:\.|\?\.)\s*(?P<obj>query|body)\b(?!\s*(?:\.|\?\.|\[|=(?!=)))")
_NONLITERAL_PROP = re.compile(
    RECV + ACCESS + r"(?:query|params|body|headers|cookies|signedCookies)\s*\[\s*(?!['\"])"
)
_NONLITERAL_GET = re.compile(RECV + ACCESS + r"(?:get|header)\s*\(\s*(?!['\"])")


def excluded(relpath: str) -> bool:
    parts = relpath.split("/")
    if any(part in _EXCLUDED_SEGMENTS for part in parts[:-1]):
        return True
    name = parts[-1]
    if name.endswith(".d.ts") or name.endswith(".min.js"):
        return True
    return re.search(r"\.(test|spec)\.", name) is not None


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _entry_point(text: str, pos: int) -> str:
    head = text[:pos]
    best_name, best_start = "", -1
    for pattern in _EP_PATTERNS:
        for match in pattern.finditer(head):
            name = match.group("n")
            if name not in _RESERVED and match.start() > best_start:
                best_name, best_start = name, match.start()
    return best_name or "<module>"


def _blank_block_comments(text: str) -> str:
    out = list(text)
    index, length, in_block = 0, len(text), False
    while index < length:
        char = text[index]
        if in_block:
            if char == "*" and index + 1 < length and text[index + 1] == "/":
                out[index] = out[index + 1] = " "
                index, in_block = index + 2, False
            else:
                if char != "\n":
                    out[index] = " "
                index += 1
            continue
        if char in "'\"`":
            quote, index = char, index + 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                elif text[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "*":
            out[index] = out[index + 1] = " "
            index, in_block = index + 2, True
            continue
        index += 1
    return "".join(out)


def _blank_line_comments(text: str) -> str:
    lines = text.splitlines(keepends=True)
    for number, line in enumerate(lines):
        if line.lstrip().startswith("//"):
            body = line.rstrip("\r\n")
            lines[number] = " " * len(body) + line[len(body) :]
    return "".join(lines)


def _split_items(content: str) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    depth, start = 0, 0
    for index, char in enumerate(content):
        if char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
        elif char == "," and depth == 0:
            items.append((content[start:index], start))
            start = index + 1
    items.append((content[start:], start))
    return items


def _destructuring(text: str) -> tuple[list[tuple[int, str, str]], int, set[int]]:
    entries: list[tuple[int, str, str]] = []
    unresolved, targets = 0, set()
    for head in _DESTRUCT_HEAD.finditer(text):
        open_pos = text.find("{", head.start())
        depth, close_pos = 0, -1
        for index in range(open_pos, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    close_pos = index
                    break
        if close_pos < 0 or text.count("\n", head.start(), close_pos) > 10:
            continue
        target = _DESTRUCT_TARGET.match(text, close_pos + 1)
        if not target:
            continue
        source_type = "env var" if target.group("env") else _OBJECTS[target.group("obj")][0]
        if target.group("recv"):
            targets.add(target.start("recv"))
        content_start = open_pos + 1
        for item_text, item_offset in _split_items(text[content_start:close_pos]):
            body = item_text.strip()
            if body.startswith("..."):
                unresolved += 1
            elif body:
                declaration = _DECLARATION.match(body)
                if declaration:
                    lead = len(item_text) - len(item_text.lstrip())
                    entries.append(
                        (content_start + item_offset + lead, source_type, declaration.group("name"))
                    )
    return entries, unresolved, targets


def scan(relpath: str, text: str) -> tuple[list[Row], int]:
    clean = _blank_line_comments(_blank_block_comments(text))
    unresolved = len(_NONLITERAL_PROP.findall(clean)) + len(_NONLITERAL_GET.findall(clean))
    destructured, destructured_unresolved, consumed = _destructuring(clean)
    unresolved += destructured_unresolved
    rows: list[Row] = []

    def emit(pos: int, source_type: str, variable: str, trust: str) -> None:
        entry = _entry_point(clean, pos)
        rows.append(Row(source_type, relpath, _line_of(clean, pos), variable, entry, trust))

    for pos, source_type, variable in destructured:
        emit(pos, source_type, variable, "env" if source_type == "env var" else "http")
    for pattern, (source_type, trust) in _PROPERTY_PATTERNS:
        for match in pattern.finditer(clean):
            group = "name" if match.group("name") else "bname"
            emit(match.start(group), source_type, match.group(group), trust)
    for pattern, source_type, trust in _SITE_PATTERNS:
        for match in pattern.finditer(clean):
            group = "name" if match.group("name") else "bname"
            emit(match.start(group), source_type, match.group(group), trust)
    for match in _ROUTE_CALL.finditer(clean):
        for param in _ROUTE_PARAM.finditer(match.group("path")):
            emit(match.start("path") + param.start(), "path param", param.group("name"), "http")
    for match in _WHOLE.finditer(clean):
        if match.start() not in consumed:
            obj = match.group("obj")
            emit(match.start(), _OBJECTS[obj][0], f"<{obj}:whole>", "http")
    return rows, unresolved


class _Pack:
    name = "ts"
    extensions: tuple[str, ...] = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")
    excluded = staticmethod(excluded)
    scan = staticmethod(scan)


PACK = _Pack()
