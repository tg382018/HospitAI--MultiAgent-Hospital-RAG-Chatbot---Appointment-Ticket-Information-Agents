"""Favicon upload validation."""

from __future__ import annotations

import pytest

from hospitai.infrastructure.tenant_assets import validate_favicon_upload

_ICO_HEADER = b"\x00\x00\x01\x00" + b"\x00" * 2  # minimal header padding


def test_validate_favicon_rejects_non_ico_extension() -> None:
    with pytest.raises(ValueError, match="\\.ico"):
        validate_favicon_upload(
            filename="icon.png",
            content_type="image/png",
            size=len(_ICO_HEADER),
            data=_ICO_HEADER,
        )


def test_validate_favicon_rejects_bad_magic() -> None:
    with pytest.raises(ValueError, match="Invalid ICO"):
        validate_favicon_upload(
            filename="favicon.ico",
            content_type="image/x-icon",
            size=8,
            data=b"not-an-ico",
        )


def test_validate_favicon_accepts_ico() -> None:
    validate_favicon_upload(
        filename="favicon.ico",
        content_type="image/x-icon",
        size=len(_ICO_HEADER),
        data=_ICO_HEADER,
    )
