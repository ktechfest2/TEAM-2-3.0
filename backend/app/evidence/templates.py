"""Configurable result-sheet templates (app/evidence/templates/*.json).

Party lists are not part of a template: they come from the election configuration,
so no party is hardcoded."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import AppError

PARTY_PREFIX = "party:"
TEMPLATE_DIR = Path(__file__).parent / "templates"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldSpec(_Model):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,60}$")
    label: str
    kind: Literal["integer", "text"]
    required: bool = False
    aliases: tuple[str, ...]
    pattern: str | None = None


class PartyVotesSpec(_Model):
    enabled: bool = True
    required: bool = True


class _Rule(_Model):
    id: str
    severity: Literal["error", "warning"]
    description: str


class RequiredRule(_Rule):
    type: Literal["required"]


class NonNegativeRule(_Rule):
    type: Literal["non_negative_integers"]


class SumEqualsRule(_Rule):
    type: Literal["sum_equals"]
    target: str
    terms: tuple[str, ...]


class LessOrEqualRule(_Rule):
    type: Literal["less_or_equal"]
    left: str
    right: str


class MatchesSubmissionRule(_Rule):
    type: Literal["matches_submission"]
    field: str
    against: Literal["polling_unit_code", "election_label"]


Rule = Annotated[
    RequiredRule | NonNegativeRule | SumEqualsRule | LessOrEqualRule | MatchesSubmissionRule,
    Field(discriminator="type"),
]


class FormTemplate(_Model):
    id: str
    name: str
    is_demo: bool
    notice: str
    fields: tuple[FieldSpec, ...]
    party_votes: PartyVotesSpec
    rules: tuple[Rule, ...]

    @model_validator(mode="after")
    def references_are_known(self) -> "FormTemplate":
        keys = {field.key for field in self.fields}
        referenced: list[str] = []
        for rule in self.rules:
            if isinstance(rule, SumEqualsRule):
                referenced += [rule.target, *rule.terms]
            elif isinstance(rule, LessOrEqualRule):
                referenced += [rule.left, rule.right]
            elif isinstance(rule, MatchesSubmissionRule):
                referenced.append(rule.field)
        unknown = {ref for ref in referenced if ref != f"{PARTY_PREFIX}*" and ref not in keys}
        if unknown:
            raise ValueError(f"rules reference unknown fields: {sorted(unknown)}")
        return self

    def field(self, key: str) -> FieldSpec | None:
        return next((field for field in self.fields if field.key == key), None)


def party_key(code: str) -> str:
    return f"{PARTY_PREFIX}{code}"


@lru_cache
def load_templates() -> dict[str, FormTemplate]:
    templates = {}
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        template = FormTemplate.model_validate_json(path.read_text(encoding="utf-8"))
        templates[template.id] = template
    return templates


def get_template(template_id: str) -> FormTemplate:
    template = load_templates().get(template_id)
    if template is None:
        raise AppError("template_not_found", "The result-sheet template is not configured.", 500)
    return template
