from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app_main import app


@pytest.fixture()
def test_client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client
