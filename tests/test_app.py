from __future__ import annotations

import inspect
from datetime import datetime, timedelta

import pytest

from backend.app import TruckInspectionApp
from backend.app.auth import TOKEN_EXPIRY_MINUTES


def test_dataclasses_do_not_use_slots() -> None:
    from backend.app import app as app_module
    from backend.app import auth as auth_module
    from backend.app import forms as forms_module
    from backend.app import inspections as inspections_module
    from backend.app import models as models_module

    modules = [app_module, auth_module, forms_module, inspections_module, models_module]
    dataclass_params = []
    for module in modules:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            params = getattr(obj, "__dataclass_params__", None)
            if params is not None:
                dataclass_params.append(params)

    assert dataclass_params, "Expected to discover dataclasses in backend modules"
    assert all(
        not getattr(params, "slots", False) for params in dataclass_params
    ), "Dataclasses must not request slots for Python 3.9 compatibility"
from backend.app.models import InspectionType, User, UserRole


def _quick_responses() -> dict[str, object]:
    return {
        "exterior_clean": True,
        "interior_clean": True,
        "seatbelts_functioning": True,
        "tire_inflation": True,
        "fuel_level": "75",
        "odometer_miles": 1200,
    }


def _detailed_responses() -> dict[str, object]:
    responses = _quick_responses()
    responses.update(
        {
            "engine_oil_ok": True,
            "fan_belts_ok": True,
            "coolant_level_ok": True,
            "washer_fluid_ok": True,
            "wipers_ok": True,
            "tire_tread_ok": True,
            "headlights_ok": True,
            "turn_signals_ok": True,
            "brake_lights_ok": True,
            "reverse_lights_ok": True,
            "fluid_leak_detected": False,
            "mirrors_ok": True,
            "emergency_system_ok": True,
        }
    )
    return responses


def _photos() -> list[str]:
    return [
        "photo1.jpg",
        "photo2.jpg",
        "photo3.jpg",
        "photo4.jpg",
    ]


def test_authentication_success(seeded_app: TruckInspectionApp) -> None:
    token = seeded_app.auth.authenticate("alex.ranger@example.com", "rangerpass")
    assert token is not None
    delta = token.expires_at - token.created_at
    assert abs(delta - timedelta(minutes=TOKEN_EXPIRY_MINUTES)) < timedelta(seconds=1)


def test_authentication_failure(seeded_app: TruckInspectionApp) -> None:
    token = seeded_app.auth.authenticate("alex.ranger@example.com", "wrongpass")
    assert token is None


def test_ranger_submits_quick_inspection(seeded_app: TruckInspectionApp, ranger: User, truck) -> None:
    inspection = seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.QUICK,
        responses=_quick_responses(),
        photo_urls=_photos(),
    )
    assert inspection.truck_id == truck.id
    assert inspection.ranger_id == ranger.id
    assert inspection.responses["fuel_level"] == "75"


def test_photo_validation(seeded_app: TruckInspectionApp, ranger: User, truck) -> None:
    with pytest.raises(ValueError):
        seeded_app.submit_inspection(
            user=ranger,
            truck=truck,
            inspection_type=InspectionType.QUICK,
            responses=_quick_responses(),
            photo_urls=_photos()[:3],
        )


def test_notes_within_window(seeded_app: TruckInspectionApp, ranger: User, truck) -> None:
    inspection = seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.DETAILED,
        responses=_detailed_responses(),
        photo_urls=_photos(),
    )
    note = seeded_app.add_note(requester=ranger, inspection=inspection, content="Follow-up")
    assert note.content == "Follow-up"


def test_notes_after_window_fails(seeded_app: TruckInspectionApp, ranger: User, truck) -> None:
    inspection = seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.QUICK,
        responses=_quick_responses(),
        photo_urls=_photos(),
    )
    past = datetime.utcnow() - timedelta(hours=25)
    with seeded_app.database.session() as conn:
        conn.execute(
            "UPDATE inspections SET created_at = ?, updated_at = ? WHERE id = ?",
            (
                past.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                past.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                inspection.id,
            ),
        )
    inspection = seeded_app.database.get_inspection(inspection.id)
    assert inspection is not None
    with pytest.raises(ValueError):
        seeded_app.add_note(requester=ranger, inspection=inspection, content="Too late")


