from __future__ import annotations

from http import HTTPStatus
from http.cookies import SimpleCookie
import secrets
from pathlib import Path
from urllib.parse import urlencode

import pytest

from backend.app.forms import FieldType, get_form_definition
from backend.app.models import InspectionType
from frontend.app import Request, create_app


class FrontendClient:
    def __init__(self, app):
        self.app = app
        self.cookies: dict[str, str] = {}

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, str] | None = None,
        files: dict[str, list[tuple[str, bytes, str]]] | None = None,
        follow_redirects: bool = False,
    ):
        headers: dict[str, str] = {}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        body = b""
        if files:
            boundary = "----WebKitFormBoundary" + secrets.token_hex(16)
            parts: list[bytes] = []
            for key, value in (data or {}).items():
                parts.append(
                    (
                        f"--{boundary}\r\n"
                        f"Content-Disposition: form-data; name=\"{key}\"\r\n\r\n"
                        f"{value}\r\n"
                    ).encode("utf-8")
                )
            for field, entries in files.items():
                for filename, content, content_type in entries:
                    parts.append(
                        (
                            f"--{boundary}\r\n"
                            f"Content-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
                            f"Content-Type: {content_type}\r\n\r\n"
                        ).encode("utf-8")
                    )
                    parts.append(content + b"\r\n")
            parts.append(f"--{boundary}--\r\n".encode("utf-8"))
            body = b"".join(parts)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif data is not None:
            body = urlencode(data, doseq=True).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(method=method, target=path, headers=headers, body=body)
        response = self.app.handle(request)
        for name, value in response.headers:
            if name.lower() == "set-cookie":
                cookie = SimpleCookie()
                cookie.load(value)
                for key in cookie:
                    if cookie[key]["max-age"] == "0":
                        self.cookies.pop(key, None)
                    else:
                        self.cookies[key] = cookie[key].value
        if follow_redirects and 300 <= response.status.value < 400:
            location = dict(response.headers).get("Location")
            if location:
                return self.request("GET", location, follow_redirects=True)
        return response


@pytest.fixture
def app(tmp_path: Path):
    db_path = tmp_path / "frontend_test.db"
    return create_app(db_path)


@pytest.fixture
def client(app):
    return FrontendClient(app)


