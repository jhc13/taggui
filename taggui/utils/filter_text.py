"""Helpers for building image list filter text from tags."""
import re

from PySide6.QtWidgets import QMenu, QWidget

ADD = 'and'
EXCLUDE = 'not'
ADD_OR = 'or'


def escape_tag_for_fnmatch(tag: str) -> str:
    """Make `*`, `?` and `[` match literally in `fnmatch`."""
    return (tag.replace('[', '[[]').replace('*', '[*]').replace('?', '[?]'))


def get_tag_filter_clause(tag: str) -> str:
    """Return a `tag:"..."` clause that matches exactly this tag."""
    tag = escape_tag_for_fnmatch(tag)
    tag = tag.replace('\\', '\\\\').replace('"', '\\"')
    return f'tag:"{tag}"'


def _clause_pattern(clause: str, negated: bool) -> str:
    escaped = re.escape(clause)
    if negated:
        return rf'(?<![^\s(])NOT\s+{escaped}(?![^\s)])'
    return rf'(?<![^\s(]){escaped}(?![^\s)])'


def _contains(text: str, clause: str, negated: bool) -> bool:
    if negated:
        return re.search(_clause_pattern(clause, True), text,
                         re.IGNORECASE) is not None
    # A positive clause that is not preceded by `NOT`.
    for match in re.finditer(_clause_pattern(clause, False), text):
        before = text[:match.start()].rstrip()
        if not re.search(r'(?:^|[\s(])NOT$', before, re.IGNORECASE):
            return True
    return False


def _remove(text: str, clause: str, negated: bool) -> str:
    """Remove a clause together with the operator that joins it."""
    core = (rf'NOT\s+{re.escape(clause)}' if negated
            else rf'(?<!NOT ){re.escape(clause)}')
    end = r'(?![^\s)])'
    for pattern in (rf'\s+(?:AND|OR)\s+{core}{end}',
                    rf'^\s*{core}\s+(?:AND|OR)\s+',
                    rf'^\s*{core}\s*$'):
        new_text, count = re.subn(pattern, '', text, count=1,
                                  flags=re.IGNORECASE)
        if count:
            return new_text.strip()
    return text


def _has_top_level_or(text: str) -> bool:
    depth = 0
    in_quote = None
    i = 0
    while i < len(text):
        char = text[i]
        if in_quote:
            if char == '\\':
                i += 1
            elif char == in_quote:
                in_quote = None
        elif char in '"\'':
            in_quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif depth == 0 and re.match(r'(?i)\sOR\s', text[i:i + 4]):
            return True
        i += 1
    return False


def extend_filter_text(text: str, tag: str, mode: str) -> str:
    """Return new filter text with the tag added in the given mode."""
    text = text.strip()
    clause = get_tag_filter_clause(tag)
    negated = mode == EXCLUDE
    if _contains(text, clause, negated):
        return text
    # Replace the opposite clause instead of creating a contradiction.
    if _contains(text, clause, not negated):
        text = _remove(text, clause, not negated)
    new_clause = f'NOT {clause}' if negated else clause
    if not text:
        return new_clause
    if mode == ADD_OR:
        return f'{text} OR {new_clause}'
    if _has_top_level_or(text):
        text = f'({text})'
    return f'{text} AND {new_clause}'


def build_tag_filter_menu(parent: QWidget, tag: str, emit) -> QMenu:
    """Context menu with actions to stack a tag onto the image filter."""
    menu = QMenu(parent)
    menu.addAction('Add to Filter', lambda: emit(tag, ADD))
    menu.addAction('Exclude from Filter', lambda: emit(tag, EXCLUDE))
    menu.addAction('Add to Filter (OR)', lambda: emit(tag, ADD_OR))
    return menu
