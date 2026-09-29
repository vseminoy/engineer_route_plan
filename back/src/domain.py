"""Domain values shared by the service and the repository."""

from datetime import datetime, time
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Skill(StrEnum):
    LOCAL_WORK = "local_work"
    CONNECTION = "connection"
    EMERGENCY = "emergency"


class VehicleType(StrEnum):
    CAR = "car"
    FOOT = "foot"
    BIKE = "bike"
    PUBLIC_TRANSPORT = "public_transport"


class TicketStatus(StrEnum):
    NOT_SENT = "not_sent"
    SENT = "sent"
    EN_ROUTE = "en_route"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class Point(BaseModel):
    """WGS84 point."""

    model_config = ConfigDict(frozen=True)

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RegionDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    office_address: str
    office: Point


class EngineerDraft(BaseModel):
    """A brigade to be stored; shift times are local time of the region."""

    model_config = ConfigDict(frozen=True)

    name: str
    start: Point
    shift_start: time
    shift_end: time
    vehicle_type: VehicleType
    skills: tuple[Skill, ...] = Field(min_length=1, max_length=3)


class TicketDraft(BaseModel):
    """A ticket to be stored; datetimes are naive local time of the region."""

    model_config = ConfigDict(frozen=True)

    external_id: str
    type_bk: str | None
    type_hd: str
    required_skill: Skill
    required_vehicle: VehicleType | None = None
    priority: int = Field(ge=1)
    district: str | None
    address: str
    location: Point
    window_start: datetime
    window_end: datetime
    duration_min: int = Field(gt=0)
    status: TicketStatus
    received_at: datetime


class EngineerSetKind(StrEnum):
    DEMO = "demo"
    GENERATED = "generated"


class EngineerSetParams(BaseModel):
    """Generator parameters of a region's `default` set, computed from region config —
    what the loader passes in for the region's very first load, before any `engineer_sets`
    row exists to read them back from."""

    model_config = ConfigDict(frozen=True)

    engineers: int = Field(ge=1, le=30)
    morning_share: float = Field(ge=0, le=1)
    evening_share: float = Field(ge=0, le=1)
    seed: str = Field(min_length=1, max_length=50)


class EngineerSet(BaseModel):
    """A stored engineer set, as listed for a region."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    kind: EngineerSetKind
    engineers: int
    morning_share: float
    evening_share: float
    seed: str


class EngineerSetWithRegion(EngineerSet):
    """`EngineerSet` plus the region it belongs to, for ownership checks the region-less
    read does not need."""

    region_id: int


class RegionWritten(BaseModel):
    """The outcome of writing a region's data: `engineers` is the region's brigade count
    across every set; `engineers_kept` is true, by set name, when that set's stored
    brigades kept their ids and only moved to the new start points."""

    model_config = ConfigDict(frozen=True)

    region_id: int
    engineers: int
    engineers_kept: dict[str, bool]


class Engineer(BaseModel):
    """A stored brigade; shift times are local time of the region."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    start: Point
    shift_start: time
    shift_end: time
    vehicle_type: VehicleType
    skills: tuple[Skill, ...] = Field(min_length=1, max_length=3)


class Ticket(BaseModel):
    """A stored ticket; datetimes are naive local time of the region."""

    model_config = ConfigDict(frozen=True)

    id: int
    external_id: str
    type_bk: str | None
    type_hd: str
    required_skill: Skill
    required_vehicle: VehicleType | None
    priority: int = Field(ge=1)
    district: str | None
    address: str
    location: Point
    window_start: datetime
    window_end: datetime
    duration_min: int = Field(gt=0)
    status: TicketStatus
    received_at: datetime
