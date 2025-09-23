from __future__ import annotations

from http import HTTPStatus
from http.cookies import SimpleCookie
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

    def request(self, method: str, path: str, *, data: dict[str, str] | None = None, follow_redirects: bool = False):
        headers: dict[str, str] = {}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        body = b""
        if data is not None:
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
    assert "Quick report" in response.body


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
            form_data[field.id] = "All good"
        elif field.field_type is FieldType.NUMBER:
            form_data[field.id] = "123"
    form_data["photo_urls"] = "\n".join(f"https://example.com/photo-{index}" for index in range(1, 5))
    form_data["video_url"] = ""

    response = client.request(
        "POST",
        f"/trucks/{truck.id}/inspect/{InspectionType.QUICK.value}",
        data=form_data,
        follow_redirects=True,
    )
    assert "Inspection submitted successfully" in response.body
    assert f"Inspection" in response.body

    inspections = service.list_inspections(requester=user)
    assert inspections
    assert inspections[0].truck_id == truck.id
    assert inspections[0].inspection_type is InspectionType.QUICK


def test_supervisor_dashboard(client: FrontendClient):
    login(client, "sam.supervisor@example.com", "supervisorpass")
    response = client.request("GET", "/dashboard")
    assert response.status == HTTPStatus.OK
    assert "Supervisor dashboard" in response.body
