"""Utility helpers for seeding a sizeable set of mock inspections."""

from __future__ import annotations

import argparse
import random
import textwrap
import uuid
from pathlib import Path

from .app import TruckInspectionApp
from .auth import ALLOWED_EMAIL_ROLES
from .forms import FieldType, get_form_definition
from .models import InspectionType, UserRole

_SAMPLE_PNG = bytes(
    [
        0x89,
        0x50,
        0x4E,
        0x47,
        0x0D,
        0x0A,
        0x1A,
        0x0A,
        0x00,
        0x00,
        0x00,
        0x0D,
        0x49,
        0x48,
        0x44,
        0x52,
        0x00,
        0x00,
        0x00,
        0x10,
        0x00,
        0x00,
        0x00,
        0x10,
        0x08,
        0x02,
        0x00,
        0x00,
        0x00,
        0x90,
        0x91,
        0x68,
        0x36,
        0x00,
        0x00,
        0x00,
        0x0C,
        0x49,
        0x44,
        0x41,
        0x54,
        0x78,
        0x9C,
        0x63,
        0xF8,
        0xCF,
        0x00,
        0x00,
        0x02,
        0x25,
        0x01,
        0x21,
        0xE2,
        0x26,
        0x56,
        0x00,
        0x00,
        0x00,
        0x00,
        0x49,
        0x45,
        0x4E,
        0x44,
        0xAE,
        0x42,
        0x60,
        0x82,
    ]
)


def _ensure_rangers(app: TruckInspectionApp, *, desired: int, rng: random.Random) -> list:
    rangers = list(app.database.list_rangers())
    while len(rangers) < desired:
        index = len(rangers) + 1
        email = f"mock.ranger{index}@park.example"
        normalized = email.lower()
        ALLOWED_EMAIL_ROLES.setdefault(normalized, UserRole.RANGER)
        if app.database.get_user_by_email(email):
            index += 1
            continue
        responses = [
            ("Favorite lookout?", f"Ridge {index}"),
            ("First badge number?", f"{1000 + index}"),
            ("Preferred snack?", "Trail mix"),
        ]
        user = app.auth.register_user(
            name=f"Mock Ranger {index}",
            email=email,
            password="password",
            security_responses=responses,
            role=UserRole.RANGER,
            ranger_number=f"RN-{5000 + index}",
        )
        rangers.append(user)
    return rangers


def _build_responses(inspection_type: InspectionType, *, rng: random.Random, miles: int) -> dict[str, object]:
    responses: dict[str, object] = {}
    for field in get_form_definition(inspection_type):
        if field.field_type is FieldType.BOOLEAN:
            value = rng.random() > 0.08
            if field.id == "fluid_leak_detected":
                value = rng.random() < 0.05
            responses[field.id] = value
        elif field.field_type is FieldType.NUMBER:
            if field.id == "odometer_miles":
                responses[field.id] = miles
            else:
                responses[field.id] = rng.randint(0, 10)
        elif field.field_type is FieldType.TEXT:
            if field.id == "fuel_level":
                responses[field.id] = str(rng.randint(35, 100))
            elif field.required:
                responses[field.id] = rng.choice(
                    [
                        "All clear",
                        "Minor dust",
                        "Ready for patrol",
                        "Needs wipe-down",
                    ]
                )
            else:
                snippet = rng.choice(
                    [
                        "",
                        "Updated inventory",
                        "Added med kit",
                        "",
                        "Replaced wiper fluid",
                    ]
                )
                responses[field.id] = snippet
    return responses


def _create_mock_photos(upload_dir: Path, *, count: int, prefix: str) -> list[str]:
    upload_dir.mkdir(parents=True, exist_ok=True)
    photo_urls: list[str] = []
    for _ in range(count):
        filename = f"{prefix}-{uuid.uuid4().hex}.png"
        path = upload_dir / filename
        path.write_bytes(_SAMPLE_PNG)
        photo_urls.append(f"/uploads/{filename}")
    return photo_urls


def generate_mock_data(
    app: TruckInspectionApp,
    *,
    total_pairs: int = 60,
    seed: int = 42,
) -> None:
    rng = random.Random(seed)
    trucks = list(app.list_trucks())
    if not trucks:
        raise RuntimeError("No trucks available; seed defaults before generating mock data")

    rangers = _ensure_rangers(app, desired=6, rng=rng)
    uploads_dir = Path(__file__).resolve().parents[2] / "frontend" / "uploads"

    for index in range(total_pairs):
        truck = trucks[index % len(trucks)]
        ranger = rangers[index % len(rangers)]
        base_miles = 1200 + index * 12
        inspection_type = InspectionType.DETAILED if index % 3 == 0 else InspectionType.QUICK
        responses = _build_responses(inspection_type, rng=rng, miles=base_miles)
        prefix = f"mock-{truck.identifier.lower()}"
        photo_count = rng.randint(4, 6)
        photos = _create_mock_photos(uploads_dir, count=photo_count, prefix=prefix)
        escalate = rng.random() < 0.12

        checkout_inspection = app.submit_inspection(
            user=ranger,
            truck=truck,
            inspection_type=inspection_type,
            responses=responses,
            photo_urls=photos,
            escalate_visibility=escalate,
        )
        assignment = app.checkout_truck(ranger=ranger, truck=truck, inspection=checkout_inspection)

        if rng.random() < 0.4:
            app.add_note(
                requester=ranger,
                inspection=checkout_inspection,
                content=rng.choice(
                    [
                        "Replaced low tire pressure sensor.",
                        "Cab light out, leaving note for maintenance.",
                        "Fuel card stored in visor.",
                    ]
                ),
            )

        end_miles = base_miles + rng.randint(10, 80)
        return_responses = {
            "odometer_miles": end_miles,
            "return_notes": rng.choice(
                [
                    "Back at HQ lot.",
                    "Washed exterior.",
                    "Cab cleaned after patrol.",
                    "",
                ]
            ),
        }

        return_inspection = app.submit_inspection(
            user=ranger,
            truck=truck,
            inspection_type=InspectionType.RETURN,
            responses=return_responses,
            photo_urls=[],
        )
        app.return_truck(assignment_id=assignment.id, ranger=ranger, inspection=return_inspection)


def _summarize(app: TruckInspectionApp) -> str:
    supervisor = app.database.get_user_by_email("supervisor@email.com")
    if supervisor is not None:
        inspections = list(app.list_inspections(requester=supervisor))
    else:
        inspections = list(app.database.list_inspections())
    total = len(inspections)
    escalated = sum(1 for insp in inspections if insp.escalate_visibility)
    return textwrap.dedent(
        f"""
        Generated {total} inspections ({escalated} escalated).
        Photos saved under frontend/uploads/. Re-run the export to include new data.
        """
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mock inspection data.")
    parser.add_argument(
        "--database",
        default="truck_inspections.db",
        help="Path to the SQLite database file (default: %(default)s)",
    )
    parser.add_argument(
        "--pairs",
        type=int,
        default=60,
        help="Number of checkout/return pairs to generate (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible data (default: %(default)s)",
    )
    args = parser.parse_args()

    db_path = Path(args.database)
    app = TruckInspectionApp.create(db_path)
    app.seed_defaults()
    generate_mock_data(app, total_pairs=args.pairs, seed=args.seed)
    print(_summarize(app))


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
