"""Map positioned OCR tokens to template fields.

Labels are located by configurable aliases; values are read from the same line.
Each field receives a confidence and the reasons it needs human attention. A value
that could not be read confidently is flagged, never silently accepted."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.evidence.ocr import OcrToken
from app.evidence.templates import FieldSpec, FormTemplate, party_key
from app.schemas.elections import Party

# Characters OCR commonly confuses with digits on handwritten or printed figures.
_DIGIT_LOOKALIKES = {
    "O": "0",
    "o": "0",
    "D": "0",
    "Q": "0",
    "I": "1",
    "l": "1",
    "|": "1",
    "i": "1",
    "!": "1",
    "Z": "2",
    "z": "2",
    "S": "5",
    "s": "5",
    "G": "6",
    "B": "8",
}
_SEPARATORS = {",", ".", " ", "'"}
AMBIGUITY_PENALTY = 0.6


@dataclass
class MappedField:
    key: str
    label: str
    kind: str
    value_int: int | None = None
    value_text: str | None = None
    confidence: float | None = None
    source_text: str | None = None
    bbox: dict[str, int] | None = None
    ambiguous_characters: list[str] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)

    @property
    def requires_review(self) -> bool:
        return bool(self.review_reasons)


@dataclass(frozen=True)
class _Line:
    tokens: tuple[OcrToken, ...]

    @property
    def normalised(self) -> str:
        return normalise(" ".join(token.text for token in self.tokens))


def normalise(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9/ ]", " ", text.lower()).split())


def parse_count(raw: str) -> tuple[int | None, list[str]]:
    """Parse a written count, recording each character that had to be reinterpreted."""
    digits: list[str] = []
    substitutions: list[str] = []
    for char in raw.strip():
        if char.isdigit():
            digits.append(char)
        elif char in _DIGIT_LOOKALIKES:
            digits.append(_DIGIT_LOOKALIKES[char])
            substitutions.append(f"{char}→{_DIGIT_LOOKALIKES[char]}")
        elif char in _SEPARATORS:
            continue
        else:
            return None, []
    if not digits:
        return None, []
    return int("".join(digits)), substitutions


def _same_row(a: list[OcrToken], b: list[OcrToken]) -> bool:
    """Engines report a label and a far-off figure ("PA ...... 201") as separate lines.
    They belong together when each one's vertical centre falls inside the other."""
    a_top, a_bottom = min(t.top for t in a), max(t.top + t.height for t in a)
    b_top, b_bottom = min(t.top for t in b), max(t.top + t.height for t in b)
    a_mid, b_mid = (a_top + a_bottom) / 2, (b_top + b_bottom) / 2
    a_right, b_right = max(t.left + t.width for t in a), max(t.left + t.width for t in b)
    apart = a_right <= min(t.left for t in b) or b_right <= min(t.left for t in a)
    return apart and a_top <= b_mid <= a_bottom and b_top <= a_mid <= b_bottom


def _group_lines(tokens: list[OcrToken]) -> list[_Line]:
    lines: dict[str, list[OcrToken]] = {}
    for token in tokens:
        lines.setdefault(token.line_key, []).append(token)
    groups: list[list[OcrToken]] = []
    for group in sorted(lines.values(), key=lambda g: min(t.left for t in g)):
        row = next((g for g in groups if _same_row(g, group)), None)
        if row is None:
            groups.append(list(group))
        else:
            row.extend(group)
    ordered = sorted(groups, key=lambda group: (min(t.top for t in group), group[0].left))
    return [_Line(tuple(sorted(group, key=lambda t: t.left))) for group in ordered]


def _bbox(tokens: list[OcrToken]) -> dict[str, int]:
    left = min(t.left for t in tokens)
    top = min(t.top for t in tokens)
    right = max(t.left + t.width for t in tokens)
    bottom = max(t.top + t.height for t in tokens)
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


# Labels are words, so a digit inside one is a misread letter ("c0de", "tota1").
_LABEL_FOLD = str.maketrans({"0": "o", "1": "l", "i": "l", "5": "s"})


def _compact(text: str) -> str:
    return normalise(text).replace(" ", "")


def _label_form(text: str) -> str:
    return _compact(text).translate(_LABEL_FOLD)


def _label_end(line: _Line, alias: str) -> int | None:
    """Index of the first token after the alias, if the alias appears in this line.

    Spacing is ignored: OCR engines split words ("PO LLING") or merge them
    ("TOTALVALID VOTES"), so consecutive tokens are compared letters-only."""
    target = _label_form(alias)
    texts = [_label_form(token.text) for token in line.tokens]
    for start in range(len(texts)):
        joined = ""
        for end in range(start, len(texts)):
            joined += texts[end]
            if joined == target:
                return end + 1
            if not target.startswith(joined):
                break
    return None


