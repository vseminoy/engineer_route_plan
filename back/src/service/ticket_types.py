"""Ticket types of the input files mapped to skill, priority rank and minutes on site."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from src.domain import Skill, TicketStatus


class WorkType(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    priority: int = Field(ge=1)
    duration_min: int = Field(gt=0)


class HdType(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    skill: Skill
    work_type: str | None = None


class Classification(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill: Skill
    priority: int
    duration_min: int


class TicketTypes(BaseModel):
    """The mapping table. A work kind named by an HD entry wins over the one the BK
    type gives, which is how HD "Авария" stays an emergency whatever the BK type."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    work_types: dict[str, WorkType]
    bk: dict[str, str]
    hd: dict[str, HdType]
    statuses: dict[str, TicketStatus]

    def model_post_init(self, _context: object) -> None:
        named = set(self.bk.values()) | {h.work_type for h in self.hd.values() if h.work_type}
        unknown = sorted(named - self.work_types.keys())
        if unknown:
            raise ValueError(f"work_types: no entry for {', '.join(unknown)}")

    @classmethod
    def from_file(cls, path: Path) -> "TicketTypes":
        with path.open("rb") as f:
            return cls.model_validate(tomllib.load(f))

    def classify(self, type_bk: str | None, type_hd: str) -> Classification | None:
        """`None` when the HD type, or the BK type it relies on, is not in the table."""
        hd = self.hd.get(type_hd)
        if hd is None:
            return None
        kind = hd.work_type or (self.bk.get(type_bk) if type_bk else None)
        if kind is None:
            return None
        work = self.work_types[kind]
        return Classification(
            skill=hd.skill, priority=work.priority, duration_min=work.duration_min
        )

    def status(self, value: str) -> TicketStatus | None:
        return self.statuses.get(value)