def test_dashboard_metrics(seeded_app: TruckInspectionApp, ranger: User, supervisor: User, truck) -> None:
    seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.QUICK,
        responses=_quick_responses(),
        photo_urls=_photos(),
    )
    seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.QUICK,
        responses=_quick_responses(),
        photo_urls=_photos(),
        escalate_visibility=True,
    )
    # Perform checkout/return to contribute to compliance totals
    start_inspection = seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.QUICK,
        responses=_quick_responses(),
        photo_urls=_photos(),
    )
    assignment = seeded_app.checkout_truck(ranger=ranger, truck=truck, inspection=start_inspection)
    end_inspection = seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.RETURN,
        responses={"odometer_miles": 2000, "return_notes": "Done"},
        photo_urls=[],
    )
    seeded_app.return_truck(assignment_id=assignment.id, ranger=ranger, inspection=end_inspection)

    dashboard = seeded_app.dashboard(supervisor=supervisor)
    assert dashboard["total_inspections"] == 1
    assert dashboard["escalated_inspections"] == 1
    metrics = dashboard["personnel_metrics"]
    ranger_entry = next(entry for entry in metrics if entry["user"].id == ranger.id)
    supervisor_entry = next(entry for entry in metrics if entry["user"].id == supervisor.id)
    assert ranger_entry["inspections_completed"] == 1
    assert supervisor_entry["inspections_completed"] == 0


def test_ranger_only_sees_own_inspections(seeded_app: TruckInspectionApp, ranger: User, supervisor: User, truck) -> None:
    other = seeded_app.auth.register_user(
        name="Other Ranger",
        email="other@example.com",
        password="password123",
        role=UserRole.RANGER,
    )
    seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.QUICK,
        responses=_quick_responses(),
        photo_urls=_photos(),
    )
    seeded_app.submit_inspection(
        user=other,
        truck=truck,
        inspection_type=InspectionType.QUICK,
        responses=_quick_responses(),
        photo_urls=_photos(),
    )
    ranger_inspections = seeded_app.list_inspections(requester=ranger)
    assert len(ranger_inspections) == 1
    supervisor_inspections = seeded_app.list_inspections(requester=supervisor)
    assert len(supervisor_inspections) == 2


def test_seeded_truck_identifiers(seeded_app: TruckInspectionApp) -> None:
    identifiers = {truck.identifier for truck in seeded_app.list_trucks()}
    assert identifiers == {
        "427",
        "P0101",
        "P0103",
        "P0106",
        "SM88",
        "T1",
        "T2",
        "T3",
    }


def test_checkout_and_return_flow(seeded_app: TruckInspectionApp, ranger: User, truck) -> None:
    start_inspection = seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.QUICK,
        responses={
            "exterior_clean": True,
            "interior_clean": True,
            "seatbelts_functioning": True,
            "tire_inflation": True,
            "fuel_level": "80",
            "odometer_miles": 1000,
        },
        photo_urls=["start1.jpg", "start2.jpg", "start3.jpg", "start4.jpg"],
    )

    assignment = seeded_app.checkout_truck(ranger=ranger, truck=truck, inspection=start_inspection)
    assert assignment.start_miles == 1000

    available_ids = {t.id for t in seeded_app.list_available_trucks()}
    assert truck.id not in available_ids

    end_inspection = seeded_app.submit_inspection(
        user=ranger,
        truck=truck,
        inspection_type=InspectionType.RETURN,
        responses={
            "odometer_miles": 1012,
            "return_notes": "All clear",
        },
        photo_urls=[],
    )

    completed = seeded_app.return_truck(assignment_id=assignment.id, ranger=ranger, inspection=end_inspection)
    assert completed.end_miles == 1012
    assert completed.returned_at is not None

    available_ids = {t.id for t in seeded_app.list_available_trucks()}
    assert truck.id in available_ids