def login(client: FrontendClient, email: str, password: str):
    return client.request(
        "POST",
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def test_ranger_login_and_dashboard(client: FrontendClient):
    response = login(client, "alex.ranger@example.com", "rangerpass")
    assert "Welcome, Alex Ranger!" in response.body
    assert "Check out (Quick)" in response.body


def test_submit_quick_inspection(app, client: FrontendClient):
    login(client, "alex.ranger@example.com", "rangerpass")
    service = app.service
    user = service.database.get_user_by_email("alex.ranger@example.com")
    assert user is not None
    truck = service.list_trucks()[0]

    form_definition = get_form_definition(InspectionType.QUICK)
    form_data: dict[str, str] = {}
    for field in form_definition:
        if field.field_type is FieldType.BOOLEAN:
            form_data[field.id] = "yes"
        elif field.field_type is FieldType.TEXT:
            if field.id == "fuel_level":
                form_data[field.id] = "75"
            else:
                form_data[field.id] = "All good"
        elif field.field_type is FieldType.NUMBER:
            form_data[field.id] = "123"
    form_data["escalate_visibility"] = "0"
    form_data["action"] = "checkout"

    files = {
        "photos": [
            (f"photo-{index}.jpg", b"binarydata", "image/jpeg")
            for index in range(1, 5)
        ]
    }

    response = client.request(
        "POST",
        f"/trucks/{truck.id}/inspect/{InspectionType.QUICK.value}?action=checkout",
        data=form_data,
        files=files,
        follow_redirects=True,
    )
    assert "Truck checked out successfully" in response.body
    assert f"Inspection" in response.body

    inspections = service.list_inspections(requester=user)
    assert inspections
    assert inspections[0].truck_id == truck.id
    assert inspections[0].inspection_type is InspectionType.QUICK
    assert all(photo.startswith("/uploads/") for photo in inspections[0].photo_urls)

    assignment = service.get_active_assignment_for_ranger(user)
    assert assignment is not None
    assert assignment.truck_id == truck.id
    assert assignment.start_miles == 123


def test_supervisor_dashboard(client: FrontendClient):
    login(client, "sam.supervisor@example.com", "supervisorpass")
    response = client.request("GET", "/dashboard")
    assert response.status == HTTPStatus.OK
    assert "Supervisor dashboard" in response.body


def test_incomplete_inspection_preserves_form(app, client: FrontendClient):
    login(client, "alex.ranger@example.com", "rangerpass")
    service = app.service
    user = service.database.get_user_by_email("alex.ranger@example.com")
    assert user is not None
    truck = service.list_trucks()[0]

    form_definition = get_form_definition(InspectionType.QUICK)
    form_data: dict[str, str] = {}
    for field in form_definition:
        if field.field_type is FieldType.BOOLEAN:
            form_data[field.id] = "yes"
        elif field.field_type is FieldType.TEXT:
            if field.id == "fuel_level":
                form_data[field.id] = "75"
            else:
                form_data[field.id] = "All good"
        elif field.field_type is FieldType.NUMBER:
            form_data[field.id] = "123"
    form_data["escalate_visibility"] = "1"
    form_data["action"] = "checkout"

    response = client.request(
        "POST",
        f"/trucks/{truck.id}/inspect/{InspectionType.QUICK.value}?action=checkout",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status == HTTPStatus.OK
    assert "Please provide between 4 and 10 photos." in response.body
    assert "name=\"exterior_clean\" value=\"yes\" checked" in response.body
    assert "data-fuel-value>75%" in response.body
    assert "escalate_visibility\" id=\"escalate_visibility\" value=\"1\"" in response.body
    assert "aria-pressed=\"true\"" in response.body


def test_ranger_can_return_truck(app, client: FrontendClient):
    login(client, "alex.ranger@example.com", "rangerpass")
    service = app.service
    user = service.database.get_user_by_email("alex.ranger@example.com")
    assert user is not None
    truck = service.list_trucks()[0]

    # Checkout the truck first
    checkout_form = get_form_definition(InspectionType.QUICK)
    checkout_data: dict[str, str] = {}
    for field in checkout_form:
        if field.field_type is FieldType.BOOLEAN:
            checkout_data[field.id] = "yes"
        elif field.field_type is FieldType.TEXT:
            checkout_data[field.id] = "72" if field.id == "fuel_level" else "Initial notes"
        elif field.field_type is FieldType.NUMBER:
            checkout_data[field.id] = "1000"
    checkout_data["escalate_visibility"] = "0"
    checkout_data["action"] = "checkout"

    checkout_files = {
        "photos": [
            (f"start-{index}.jpg", b"startdata", "image/jpeg")
            for index in range(1, 5)
        ]
    }

    checkout_response = client.request(
        "POST",
        f"/trucks/{truck.id}/inspect/{InspectionType.QUICK.value}?action=checkout",
        data=checkout_data,
        files=checkout_files,
        follow_redirects=True,
    )
    assert "Truck checked out successfully" in checkout_response.body

    assignment = service.get_active_assignment_for_ranger(user)
    assert assignment is not None

    # Return the truck with higher mileage (no photos required)
    return_form = get_form_definition(InspectionType.RETURN)
    return_data: dict[str, str] = {}
    for field in return_form:
        if field.field_type is FieldType.NUMBER:
            return_data[field.id] = "1010"
        elif field.field_type is FieldType.TEXT:
            return_data[field.id] = "All clear"
    return_data["action"] = "return"
    return_data["assignment_id"] = str(assignment.id)

    return_response = client.request(
        "POST",
        f"/trucks/{truck.id}/inspect/{InspectionType.RETURN.value}?action=return&assignment={assignment.id}",
        data=return_data,
        files=None,
        follow_redirects=True,
    )
    assert "Truck returned successfully" in return_response.body

    updated_assignment = service.database.get_assignment(assignment.id)
    assert updated_assignment is not None
    assert updated_assignment.returned_at is not None
    assert updated_assignment.end_miles == 1010

    available_ids = {truck.id for truck in service.list_available_trucks()}
    assert assignment.truck_id in available_ids

    inspections = service.list_inspections(requester=user)
    assert inspections[0].inspection_type is InspectionType.RETURN


def test_supervisor_can_submit_inspection(app, client: FrontendClient):
    response = login(client, "sam.supervisor@example.com", "supervisorpass")
    assert "Quick inspection" in response.body

    service = app.service
    user = service.database.get_user_by_email("sam.supervisor@example.com")
    assert user is not None
    truck = service.list_trucks()[0]

    form_definition = get_form_definition(InspectionType.QUICK)
    form_data: dict[str, str] = {}
    for field in form_definition:
        if field.field_type is FieldType.BOOLEAN:
            form_data[field.id] = "yes"
        elif field.field_type is FieldType.TEXT:
            if field.id == "fuel_level":
                form_data[field.id] = "80"
            else:
                form_data[field.id] = "Supervisor check"
        elif field.field_type is FieldType.NUMBER:
            form_data[field.id] = "456"
    form_data["escalate_visibility"] = "0"
    form_data["action"] = "checkout"

    files = {
        "photos": [
            (f"photo-{index}.jpg", b"binarydata", "image/jpeg")
            for index in range(1, 5)
        ]
    }

    response = client.request(
        "POST",
        f"/trucks/{truck.id}/inspect/{InspectionType.QUICK.value}?action=checkout",
        data=form_data,
        files=files,
        follow_redirects=True,
    )
    assert "Truck checked out successfully" in response.body

    inspections = service.list_inspections(requester=user, ranger=user)
    assert inspections
    latest = inspections[-1]
    assert latest.truck_id == truck.id
    assert latest.inspection_type is InspectionType.QUICK
