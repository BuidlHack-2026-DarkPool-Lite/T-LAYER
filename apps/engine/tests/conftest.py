"""공통 픽스처."""

from __future__ import annotations

import pytest

from src.matching.state import matching_state


@pytest.fixture(autouse=True)
def _reset_matching_state():
    matching_state.reset()
    yield
    matching_state.reset()
