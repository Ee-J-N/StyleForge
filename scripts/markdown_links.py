"""Extract Markdown link destinations while excluding code examples."""

from __future__ import annotations

import re


def _escaped(text, index):
    slashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        slashes += 1
        index -= 1
    return slashes % 2 == 1


def _mask_fenced_code(text):
    lines = text.splitlines(keepends=True)
    output = []
    marker = None
    length = 0
    for line in lines:
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*?)(?:\r?\n)?$", line)
        if marker is None and match:
            marker, length = match.group(1)[0], len(match.group(1))
            output.append("\n" if line.endswith("\n") else "")
            continue
        if marker is not None:
            close = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*(?:\r?\n)?$", line)
            output.append("\n" if line.endswith("\n") else "")
            if close and close.group(1)[0] == marker and len(close.group(1)) >= length:
                marker = None
            continue
        output.append(line)
    return "".join(output)


def _mask_inline_code(text):
    chars = list(text)
    index = 0
    while index < len(text):
        if text[index] != "`" or _escaped(text, index):
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] == "`":
            end += 1
        run = text[index:end]
        close = end
        while close < len(text):
            candidate = text.find("`", close)
            if candidate < 0:
                break
            finish = candidate + 1
            while finish < len(text) and text[finish] == "`":
                finish += 1
            if text[candidate:finish] == run and not _escaped(text, candidate):
                chars[index:finish] = " " * (finish - index)
                index = finish
                break
            close = finish
        else:
            index = end
            continue
        if index < end:
            index = end
    return "".join(chars)


def mask_code(text):
    """Blank fenced, indented and inline code while preserving source offsets."""
    chars = list(text)
    offset = 0
    marker = None
    length = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        opener = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", body)
        if marker is None:
            if opener:
                marker, length = opener.group(1)[0], len(opener.group(1))
                is_code = True
            else:
                is_code = body.startswith("    ") or body.startswith("\t")
        else:
            close = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", body)
            is_code = True
            if close and close.group(1)[0] == marker and len(close.group(1)) >= length:
                marker = None
        if is_code:
            for index in range(offset, offset + len(body)):
                chars[index] = " "
        offset += len(line)
    return _mask_inline_code("".join(chars))


def replace_outside_code(text, pattern, replacement):
    mask = mask_code(text)
    return pattern.sub(lambda match: match.group(0) if match.group(0) != mask[match.start():match.end()]
                       else replacement(match), text)


def _normalized_label(value):
    return " ".join(value.strip().split()).casefold()


def _bracket_close(text, start):
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if _escaped(text, index):
            index += 1
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _destination(text, start):
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text):
        return "", index
    if text[index] == "<":
        end = index + 1
        while end < len(text):
            if text[end] == ">" and not _escaped(text, end):
                return _unescape(text[index + 1:end]), end + 1
            end += 1
        return "", index
    start = index
    depth = 0
    while index < len(text):
        char = text[index]
        if _escaped(text, index):
            index += 1
            continue
        if char == "(" :
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        elif char.isspace() and depth == 0:
            break
        index += 1
    return _unescape(text[start:index]), index


def _unescape(value):
    punctuation = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    result = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value) and value[index + 1] in punctuation:
            index += 1
        result.append(value[index])
        index += 1
    return "".join(result)


def extract_links(text):
    """Return Markdown image/link destinations and unresolved references."""
    source = mask_code(text)
    definitions = {}
    definition_spans = []
    for match in re.finditer(r"(?m)^ {0,3}\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]*)>|([^\s\n]+))(?:[ \t]+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?[ \t]*(?:\r?\n|$)", source):
        destination = match.group(2) if match.group(2) is not None else match.group(3)
        definitions.setdefault(_normalized_label(match.group(1)), _unescape(destination))
        definition_spans.append(match.span())
    if definition_spans:
        chars = list(source)
        for start, end in definition_spans:
            for index in range(start, end):
                if chars[index] not in "\r\n":
                    chars[index] = " "
        source = "".join(chars)

    results = []
    index = 0
    while index < len(source):
        image = source[index] == "!" and index + 1 < len(source) and source[index + 1] == "[" and not _escaped(source, index)
        bracket = index + 1 if image else index
        if source[bracket] != "[" or _escaped(source, bracket):
            index += 1
            continue
        close = _bracket_close(source, bracket)
        if close is None:
            index += 1
            continue
        label = source[bracket + 1:close]
        cursor = close + 1
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        destination = None
        if cursor < len(source) and source[cursor] == "(":
            destination, end = _destination(source, cursor + 1)
            if end < len(source) and source[end] == ")":
                results.append({"kind": "image" if image else "link", "target": destination})
                index = end + 1
                continue
        elif cursor < len(source) and source[cursor] == "[":
            ref_end = _bracket_close(source, cursor)
            if ref_end is not None:
                ref = _normalized_label(source[cursor + 1:ref_end] or label)
                destination = definitions.get(ref)
                if destination is not None:
                    results.append({"kind": "image" if image else "link", "target": destination})
                else:
                    results.append({"kind": "unresolved_image" if image else "unresolved_link", "target": ref})
                index = ref_end + 1
                continue
        else:
            ref = _normalized_label(label)
            if ref in definitions:
                results.append({"kind": "image" if image else "link", "target": definitions[ref]})
                index = close + 1
                continue
        index = close + 1

    for match in re.finditer(r"(?is)<img\b[^>]*?\bsrc\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", source):
        results.append({"kind": "image", "target": next(group for group in match.groups() if group is not None)})
    for match in re.finditer(r"(?is)<a\b[^>]*?\bhref\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", source):
        results.append({"kind": "link", "target": next(group for group in match.groups() if group is not None)})
    return results
