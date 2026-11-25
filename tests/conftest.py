"""Fast unit/HTTP regressions do not start a real office renderer.
Run the separate real-document pagination check explicitly with force=True.
"""
import pytest

@pytest.fixture(autouse=True)
def isolate_office_renderer(monkeypatch):
    monkeypatch.setenv('SAFETY_PAGINATION_MODE','off')
