"""Chat UI branding schemas (admin + public)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class QuickActionChip(BaseModel):
    icon: str = Field(default="", max_length=8)
    label: str = Field(..., min_length=1, max_length=80)


class ChatBrandingPublic(BaseModel):
    slug: str
    header_background: str
    welcome_title: str
    welcome_subtitle: str
    logo_url: str | None = None
    has_custom_logo: bool = False
    favicon_url: str | None = None
    has_custom_favicon: bool = False
    quick_actions: list[QuickActionChip] = Field(default_factory=list)


class ChatBrandingPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header_background: str | None = Field(default=None, max_length=512)
    welcome_title: str | None = Field(default=None, max_length=200)
    welcome_subtitle: str | None = Field(default=None, max_length=500)
    quick_actions: list[QuickActionChip] | None = None
