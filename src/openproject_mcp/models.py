from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import hal

T = TypeVar("T", bound=BaseModel)


class Link(BaseModel):
    href: str
    title: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class BaseHALModel(BaseModel):
    """
    Base model that handles HAL+JSON patterns.
    We keep _links/_embedded loosely typed because OpenProject uses:
      - single link objects
      - arrays of link objects
      - empty arrays
      - href can be null in some relations
    """

    links: Dict[str, Any] = Field(default_factory=dict, alias="_links")
    embedded: Dict[str, Any] = Field(default_factory=dict, alias="_embedded")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    def link_href(self, rel: str) -> Optional[str]:
        return hal.get_link_href({"_links": self.links}, rel)

    def link_title(self, rel: str) -> Optional[str]:
        return hal.get_link_title({"_links": self.links}, rel)

    def link_id(self, rel: str) -> Optional[int]:
        href = self.link_href(rel)
        return hal.parse_id_from_href(href) if href else None

    def embedded_raw(self, rel: str) -> Optional[Dict[str, Any]]:
        value = self.embedded.get(rel)
        return value if isinstance(value, dict) else None

    def embedded_as(self, rel: str, model: Type[T]) -> Optional[T]:
        raw = self.embedded_raw(rel)
        if not raw:
            return None
        try:
            return model.model_validate(raw)
        except ValidationError:
            return None


# --- Lightweight Metadata Reference Models ---


class TypeRef(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(extra="ignore")


class PriorityRef(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(extra="ignore")


class StatusRef(BaseModel):
    id: int
    name: str
    is_closed: bool = Field(default=False, alias="isClosed")

    model_config = ConfigDict(extra="ignore")


class UserRef(BaseModel):
    id: int
    name: str
    login: Optional[str] = None
    mail: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class ProjectRef(BaseModel):
    id: int
    name: str
    identifier: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


# --- Input Models (Tool Payloads) ---
class WorkPackageCreateInput(BaseModel):
    project: str
    type: str
    subject: str
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class WorkPackageUpdateStatusInput(BaseModel):
    id: int
    status: str

    model_config = ConfigDict(extra="forbid")


class WorkPackageUpdateInput(BaseModel):
    id: int
    subject: Optional[str] = None
    description: Optional[str] = None
    append_description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[Any] = None  # id/int/str/None to clear
    start_date: Optional[date | str] = None
    due_date: Optional[date | str] = None
    percent_done: Optional[int] = None
    estimated_time: Optional[str] = None  # ISO 8601 preferred
    type: Optional[str] = None
    project: Optional[str] = None
    accountable: Optional[int | str | None] = None  # responsible link

    model_config = ConfigDict(extra="forbid")


# --- Summary Models (Output) ---


class ProjectSummary(BaseModel):
    id: int
    name: str
    identifier: str
    active: bool


class UserSummary(BaseModel):
    id: int
    name: str
    login: Optional[str]


class StatusSummary(BaseModel):
    id: int
    name: str
    is_closed: bool


class WorkPackageSummary(BaseModel):
    id: int
    subject: str
    status: str
    priority: str
    assignee: Optional[str]
    project: str


# --- Core Entities ---


class User(BaseHALModel):
    id: int
    name: str
    login: Optional[str] = None
    admin: bool = False

    def to_summary(self) -> UserSummary:
        return UserSummary(
            id=self.id,
            name=self.name,
            login=self.login,
        )


class Status(BaseHALModel):
    id: int
    name: str
    is_closed: bool = Field(default=False, alias="isClosed")
    color: Optional[str] = None

    def to_summary(self) -> StatusSummary:
        return StatusSummary(
            id=self.id,
            name=self.name,
            is_closed=self.is_closed,
        )


class Project(BaseHALModel):
    id: int
    identifier: str
    name: str
    active: bool = True
    description: Optional[Dict[str, Any]] = None

    @property
    def description_text(self) -> str:
        if isinstance(self.description, dict):
            return str(self.description.get("raw") or "")
        return ""

    def to_summary(self) -> ProjectSummary:
        return ProjectSummary(
            id=self.id,
            name=self.name,
            identifier=self.identifier,
            active=self.active,
        )


class WorkPackage(BaseHALModel):
    id: int
    subject: str
    lock_version: int = Field(alias="lockVersion")
    description: Optional[Dict[str, Any]] = None

    # Raw value fields (useful if HAL links are missing/broken)
    # Note: OpenProject can return null for these fields
    percentage_done: Optional[int] = Field(default=None, alias="percentageDone")
    estimated_time: Optional[str] = Field(default=None, alias="estimatedTime")

    @property
    def description_text(self) -> str:
        if isinstance(self.description, dict):
            return str(self.description.get("raw") or "")
        return ""

    # --- Convenience Accessors (Link Titles) ---
    @property
    def status_title(self) -> str:
        return self.link_title("status") or "Unknown"

    @property
    def priority_title(self) -> str:
        return self.link_title("priority") or "Normal"

    @property
    def assignee_title(self) -> Optional[str]:
        return self.link_title("assignee")

    @property
    def project_title(self) -> str:
        return self.link_title("project") or "Unknown"

    # --- Convenience Accessors (Link IDs) ---
    @property
    def project_id(self) -> Optional[int]:
        return self.link_id("project")

    @property
    def status_id(self) -> Optional[int]:
        return self.link_id("status")

    def to_summary(self) -> WorkPackageSummary:
        return WorkPackageSummary(
            id=self.id,
            subject=self.subject,
            status=self.status_title,
            priority=self.priority_title,
            assignee=self.assignee_title,
            project=self.project_title,
        )
