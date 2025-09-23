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
        if not self.database.get_user_by_email("alex.ranger@example.com"):
            self.auth.register_user(
                name="Alex Ranger",
                email="alex.ranger@example.com",
                password="rangerpass",
                role=UserRole.RANGER,
            )
        if not self.database.get_user_by_email("sam.supervisor@example.com"):
            self.auth.register_user(
                name="Sam Supervisor",
                email="sam.supervisor@example.com",
                password="supervisorpass",
                role=UserRole.SUPERVISOR,
            )
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
        return self.database.add_assignment(
            truck_id=truck.id,
            ranger_id=ranger.id,
            start_inspection_id=inspection.id,
            start_miles=start_miles,
        )

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
