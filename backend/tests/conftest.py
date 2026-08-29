import pytest

from app import settings


@pytest.fixture(autouse=True)
def default_tests_to_mock(monkeypatch):
    monkeypatch.setattr(settings, "AI_MODE", "mock")
    monkeypatch.setattr(settings, "AI_STYLING_MODE", "mock")
    monkeypatch.setattr(settings, "AI_IMAGE_MODE", "mock")
