"""Deterministic, template-configured result validation.

Arithmetic consistency is not proof of authenticity: a fabricated sheet can add up.
The report says so explicitly."""

import re
from dataclasses import dataclass
from typing import Any, Literal

from app.evidence.templates import (
    PARTY_PREFIX,
    FormTemplate,
    LessOrEqualRule,
    MatchesSubmissionRule,
    NonNegativeRule,
    RequiredRule,
    SumEqualsRule,
    party_key,
)
from app.schemas.elections import Party

DISCLAIMER = (
    "Arithmetic and consistency checks show whether the figures agree with each other and "
    "with the form rules. They do not prove that a result sheet is authentic."
)

Outcome = Literal["passed", "failed", "not_evaluated"]
Values = dict[str, int | str | None]


@dataclass(frozen=True)
class SubmissionContext:
    polling_unit_code: str
    election_label: str


def _check(rule: Any, outcome: Outcome, detail: str, fields: list[str], **extra: Any) -> dict:
    return {
        "rule_id": rule.id,
        "description": rule.description,
        "severity": rule.severity,
        "outcome": outcome,
        "detail": detail,
        "fields": fields,
        **extra,
    }


def _expand(terms: tuple[str, ...], party_keys: list[str]) -> list[str]:
    expanded: list[str] = []
    for term in terms:
        expanded += party_keys if term == f"{PARTY_PREFIX}*" else [term]
    return expanded


def _integer(values: Values, key: str) -> int | None:
    value = values.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _comparable(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _codes_match(sheet: str, expected: str) -> bool:
    a, b = _comparable(sheet), _comparable(expected)
    if not a or not b:
        return False
    digits_a, digits_b = re.sub(r"\D", "", a), re.sub(r"\D", "", b)
    return a == b or (len(digits_a) >= 4 and digits_a == digits_b)


def validate_result(
    values: Values,
    template: FormTemplate,
    parties: list[Party],
    context: SubmissionContext,
    attention_fields: list[str],
) -> dict[str, Any]:
    party_keys = [party_key(p.code) for p in parties] if template.party_votes.enabled else []
    integer_keys = [s.key for s in template.fields if s.kind == "integer"] + party_keys
    required = [s.key for s in template.fields if s.required]
    if template.party_votes.enabled and template.party_votes.required:
        required += party_keys
    missing = [key for key in required if values.get(key) is None]

    checks: list[dict[str, Any]] = []
    for rule in template.rules:
        if isinstance(rule, RequiredRule):
            checks.append(
                _check(rule, "failed", f"Missing: {', '.join(missing)}", missing)
                if missing
                else _check(rule, "passed", "All required fields are present.", required)
            )
        elif isinstance(rule, NonNegativeRule):
            bad = [
                key
                for key in integer_keys
                if values.get(key) is not None
                and (_integer(values, key) is None or _integer(values, key) < 0)  # type: ignore[operator]
            ]
            checks.append(
                _check(rule, "failed", f"Not a whole number of zero or more: {', '.join(bad)}", bad)
                if bad
                else _check(
                    rule, "passed", "All counts are whole numbers of zero or more.", integer_keys
                )
            )
        elif isinstance(rule, SumEqualsRule):
            terms = _expand(rule.terms, party_keys)
            fields = [rule.target, *terms]
            target = _integer(values, rule.target)
            parts = [_integer(values, key) for key in terms]
            absent = [k for k, v in zip(fields, [target, *parts], strict=True) if v is None]
            if absent or not terms:
                checks.append(
                    _check(
                        rule,
                        "not_evaluated",
                        f"Cannot evaluate without: {', '.join(absent)}",
                        fields,
                    )
                )
                continue
            total = sum(p for p in parts if p is not None)
            if total == target:
                checks.append(
                    _check(
                        rule,
                        "passed",
                        f"{rule.target} = {target}",
                        fields,
                        expected=total,
                        actual=target,
                    )
                )
            else:
                checks.append(
                    _check(
                        rule,
                        "failed",
                        f"{rule.target} is {target}, but the listed figures add up to {total} "
                        f"(difference {target - total:+d}).",  # type: ignore[operator]
                        fields,
                        expected=total,
                        actual=target,
                    )
                )
        elif isinstance(rule, LessOrEqualRule):
            fields = [rule.left, rule.right]
            left, right = _integer(values, rule.left), _integer(values, rule.right)
            if left is None or right is None:
                absent = [k for k, v in ((rule.left, left), (rule.right, right)) if v is None]
                checks.append(
                    _check(
                        rule,
                        "not_evaluated",
                        f"Cannot evaluate without: {', '.join(absent)}",
                        fields,
                    )
                )
            elif left <= right:
                checks.append(
                    _check(
                        rule,
                        "passed",
                        f"{left} ≤ {right}",
                        fields,
                        expected=f"≤ {right}",
                        actual=left,
                    )
                )
            else:
                checks.append(
                    _check(
                        rule,
                        "failed",
                        f"{rule.left} ({left}) exceeds {rule.right} ({right}) by {left - right}.",
                        fields,
                        expected=f"≤ {right}",
                        actual=left,
                    )
                )
        elif isinstance(rule, MatchesSubmissionRule):
            sheet = values.get(rule.field)
            expected = getattr(context, rule.against)
            if not isinstance(sheet, str) or not sheet:
                checks.append(
                    _check(
                        rule,
                        "not_evaluated",
                        f"{rule.field} was not read from the sheet.",
                        [rule.field],
                    )
                )
            elif (
                _codes_match(sheet, expected)
                if rule.against == "polling_unit_code"
                else _comparable(expected) in _comparable(sheet)
                or _comparable(sheet) in _comparable(expected)
            ):
                checks.append(
                    _check(
                        rule,
                        "passed",
                        "Matches the submission.",
                        [rule.field],
                        expected=expected,
                        actual=sheet,
                    )
                )
            else:
                checks.append(
                    _check(
                        rule,
                        "failed",
                        f"The sheet shows '{sheet}', but the submission is for '{expected}'.",
                        [rule.field],
                        expected=expected,
                        actual=sheet,
                    )
                )

    errors = [c for c in checks if c["outcome"] == "failed" and c["severity"] == "error"]
    warnings = [
        c
        for c in checks
        if (c["outcome"] == "failed" and c["severity"] == "warning")
        or c["outcome"] == "not_evaluated"
    ]
    return {
        "template_id": template.id,
        "checks": checks,
        "passed": [c["rule_id"] for c in checks if c["outcome"] == "passed"],
        "failed": [c["rule_id"] for c in errors],
        "warnings": [c["rule_id"] for c in warnings],
        "missing_fields": missing,
        "attention_fields": sorted(set(attention_fields)),
        "summary": {"errors": len(errors), "warnings": len(warnings)},
        "is_consistent": not errors,
        "disclaimer": DISCLAIMER,
    }
