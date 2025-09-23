from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Optional

from .database import Database
from .forms import get_form_definition, validate_responses
from .models import Inspection, InspectionNote, InspectionType, Truck, User, UserRole

PHOTO_MIN = 4
PHOTO_MAX = 10
NOTE_WINDOW_HOURS = 24


@dataclass
class InspectionService:
    database: Database

    def list_forms(self) -> dict[str, list[dict[str, object]]]:
        return {
            inspection_type.value: [
                {
                    "id": field.id,
                    "label": field.label,
                    "field_type": field.field_type.value,
                    "required": field.required,
                }
                for field in get_form_definition(inspection_type)
            ]
            for inspection_type in InspectionType
        }

    def create_inspection(
        self,
        *,
        inspection_type: InspectionType,
        truck: Truck,
        ranger: User,
        responses: dict,
        photo_urls: Iterable[str],
        video_url: Optional[str],
        escalate_visibility: bool = False,
    ) -> Inspection:
        if ranger.role not in {UserRole.RANGER, UserRole.SUPERVISOR}:
            raise PermissionError("Only rangers and supervisors may create inspections")
        if not truck.active:
            raise ValueError("Truck is not active")
        photo_list = list(photo_urls)
        if inspection_type is not InspectionType.RETURN:
            if len(photo_list) < PHOTO_MIN or len(photo_list) > PHOTO_MAX:
                raise ValueError("Between 4 and 10 photos are required")
        else:
            if len(photo_list) > PHOTO_MAX:
                raise ValueError("At most 10 photos are allowed")
        validated = validate_responses(inspection_type, responses)
        return self.database.add_inspection(
            inspection_type=inspection_type,
            truck_id=truck.id,
            ranger_id=ranger.id,
            escalate_visibility=escalate_visibility,
            responses=validated,
            photo_urls=photo_list,
            video_url=video_url,
        )

    def list_inspections(
        self,
        *,
        requester: User,
        truck: Optional[Truck] = None,
        ranger: Optional[User] = None,
    ) -> List[Inspection]:
        truck_id = truck.id if truck else None
        ranger_filter = ranger.id if ranger else None
        if requester.role == UserRole.RANGER:
            ranger_filter = requester.id
        inspections = list(self.database.list_inspections(truck_id=truck_id, ranger_id=ranger_filter))
        return inspections

    def get_inspection(self, *, requester: User, inspection_id: int) -> Inspection:
        inspection = self.database.get_inspection(inspection_id)
        if not inspection:
            raise LookupError("Inspection not found")
        if requester.role == UserRole.RANGER and inspection.ranger_id != requester.id:
            raise PermissionError("Rangers may only view their own inspections")
        return inspection

    def add_note(self, *, requester: User, inspection: Inspection, content: str) -> InspectionNote:
        if requester.role == UserRole.RANGER and inspection.ranger_id != requester.id:
            raise PermissionError("Cannot annotate another ranger's inspection")
        if datetime.utcnow() - inspection.created_at > timedelta(hours=NOTE_WINDOW_HOURS):
            raise ValueError("Notes can only be added within 24 hours of submission")
        note = self.database.add_note(inspection_id=inspection.id, author_id=requester.id, content=content)
        self.database.update_inspection_timestamp(inspection.id, note.created_at)
        return note

    def list_notes(self, inspection_id: int) -> List[InspectionNote]:
        return list(self.database.list_notes(inspection_id))

    def ranger_metrics(self) -> list[dict[str, object]]:
        metrics: list[dict[str, object]] = []
        inspections = list(self.database.list_inspections())
        for ranger in self.database.list_rangers():
            ranger_inspections = [insp for insp in inspections if insp.ranger_id == ranger.id]
            most_recent = max((insp.created_at for insp in ranger_inspections), default=None)
            metrics.append(
                {
                    "ranger": ranger,
                    "inspections_completed": len(ranger_inspections),
                    "most_recent_inspection": most_recent,
                }
            )
        return metrics

    def dashboard(self) -> dict[str, object]:
        inspections = list(self.database.list_inspections())
        escalated = sum(1 for insp in inspections if insp.escalate_visibility)
        return {
            "total_inspections": len(inspections),
            "escalated_inspections": escalated,
            "ranger_metrics": self.ranger_metrics(),
        }