def _find_label(lines: list[_Line], aliases: tuple[str, ...]) -> tuple[_Line, int] | None:
    for alias in sorted(aliases, key=len, reverse=True):
        target = _label_form(alias)
        for line in lines:
            if target in _label_form(line.normalised):
                end = _label_end(line, alias)
                if end is not None:
                    return line, end
    return None


def _read_integer(result: MappedField, tokens: tuple[OcrToken, ...]) -> None:
    # Prefer tokens containing real digits; fall back to digit look-alikes only if none do.
    with_digits = [i for i, t in enumerate(tokens) if any(c.isdigit() for c in t.text)]
    order = with_digits or list(range(len(tokens)))
    for index in order:
        token = tokens[index]
        value, substitutions = parse_count(token.text)
        if value is None:
            continue
        used = [token]
        # Figures such as "1 234" may be split into several tokens.
        for follower in tokens[index + 1 :]:
            more, extra = parse_count(follower.text)
            if more is None or not re.fullmatch(r"\d{3}", follower.text):
                break
            value = int(f"{value}{follower.text}")
            substitutions += extra
            used.append(follower)
        result.value_int = value
        result.source_text = " ".join(t.text for t in used)[:200]
        result.bbox = _bbox(used)
        confidence = min(t.confidence for t in used)
        if substitutions:
            result.ambiguous_characters = substitutions
            confidence *= AMBIGUITY_PENALTY
        result.confidence = round(confidence, 4)
        return


def _read_text(result: MappedField, spec: FieldSpec, tokens: tuple[OcrToken, ...]) -> None:
    usable = [t for t in tokens if normalise(t.text) not in {"", ":", "-"}]
    if not usable:
        return
    text = " ".join(t.text.strip(":") for t in usable).strip().upper()
    if spec.pattern:
        compact = text.replace(" ", "")
        if re.fullmatch(spec.pattern, compact):
            text = compact
        else:
            result.review_reasons.append("unexpected_format")
    result.value_text = text[:120]
    result.source_text = " ".join(t.text for t in usable)[:200]
    result.bbox = _bbox(usable)
    result.confidence = round(min(t.confidence for t in usable), 4)


def _finalise(result: MappedField, threshold: float) -> MappedField:
    if result.value_int is None and result.value_text is None:
        result.review_reasons.append("not_found")
        return result
    if result.ambiguous_characters:
        result.review_reasons.append("ambiguous_characters")
    if result.confidence is not None and result.confidence < threshold:
        result.review_reasons.append("low_confidence")
    return result


def map_fields(
    tokens: list[OcrToken],
    template: FormTemplate,
    parties: list[Party],
    threshold: float,
) -> list[MappedField]:
    lines = _group_lines(tokens)
    mapped: list[MappedField] = []

    for spec in template.fields:
        result = MappedField(key=spec.key, label=spec.label, kind=spec.kind)
        found = _find_label(lines, spec.aliases)
        if found:
            line, end = found
            remainder = line.tokens[end:]
            if spec.kind == "integer":
                _read_integer(result, remainder)
            else:
                _read_text(result, spec, remainder)
        mapped.append(_finalise(result, threshold))

    if template.party_votes.enabled:
        for party in parties:
            result = MappedField(key=party_key(party.code), label=party.name, kind="integer")
            code = party.code.lower()
            for line in lines:
                first = normalise(line.tokens[0].text) if line.tokens else ""
                if first == code:
                    _read_integer(result, line.tokens[1:])
                    break
            mapped.append(_finalise(result, threshold))
    return mapped


def empty_fields(template: FormTemplate, parties: list[Party]) -> list[MappedField]:
    """Placeholder fields when OCR is unavailable: everything needs manual entry."""
    fields = [MappedField(key=s.key, label=s.label, kind=s.kind) for s in template.fields]
    if template.party_votes.enabled:
        fields += [
            MappedField(key=party_key(p.code), label=p.name, kind="integer") for p in parties
        ]
    for item in fields:
        item.review_reasons.append("manual_entry_required")
    return fields


def field_labels(template: FormTemplate, parties: list[Party]) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {
        spec.key: {"label": spec.label, "kind": spec.kind, "required": spec.required}
        for spec in template.fields
    }
    if template.party_votes.enabled:
        for party in parties:
            labels[party_key(party.code)] = {
                "label": party.name,
                "kind": "integer",
                "required": template.party_votes.required,
            }
    return labels
