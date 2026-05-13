"""Tenant-scoped policy flags stored in ``Tenant.settings`` JSONB."""

from __future__ import annotations

from typing import Any, Protocol


class _TenantPolicySource(Protocol):
    settings: dict[str, Any] | None


# Keys the admin API may read/write (extend deliberately).
RAG_RETRIEVAL_ENABLED_KEY = "rag_retrieval_enabled"


def default_policy() -> dict[str, Any]:
    return {RAG_RETRIEVAL_ENABLED_KEY: True}


def effective_policy(tenant: _TenantPolicySource | None) -> dict[str, Any]:
    """Merge DB ``tenant.settings`` with defaults (tenant values override for known keys)."""
    base = default_policy()
    raw = tenant.settings if tenant and isinstance(tenant.settings, dict) else None
    if not raw:
        return dict(base)
    merged = dict(base)
    for k, v in raw.items():
        if k in base:
            merged[k] = v
    return merged


def rag_retrieval_enabled(tenant: _TenantPolicySource | None) -> bool:
    pol = effective_policy(tenant)
    v = pol.get(RAG_RETRIEVAL_ENABLED_KEY)
    return v is not False


def merge_policy_patch(current: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    """Apply ``patch`` over current tenant settings; only known policy keys are written."""
    defaults = default_policy()
    out: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
    for k, v in defaults.items():
        out.setdefault(k, v)
    for k, v in patch.items():
        if k in defaults:
            out[k] = v
    return out
