"""Admin API schemas — tenant connector (external hospital)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TenantConnectorPublic(BaseModel):
    """Non-secret view for admin UI."""

    external_hospital_base_url: str | None
    has_external_hospital_api_key: bool


class TenantConnectorProbeAccepted(BaseModel):
    """Celery kuyruğuna alındı; sonuç için task_id ile worker çıktısına bakın."""

    task_id: str = Field(..., description="Celery async result id")


class TenantConnectorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_hospital_base_url: str | None = Field(
        default=None,
        description="Set to empty string or null to clear.",
    )
    external_hospital_api_key: str | None = Field(
        default=None,
        description="Set to empty string or null to clear. Omit to leave unchanged.",
    )
