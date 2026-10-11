"""Read the bounded text KeyValues format used by Steam's local manifests."""

import re

type KeyValues = dict[str, str | KeyValues]

TOKEN = re.compile(r'\s+|//[^\r\n]*|"(?:\\.|[^"\\])*"|[{}]|[^\s{}"]+')


def parse_keyvalues(contents: str) -> KeyValues:
    """Read nested quoted/bare values, comments and escaped Windows paths."""
    tokens: list[str] = []
    position = 0
    for match in TOKEN.finditer(contents):
        if match.start() != position:
            raise ValueError("Invalid Steam KeyValues token")
        position = match.end()
        token = match[0]
        if token.isspace() or token.startswith("//"):
            continue
        tokens.append(token)
    if position != len(contents):
        raise ValueError("Unterminated Steam KeyValues string")
    values, _ = _parse_object(tokens, 0, 0)
    return values


def _string(token: str) -> str:
    if token.startswith('"'):
        return re.sub(r'\\([\\"])', r"\1", token[1:-1])
    return token


def _parse_object(tokens: list[str], position: int, depth: int) -> tuple[KeyValues, int]:
    if depth > 32:
        raise ValueError("Steam KeyValues nesting is too deep")
    values: KeyValues = {}
    while position < len(tokens):
        token = tokens[position]
        position += 1
        if token == "}":
            if depth == 0:
                raise ValueError("Unexpected Steam KeyValues closing brace")
            return values, position
        if token == "{" or position == len(tokens):
            raise ValueError("Missing Steam KeyValues key or value")
        key = _string(token).casefold()
        token = tokens[position]
        position += 1
        if token == "{":
            values[key], position = _parse_object(tokens, position, depth + 1)
        elif token == "}":
            raise ValueError("Missing Steam KeyValues value")
        else:
            values[key] = _string(token)
    if depth != 0:
        raise ValueError("Unterminated Steam KeyValues object")
    return values, position
