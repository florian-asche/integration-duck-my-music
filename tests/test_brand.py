"""Tests for the brand images that Home Assistant shows for the integration."""

import struct
from pathlib import Path

import pytest

BRAND = Path(__file__).resolve().parent.parent / "custom_components" / "satellite_controller" / "brand"


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from the IHDR chunk of a PNG file."""
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", header[16:24])


@pytest.mark.parametrize(("name", "size"), [("icon.png", 256), ("icon@2x.png", 512)])
def test_icon_has_the_size_home_assistant_expects(name: str, size: int) -> None:
    assert png_size(BRAND / name) == (size, size)
