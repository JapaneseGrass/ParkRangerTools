from __future__ import annotations

from pathlib import Path
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.app import TruckInspectionApp
from backend.app.models import User, UserRole


@pytest.fixture()
def app(tmp_path: Path) -> TruckInspectionApp:
    app = TruckInspectionApp.create(tmp_path / "test_inspections.db")
    return app


@pytest.fixture()
def seeded_app(app: TruckInspectionApp) -> TruckInspectionApp:
    app.seed_defaults()
    return app


@pytest.fixture()
def ranger(seeded_app: TruckInspectionApp) -> User:
    user = seeded_app.database.get_user_by_email("ranger@email.com")
    assert user is not None
    return user


@pytest.fixture()
def supervisor(seeded_app: TruckInspectionApp) -> User:
    user = seeded_app.database.get_user_by_email("supervisor@email.com")
    assert user is not None
    return user


@pytest.fixture()
def truck(seeded_app: TruckInspectionApp):
    trucks = seeded_app.list_trucks()
    assert trucks, "Seed should provide trucks"
    return trucks[0]
