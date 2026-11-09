"""Request/response models for the Website Tracker feature."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ACTIVITY_TYPES: tuple[str, ...] = (
    "SEO Update",
    "Content Update",
    "CTA Update",
    "Technical Fix",
    "Internal Linking",
    "Other",
)

ACTIVITY_STATUSES: tuple[str, ...] = ("planned", "completed")


def _clean_required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must not be empty")
    return cleaned


class Website(BaseModel):
    id: int
    name: str
    domain: str
    created_at: str
    updated_at: str
    url_count: int = 0
    activity_count: int = 0


class ActivityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    activity_type: str
    status: Literal["planned", "completed"] = "planned"
    website_id: int | None = None
    website_url_id: int | None = None
    planned_date: date
    completed_date: date | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        return _clean_required(value, "title")

    @field_validator("description")
    @classmethod
    def description_is_trimmed(cls, value: str) -> str:
        return value.strip()

    @field_validator("activity_type")
    @classmethod
    def activity_type_must_be_known(cls, value: str) -> str:
        if value not in ACTIVITY_TYPES:
            raise ValueError(
                f"activity_type must be one of: {', '.join(ACTIVITY_TYPES)}"
            )
        return value

    @field_validator("website_id", "website_url_id")
    @classmethod
    def ids_must_be_positive(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("ids must be positive integers")
        return value

    @model_validator(mode="after")
    def completed_date_requires_completed_status(self) -> "ActivityCreate":
        if self.status == "planned" and self.completed_date is not None:
            raise ValueError("completed_date is only allowed for completed activities")
        return self


class ActivityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    activity_type: str | None = None
    status: Literal["planned", "completed"] | None = None
    website_id: int | None = None
    website_url_id: int | None = None
    planned_date: date | None = None
    completed_date: date | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required(value, "title")

    @field_validator("description")
    @classmethod
    def description_is_trimmed(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("activity_type")
    @classmethod
    def activity_type_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in ACTIVITY_TYPES:
            raise ValueError(
                f"activity_type must be one of: {', '.join(ACTIVITY_TYPES)}"
            )
        return value

    @field_validator("website_id", "website_url_id")
    @classmethod
    def ids_must_be_positive(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("ids must be positive integers")
        return value


class CompleteActivityRequest(BaseModel):
    completed_date: date | None = None


class WebsiteActivity(BaseModel):
    id: int
    title: str
    description: str
    activity_type: str
    status: str
    website_id: int
    website_name: str | None
    website_url_id: int | None
    website_url: str | None
    planned_date: str
    completed_date: str | None
    created_at: str
    updated_at: str


class WebsiteUrl(BaseModel):
    id: int
    website_id: int
    website_name: str
    website_domain: str
    url: str
    sitemap_last_modified: str | None
    created_at: str
    updated_at: str
    activity_count: int
    planned_count: int
    completed_count: int
    last_activity_date: str | None


class WebsiteUrlDetail(WebsiteUrl):
    activities: list[WebsiteActivity]


class SitemapImportRequest(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=50)
    # Optional for backwards compatibility with the original single-website
    # client; omitted means the legacy EOS Teknologi website.
    website_id: int | None = None


class SitemapImportResponse(BaseModel):
    website_id: int
    website_name: str
    filenames: list[str]
    files_processed: int
    found: int
    imported: int
    updated: int
    skipped: int
    duplicates: int
    invalid: int
    unrelated_domains: int
    sitemap_index: bool
    child_sitemaps_skipped: int


class SitemapFile(BaseModel):
    filename: str
