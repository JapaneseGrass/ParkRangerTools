from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .auth import AuthService
from .database import Database
from .inspections import InspectionService
from .models import (
    Inspection,
    InspectionNote,
    InspectionType,
    Truck,
    TruckAssignment,
    TruckReservation,
    User,
    UserRole,
)


@dataclass
class TruckInspectionApp:
    database: Database
    auth: AuthService
    inspections: InspectionService

    @classmethod
    def create(cls, database_path: Path) -> "TruckInspectionApp":
        database = Database(database_path)
        database.initialize()
        auth = AuthService(database)
        inspections = InspectionService(database)
        return cls(database=database, auth=auth, inspections=inspections)

    def seed_defaults(self) -> None:
        default_alex_questions = [
            ("What park was your first assignment?", "Rocky Ridge"),
            ("What is your ranger call sign?", "Alpha-1"),
            ("Favorite trail snack?", "Trail mix"),
        ]
        alex = self.database.get_user_by_email("alex.ranger@example.com")
        if not alex:
            self.auth.register_user(
                name="Alex Ranger",
                email="alex.ranger@example.com",
                password="rangerpass",
                security_responses=default_alex_questions,
                role=UserRole.RANGER,
                ranger_number="RN-1001",
            )
        elif not (alex.security_questions or []):
            self.auth.set_security_questions("alex.ranger@example.com", default_alex_questions)

        default_sam_questions = [
            ("What year did you join the parks team?", "2012"),
            ("Name of your first ranger partner?", "Jamie"),
            ("Favorite lookout point?", "Eagle Rock"),
        ]
        sam = self.database.get_user_by_email("sam.supervisor@example.com")
        if not sam:
            self.auth.register_user(
                name="Sam Supervisor",
                email="sam.supervisor@example.com",
                password="supervisorpass",
                security_responses=default_sam_questions,
                role=UserRole.SUPERVISOR,
                ranger_number="RN-2001",
            )
        elif not (sam.security_questions or []):
            self.auth.set_security_questions("sam.supervisor@example.com", default_sam_questions)
        truck_definitions = [
            ("SM88", None),
            ("P0106", None),
            ("P0101", None),
            ("P0103", None),
            ("427", None),
            ("T1", None),
            ("T2", None),
            ("T3", None),
        ]
        for identifier, description in truck_definitions:
            if not self.database.get_truck_by_identifier(identifier):
                self.database.add_truck(identifier, description)

    # Truck operations
    def list_trucks(self) -> List[Truck]:
        return list(self.database.list_active_trucks())

    def list_available_trucks(self) -> List[Truck]:
        active_assignments = {assignment.truck_id for assignment in self.database.list_active_assignments()}
        trucks = list(self.database.list_active_trucks())
        return [truck for truck in trucks if truck.id not in active_assignments]

    def get_active_assignment_for_truck(self, truck: Truck) -> Optional[TruckAssignment]:
        return self.database.get_active_assignment_for_truck(truck.id)

    def get_active_assignment_for_ranger(self, ranger: User) -> Optional[TruckAssignment]:
        return self.database.get_active_assignment_for_ranger(ranger.id)

    def list_active_assignments(self) -> List[TruckAssignment]:
        return list(self.database.list_active_assignments())

    def create_truck(self, *, identifier: str, description: Optional[str], supervisor: User) -> Truck:
        if supervisor.role != UserRole.SUPERVISOR:
            raise PermissionError("Only supervisors may create trucks")
        if self.database.get_truck_by_identifier(identifier):
            raise ValueError("Truck identifier already exists")
        return self.database.add_truck(identifier, description, active=True)

    def get_truck(self, truck_id: int) -> Truck:
        truck = self.database.get_truck(truck_id)
        if not truck:
            raise LookupError("Truck not found")
        return truck

    # Inspection operations
    def submit_inspection(
        self,
        *,
        user: User,
        truck: Truck,
        inspection_type: InspectionType,
        responses: dict,
        photo_urls: Iterable[str],
        video_url: Optional[str] = None,
        escalate_visibility: bool = False,
    ) -> Inspection:
        return self.inspections.create_inspection(
            inspection_type=inspection_type,
            truck=truck,
            ranger=user,
            responses=responses,
            photo_urls=photo_urls,
            video_url=video_url,
            escalate_visibility=escalate_visibility,
        )

    def list_inspections(
        self,
        *,
        requester: User,
        truck: Optional[Truck] = None,
        ranger: Optional[User] = None,
    ) -> List[Inspection]:
        return self.inspections.list_inspections(requester=requester, truck=truck, ranger=ranger)

    def get_inspection(self, *, requester: User, inspection_id: int) -> Inspection:
        return self.inspections.get_inspection(requester=requester, inspection_id=inspection_id)

    def add_note(self, *, requester: User, inspection: Inspection, content: str) -> InspectionNote:
        return self.inspections.add_note(requester=requester, inspection=inspection, content=content)

    def list_notes(self, inspection_id: int) -> List[InspectionNote]:
        return self.inspections.list_notes(inspection_id)

    def dashboard(self, *, supervisor: User) -> dict[str, object]:
        if supervisor.role != UserRole.SUPERVISOR:
            raise PermissionError("Dashboard is available to supervisors only")
        return self.inspections.dashboard()

    def get_forms(self) -> dict[str, list[dict[str, object]]]:
        return self.inspections.list_forms()

    def update_account(self, user_id: int, *, name: str, ranger_number: Optional[str]) -> User:
        return self.auth.update_profile(user_id=user_id, name=name, ranger_number=ranger_number)

    def checkout_truck(
        self,
        *,
        ranger: User,
        truck: Truck,
        inspection: Inspection,
    ) -> TruckAssignment:
        if self.database.get_active_assignment_for_truck(truck.id):
            raise ValueError("Truck is already checked out")
        start_miles = self._extract_odometer(inspection)
        assignment = self.database.add_assignment(
            truck_id=truck.id,
            ranger_id=ranger.id,
            start_inspection_id=inspection.id,
            start_miles=start_miles,
        )
        self.database.delete_reservation_for_truck(truck.id)
        return assignment

    def return_truck(
        self,
        *,
        assignment_id: int,
        ranger: User,
        inspection: Inspection,
    ) -> TruckAssignment:
        assignment = self.database.get_assignment(assignment_id)
        if not assignment:
            raise LookupError("Assignment not found")
        if assignment.returned_at is not None:
            raise ValueError("Truck has already been returned")
        if assignment.ranger_id != ranger.id and ranger.role != UserRole.SUPERVISOR:
            raise PermissionError("You cannot return this truck")
        if assignment.truck_id != inspection.truck_id:
            raise ValueError("Inspection does not match the checked out truck")
        end_miles = self._extract_odometer(inspection)
        if end_miles < assignment.start_miles:
            raise ValueError("Ending mileage cannot be less than the starting mileage")
        return self.database.close_assignment(
            assignment_id,
            end_inspection_id=inspection.id,
            end_miles=end_miles,
        )

    # Reservation operations
    def reserve_truck(
        self,
        *,
        requester: User,
        truck: Truck,
        note: Optional[str],
    ) -> TruckReservation:
        if self.database.get_active_assignment_for_truck(truck.id):
            raise ValueError("Truck is currently checked out and cannot be reserved.")
        existing = self.database.get_reservation_for_truck(truck.id)
        if existing and existing.user_id != requester.id and requester.role != UserRole.SUPERVISOR:
            raise ValueError("Truck already has a reservation.")
        clean_note = (note or "").strip()
        if len(clean_note) > 80:
            raise ValueError("Reservation note must be 80 characters or fewer.")
        if not clean_note:
            clean_note = self._default_reservation_note(requester)
        return self.database.add_or_update_reservation(
            truck_id=truck.id,
            user_id=requester.id,
            note=clean_note or None,
        )

    def cancel_reservation(
        self,
        *,
        requester: User,
        truck: Truck,
    ) -> None:
        reservation = self.database.get_reservation_for_truck(truck.id)
        if not reservation:
            raise ValueError("No reservation exists for this truck.")
        if reservation.user_id != requester.id:
            raise PermissionError("You cannot cancel another ranger's reservation.")
        self.database.delete_reservation_for_truck(truck.id)

    def list_truck_reservations(self) -> list[TruckReservation]:
        return list(self.database.list_reservations())

    def update_reservation_note(
        self,
        *,
        requester: User,
        truck: Truck,
        note: Optional[str],
    ) -> TruckReservation:
        reservation = self.database.get_reservation_for_truck(truck.id)
        if not reservation:
            raise ValueError("No reservation exists for this truck.")
        if reservation.user_id != requester.id:
            raise PermissionError("You cannot update another ranger's reservation.")
        clean_note = (note or "").strip()
        if len(clean_note) > 80:
            raise ValueError("Reservation note must be 80 characters or fewer.")
        owner = self.database.get_user(reservation.user_id) or requester
        if not clean_note:
            clean_note = self._default_reservation_note(owner)
        return self.database.add_or_update_reservation(
            truck_id=truck.id,
            user_id=reservation.user_id,
            note=clean_note,
        )

    def _default_reservation_note(self, user: User) -> str:
        number = (user.ranger_number or "").strip()
        digits = "".join(ch for ch in number if ch.isdigit())
        suffix = digits[-2:] if len(digits) >= 2 else digits or "--"
        return f"Reserved by Ranger {suffix}"

    @staticmethod
    def _extract_odometer(inspection: Inspection) -> int:
        miles = inspection.responses.get("odometer_miles")
        if miles is None:
            raise ValueError("Inspection must include mileage")
        try:
            return int(miles)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid mileage value") from exc


if __name__ == "__main__":  # pragma: no cover - manual interaction helper
    app = TruckInspectionApp.create(Path("truck_inspections.db"))
    app.seed_defaults()
    print("Truck Inspection App ready.")
    print("Default ranger login: alex.ranger@example.com / rangerpass")
    print("Default supervisor login: sam.supervisor@example.com / supervisorpass")
    print("Use this module within Python to interact with services programmatically.")
