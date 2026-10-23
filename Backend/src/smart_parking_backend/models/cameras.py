from datetime import datetime
from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

MAX_CAMERAS = 32
MAX_FRAME_BYTES = 2 * 1024 * 1024
DEFAULT_THUMBNAIL_INTERVAL_SECONDS = 1.0


class CameraCategory(str, Enum):
    EXTERIOR = "Exterior"
    CITY = "City"
    ENTRANCE = "Entrance"
    EXIT = "Exit"
    PARKING_LEVEL = "ParkingLevel"
    RAMP = "Ramp"
    EV = "EV"


class FrameKind(str, Enum):
    THUMBNAIL = "thumbnail"
    FOCUSED = "focused"


class FeedHealth(str, Enum):
    FRESH = "Fresh"
    STALE = "Stale"
    NO_FRAME = "NoFrame"
    UNAVAILABLE = "Unavailable"


class CameraDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    camera_id: str = Field(min_length=1, max_length=128)
    display_name: str
    category: CameraCategory
    level: int = Field(ge=0, le=4)
    enabled: bool
    allow_focused: bool
    thumbnail_interval_seconds: float = Field(ge=0)
    description: str = ""
    coverage: str = ""


class CameraCatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unity_session_id: str = Field(min_length=1, max_length=64)
    focused_interval_seconds: float = Field(gt=0)
    cameras: list[CameraDefinition] = Field(max_length=MAX_CAMERAS)


class FrameUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unity_session_id: str = Field(min_length=1, max_length=64)
    kind: FrameKind
    sequence: int = Field(ge=1)
    captured_at: AwareDatetime
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    focus_generation: str | None = None


class FeedStatus(BaseModel):
    health: FeedHealth
    sequence: int | None = None
    captured_at: datetime | None = None
    age_ms: int | None = None
    width: int | None = None
    height: int | None = None


class CameraView(CameraDefinition):
    thumbnail: FeedStatus
    focused: FeedStatus


class FocusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str | None = None


class FocusState(BaseModel):
    camera_id: str | None = None
    focus_generation: str | None = None
    expires_at: datetime | None = None


class FocusLease(FocusState):
    lease_id: str


class CameraControl(BaseModel):
    unity_session_id: str
    backend_instance_id: str
    focus: FocusState
