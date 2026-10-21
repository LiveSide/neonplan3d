"""Fixtures for NeonPlan 3D tests."""

from __future__ import annotations

from collections.abc import Generator
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
import pytest

from custom_components.neonplan3d import packs


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture(autouse=True)
def only_the_test_key_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the publisher key file of the checkout out of every test (fork, see FORK.md).

    packs._local_key_files() also looks beside the integration, which in a checkout is the
    repository root - exactly where a developer's own neonplan3d_publishers.json sits. A test
    that expects no key, or only its own, would otherwise see that one and fail on a machine
    that signs furniture. Only NEONPLAN3D_PUBLISHERS counts here, and the tests that need a
    key set it to a file under tmp_path.
    """

    def env_only() -> list[Path]:
        env = os.environ.get("NEONPLAN3D_PUBLISHERS")
        return [Path(env)] if env else []

    monkeypatch.setattr(packs, "_local_key_files", env_only)


@pytest.fixture(autouse=True)
def mock_frontend(hass: HomeAssistant) -> Generator[dict[str, object]]:
    """Stand in for the frontend and panel_custom components (hass_frontend is not installed in tests)."""
    hass.config.components.update({"frontend", "panel_custom"})
    with (
        patch("homeassistant.components.frontend.add_extra_js_url") as add_js,
        patch("homeassistant.components.frontend.remove_extra_js_url") as remove_js,
        patch("homeassistant.components.frontend.async_remove_panel") as remove_panel,
        patch("homeassistant.components.panel_custom.async_register_panel", new_callable=AsyncMock) as register,
    ):
        yield {"add_js": add_js, "remove_js": remove_js, "remove_panel": remove_panel, "register": register}
