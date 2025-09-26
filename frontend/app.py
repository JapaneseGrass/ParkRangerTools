from __future__ import annotations

import html
import mimetypes
import secrets
import uuid
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import parse_qs, urlparse

from backend.app.app import TruckInspectionApp
from backend.app.forms import FieldType, get_form_definition
from backend.app.models import Inspection, InspectionType, Truck, TruckAssignment, User, UserRole
from backend.app.auth import ALLOWED_EMAIL_ROLES


TRUCK_CATEGORY_MAP: dict[str, str] = {
    "SM88": "full_size",
    "P0106": "full_size",
    "P0101": "mid_size",
    "P0103": "mid_size",
    "427": "mid_size",
    "T1": "maintenance",
    "T2": "maintenance",
    "T3": "maintenance",
}

TRUCK_CATEGORY_INFO: dict[str, dict[str, str]] = {
    "full_size": {
        "label": "Ford F-150",
        "badge_class": "full-size",
        "icon": """
        <svg class=\"truck-icon\" viewBox=\"0 0 140 64\" role=\"img\" aria-label=\"Full-size pickup\">
          <rect x=\"18\" y=\"30\" width=\"90\" height=\"22\" rx=\"6\" fill=\"#2f6b3c\" />
          <rect x=\"82\" y=\"22\" width=\"36\" height=\"20\" rx=\"6\" fill=\"#24512c\" />
          <rect x=\"90\" y=\"26\" width=\"20\" height=\"12\" rx=\"3\" fill=\"#e6f2eb\" />
          <rect x=\"30\" y=\"32\" width=\"18\" height=\"8\" rx=\"3\" fill=\"#f8e1a0\" />
          <circle cx=\"42\" cy=\"56\" r=\"9\" fill=\"#1f2a24\" />
          <circle cx=\"96\" cy=\"56\" r=\"9\" fill=\"#1f2a24\" />
          <circle cx=\"42\" cy=\"56\" r=\"4\" fill=\"#d4dad6\" />
          <circle cx=\"96\" cy=\"56\" r=\"4\" fill=\"#d4dad6\" />
        </svg>
        """,
    },
    "mid_size": {
        "label": "Chevy Colorado",
        "badge_class": "mid-size",
        "icon": """
        <svg class=\"truck-icon\" viewBox=\"0 0 140 64\" role=\"img\" aria-label=\"Mid-size pickup\">
          <rect x=\"20\" y=\"32\" width=\"80\" height=\"20\" rx=\"6\" fill=\"#c47a3a\" />
          <rect x=\"74\" y=\"24\" width=\"32\" height=\"18\" rx=\"6\" fill=\"#a9622a\" />
          <rect x=\"80\" y=\"28\" width=\"16\" height=\"10\" rx=\"3\" fill=\"#f4e6da\" />
          <rect x=\"28\" y=\"34\" width=\"16\" height=\"6\" rx=\"3\" fill=\"#f6d28f\" />
          <circle cx=\"40\" cy=\"56\" r=\"8.5\" fill=\"#1f2a24\" />
          <circle cx=\"92\" cy=\"56\" r=\"8.5\" fill=\"#1f2a24\" />
          <circle cx=\"40\" cy=\"56\" r=\"3.8\" fill=\"#f4dfc6\" />
          <circle cx=\"92\" cy=\"56\" r=\"3.8\" fill=\"#f4dfc6\" />
        </svg>
        """,
    },
    "maintenance": {
        "label": "F-150 Flatbed",
        "badge_class": "maintenance",
        "icon": """
        <svg class=\"truck-icon\" viewBox=\"0 0 148 64\" role=\"img\" aria-label=\"Flatbed pickup\">
          <rect x=\"20\" y=\"34\" width=\"58\" height=\"20\" rx=\"5\" fill=\"#6c7568\" />
          <rect x=\"74\" y=\"26\" width=\"32\" height=\"18\" rx=\"6\" fill=\"#879182\" />
          <rect x=\"104\" y=\"34\" width=\"22\" height=\"20\" rx=\"4\" fill=\"#a0a89c\" />
          <rect x=\"80\" y=\"30\" width=\"16\" height=\"10\" rx=\"3\" fill=\"#edf0e6\" />
          <rect x=\"26\" y=\"36\" width=\"20\" height=\"6\" rx=\"2\" fill=\"#f7d56b\" />
          <circle cx=\"38\" cy=\"56\" r=\"8.5\" fill=\"#1f2a24\" />
          <circle cx=\"92\" cy=\"56\" r=\"8.5\" fill=\"#1f2a24\" />
          <circle cx=\"38\" cy=\"56\" r=\"3.8\" fill=\"#dfe8de\" />
          <circle cx=\"92\" cy=\"56\" r=\"3.8\" fill=\"#dfe8de\" />
        </svg>
        """,
    },
    "default": {
        "label": "Park vehicle",
        "badge_class": "default",
        "icon": """
        <svg class=\"truck-icon\" viewBox=\"0 0 140 68\" role=\"img\" aria-label=\"Park vehicle\">
          <rect x=\"20\" y=\"34\" width=\"66\" height=\"20\" rx=\"6\" fill=\"#4f7460\" />
          <rect x=\"68\" y=\"26\" width=\"30\" height=\"18\" rx=\"6\" fill=\"#6d8f7f\" />
          <circle cx=\"36\" cy=\"56\" r=\"8\" fill=\"#2b2b2b\" />
          <circle cx=\"82\" cy=\"56\" r=\"8\" fill=\"#2b2b2b\" />
          <circle cx=\"36\" cy=\"56\" r=\"3.5\" fill=\"#dfe8de\" />
          <circle cx=\"82\" cy=\"56\" r=\"3.5\" fill=\"#dfe8de\" />
        </svg>
        """,
    },
}


def backend_role_for_email(email: str) -> UserRole:
    normalized = email.strip().lower()
    role = ALLOWED_EMAIL_ROLES.get(normalized)
    if role is None:
        raise ValueError("Registration is restricted to approved park ranger accounts.")
    return role


@dataclass
class UploadedFile:
    filename: str
    content_type: str
    data: bytes

@dataclass
class Request:
    method: str
    target: str
    headers: dict[str, str]
    body: bytes = b""

    def __post_init__(self) -> None:
        parsed = urlparse(self.target)
        self.path = parsed.path or "/"
        self.query = parse_qs(parsed.query)
        self.form: dict[str, list[str]] = {}
        self.files: dict[str, list[UploadedFile]] = {}
        if self.method in {"POST", "PUT"}:
            content_type = self.headers.get("Content-Type", "")
            if "application/x-www-form-urlencoded" in content_type:
                self.form = parse_qs(self.body.decode("utf-8"))
            elif "multipart/form-data" in content_type:
                self._parse_multipart(content_type)
        cookie_header = self.headers.get("Cookie", "")
        cookie = SimpleCookie(cookie_header)
        self.cookies = {key: morsel.value for key, morsel in cookie.items()}

    def form_value(self, name: str, default: Optional[str] = None) -> Optional[str]:
        values = self.form.get(name)
        return values[0] if values else default

    def form_values(self, name: str) -> list[str]:
        return self.form.get(name, [])

    def file_values(self, name: str) -> list[UploadedFile]:
        return self.files.get(name, [])

    def _parse_multipart(self, content_type: str) -> None:
        message = BytesParser(policy=default).parsebytes(
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + self.body
        )
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            name = part.get_param("name", header="Content-Disposition")
            if not name:
                continue
            filename = part.get_param("filename", header="Content-Disposition")
            payload = part.get_payload(decode=True)
            if filename:
                upload = UploadedFile(
                    filename=filename,
                    content_type=part.get_content_type(),
                    data=payload,
                )
                self.files.setdefault(name, []).append(upload)
            else:
                charset = part.get_content_charset("utf-8") or "utf-8"
                value = payload.decode(charset)
                self.form.setdefault(name, []).append(value)

    def cookie(self, name: str) -> Optional[str]:
        return self.cookies.get(name)


@dataclass
class Response:
    status: int = HTTPStatus.OK
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes | str = ""

    def set_cookie(self, name: str, value: str, *, path: str = "/", max_age: Optional[int] = None) -> None:
        cookie = SimpleCookie()
        cookie[name] = value
        cookie[name]["path"] = path
        if max_age is not None:
            cookie[name]["max-age"] = str(max_age)
        header_value = cookie.output(header="")
        self.headers.append(("Set-Cookie", header_value.strip()))

    def add_header(self, name: str, value: str) -> None:
        self.headers.append((name, value))


class TruckInspectionWebApp:
    def __init__(self, database_path: Path) -> None:
        self.service = TruckInspectionApp.create(database_path)
        self.service.seed_defaults()
        self.sessions: dict[str, int] = {}
        self.flash_messages: dict[str, list[tuple[str, str]]] = {}
        self.static_dir = Path(__file__).parent / "static"
        self.upload_dir = Path(__file__).parent / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    # Public API -----------------------------------------------------------------
    def wsgi_app(self, environ: dict[str, Any], start_response: Callable) -> Iterable[bytes]:
        method = environ["REQUEST_METHOD"]
        target = environ.get("RAW_URI") or environ.get("PATH_INFO", "/")
        if environ.get("QUERY_STRING") and "?" not in target:
            target = f"{target}?{environ['QUERY_STRING']}"
        length = int(environ.get("CONTENT_LENGTH") or 0)
        body = environ["wsgi.input"].read(length) if length else b""
        headers = {key: value for key, value in environ.items() if key.startswith("HTTP_")}
        if "CONTENT_TYPE" in environ:
            headers["Content-Type"] = environ["CONTENT_TYPE"]
        if "HTTP_COOKIE" in environ:
            headers["Cookie"] = environ["HTTP_COOKIE"]
        request = Request(method=method, target=target, headers=headers, body=body)
        response = self.handle(request)
        start_response(f"{response.status.value} {response.status.phrase}", response.headers)
        body = response.body if isinstance(response.body, bytes) else response.body.encode("utf-8")
        return [body]

    def handle(self, request: Request) -> Response:
        if request.method == "GET" and request.path.startswith("/static/"):
            filename = request.path.split("/", 2)[-1]
            return self._serve_static(filename)
        if request.method == "GET" and request.path.startswith("/uploads/"):
            filename = request.path.split("/", 2)[-1]
            return self._serve_upload(filename)

        route = self._match_route(request)
        if not route:
            return self._not_found()
        handler, params = route
        response = handler(request, **params)
        if not any(name.lower() == "content-type" for name, _ in response.headers):
            response.add_header("Content-Type", "text/html; charset=utf-8")
        if not (300 <= response.status.value < 400) and isinstance(response.body, str):
            messages = self._consume_messages(request)
            if messages:
                response.body = response.body.replace("<!--FLASH-->", self._render_messages(messages))
            else:
                response.body = response.body.replace("<!--FLASH-->", "")
        return response

    def run(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        from wsgiref.simple_server import make_server

        with make_server(host, port, self.wsgi_app) as httpd:
            print(f"Serving on http://{host}:{port}")
            httpd.serve_forever()

    # Routing --------------------------------------------------------------------
    def _match_route(self, request: Request) -> Optional[tuple[Callable, dict[str, Any]]]:
        simple_routes: dict[tuple[str, str], Callable[[Request], Response]] = {
            ("GET", "/"): self._home,
            ("GET", "/login"): self._login_get,
            ("POST", "/login"): self._login_post,
            ("GET", "/logout"): self._logout,
            ("GET", "/register"): self._register_get,
            ("POST", "/register"): self._register_post,
            ("GET", "/password"): self._password_get,
            ("POST", "/password"): self._password_post,
            ("GET", "/account"): self._account_get,
            ("POST", "/account"): self._account_post,
            ("GET", "/inspections"): self._inspection_list,
            ("GET", "/dashboard"): self._dashboard,
        }
        handler = simple_routes.get((request.method, request.path))
        if handler:
            return handler, {}

        if request.path.startswith("/trucks/"):
            parts = request.path.strip("/").split("/")
            if len(parts) == 4 and parts[2] == "inspect":
                return self._truck_inspection, {"truck_id": parts[1], "inspection_type": parts[3]}
        if request.path.startswith("/inspections/"):
            parts = request.path.strip("/").split("/")
            if len(parts) == 2 and request.method == "GET":
                return self._inspection_detail, {"inspection_id": parts[1]}
            if len(parts) == 3 and parts[2] == "notes" and request.method == "POST":
                return self._add_note, {"inspection_id": parts[1]}
        return None

    # Session helpers ------------------------------------------------------------
    def _current_user(self, request: Request) -> Optional[User]:
        token = request.cookie("session_id")
        if not token:
            return None
        user_id = self.sessions.get(token)
        if not user_id:
            return None
        return self.service.database.get_user(user_id)

    def _set_session(self, response: Response, user: User) -> str:
        token = secrets.token_urlsafe(24)
        self.sessions[token] = user.id
        response.set_cookie("session_id", token, path="/")
        return token

    def _clear_session(self, request: Request, response: Response) -> None:
        token = request.cookie("session_id")
        if token:
            self.sessions.pop(token, None)
            response.set_cookie("session_id", "", path="/", max_age=0)

    def _flash(self, request: Request, category: str, message: str, *, token: Optional[str] = None) -> None:
        key = token or request.cookie("session_id") or "__anon__"
        self.flash_messages.setdefault(key, []).append((category, message))

    def _consume_messages(self, request: Request) -> list[tuple[str, str]]:
        key = request.cookie("session_id") or "__anon__"
        return self.flash_messages.pop(key, [])

    # Route handlers -------------------------------------------------------------
    def _home(self, request: Request) -> Response:
        user = self._current_user(request)
        if not user:
            return self._redirect("/login")
        ranger_filter = user if user.role == UserRole.SUPERVISOR else None
        inspections = [
            self._build_inspection_view(insp)
            for insp in self.service.list_inspections(requester=user, ranger=ranger_filter)
        ]
        if user.role == UserRole.SUPERVISOR:
            trucks = self.service.list_trucks()
            active_assignments = {assignment.truck_id: assignment for assignment in self.service.list_active_assignments()}
            content = self._render_supervisor_home(user, trucks, active_assignments, inspections)
        else:
            assignment = self.service.get_active_assignment_for_ranger(user)
            assignment_truck = self.service.get_truck(assignment.truck_id) if assignment else None
            available_trucks = self.service.list_available_trucks()
            content = self._render_ranger_home(user, available_trucks, assignment, assignment_truck, inspections)
        page_title = "Ranger Home" if user.role == UserRole.RANGER else "Home"
        return self._page(page_title, user, content)

    def _login_get(self, request: Request) -> Response:
        return self._page("Sign in", None, self._render_login(), show_icons=False)

    def _login_post(self, request: Request) -> Response:
        email = (request.form_value("email") or "").strip()
        password = request.form_value("password") or ""
        token = self.service.auth.authenticate(email, password)
        if token is None:
            self._flash(request, "error", "Invalid credentials. Please try again.")
            return self._page("Sign in", None, self._render_login(), show_icons=False)
        user = self.service.database.get_user(token.user_id)
        response = self._redirect("/")
        if user:
            session_token = self._set_session(response, user)
            self._flash(request, "success", "Signed in successfully.", token=session_token)
        return response

    def _logout(self, request: Request) -> Response:
        response = self._redirect("/login")
        self._clear_session(request, response)
        self._flash(request, "info", "Signed out.")
        return response

    def _register_get(self, request: Request) -> Response:
        return self._page("Create account", None, self._render_register())

    def _register_post(self, request: Request) -> Response:
        name = (request.form_value("name") or "").strip()
        email = (request.form_value("email") or "").strip()
        ranger_number = (request.form_value("ranger_number") or "").strip()
        password = request.form_value("password") or ""
        confirm = request.form_value("confirm_password") or ""
        if not name or not email or not password:
            self._flash(request, "error", "All fields are required.")
            return self._page("Create account", None, self._render_register(name=name, email=email, ranger_number=ranger_number))
        if not ranger_number:
            self._flash(request, "error", "Ranger number is required.")
            return self._page("Create account", None, self._render_register(name=name, email=email, ranger_number=ranger_number))
        if password != confirm:
            self._flash(request, "error", "Passwords do not match.")
            return self._page("Create account", None, self._render_register(name=name, email=email, ranger_number=ranger_number))
        try:
            role = backend_role_for_email(email)
            self.service.auth.register_user(name=name, email=email, password=password, role=role, ranger_number=ranger_number)
        except ValueError as exc:
            self._flash(request, "error", str(exc))
            return self._page("Create account", None, self._render_register(name=name, email=email, ranger_number=ranger_number))
        except Exception:
            self._flash(request, "error", "Unable to create account. The email may already be registered.")
            return self._page("Create account", None, self._render_register(name=name, email=email, ranger_number=ranger_number))
        self._flash(request, "success", "Account created. You can now sign in.")
        return self._redirect("/login")

    def _password_get(self, request: Request) -> Response:
        return self._page("Update password", None, self._render_password())

    def _password_post(self, request: Request) -> Response:
        email = (request.form_value("email") or "").strip()
        password = request.form_value("password") or ""
        confirm = request.form_value("confirm_password") or ""
        if not email or not password:
            self._flash(request, "error", "Email and new password are required.")
            return self._page("Update password", None, self._render_password(email=email))
        if password != confirm:
            self._flash(request, "error", "Passwords do not match.")
            return self._page("Update password", None, self._render_password(email=email))
        try:
            self.service.auth.update_password(email=email, new_password=password)
        except ValueError as exc:
            self._flash(request, "error", str(exc))
            return self._page("Update password", None, self._render_password(email=email))
        except LookupError as exc:
            self._flash(request, "error", str(exc))
            return self._page("Update password", None, self._render_password(email=email))
        self._flash(request, "success", "Password updated. You can now sign in with the new password.")
        return self._redirect("/login")

    def _account_get(self, request: Request) -> Response:
        user = self._current_user(request)
        if not user:
            return self._redirect("/login")
        return self._page(
            "Account",
            user,
            self._render_account(user, name=user.name, ranger_number=user.ranger_number or ""),
        )

    def _account_post(self, request: Request) -> Response:
        user = self._current_user(request)
        if not user:
            return self._redirect("/login")
        name = (request.form_value("name") or "").strip()
        ranger_number = (request.form_value("ranger_number") or "").strip()
        password = request.form_value("password") or ""
        confirm = request.form_value("confirm_password") or ""
        if not name or not ranger_number:
            self._flash(request, "error", "Name and ranger number are required.")
            return self._page(
                "Account",
                user,
                self._render_account(user, name=name or user.name, ranger_number=ranger_number),
            )
        try:
            updated_user = self.service.auth.update_profile(user.id, name=name, ranger_number=ranger_number)
            if password or confirm:
                if password != confirm:
                    self._flash(request, "error", "Passwords do not match.")
                    return self._page("Account", user, self._render_account(user, name=name, ranger_number=ranger_number))
                self.service.auth.update_password(email=updated_user.email, new_password=password)
        except ValueError as exc:
            self._flash(request, "error", str(exc))
            return self._page("Account", user, self._render_account(user, name=name, ranger_number=ranger_number))
        except LookupError as exc:
            self._flash(request, "error", str(exc))
            return self._page("Account", user, self._render_account(user, name=name, ranger_number=ranger_number))
        self._flash(request, "success", "Account details updated.")
        return self._redirect("/account")

    def _truck_inspection(self, request: Request, *, truck_id: str, inspection_type: str) -> Response:
        user = self._current_user(request)
        if not user:
            return self._redirect("/login")
        try:
            truck = self.service.get_truck(int(truck_id))
        except (ValueError, LookupError):
            return self._not_found()
        try:
            inspection_enum = InspectionType(inspection_type)
        except ValueError:
            return self._not_found()
        preserved = self._preserve_form_state(request)
        action = request.query.get("action", [None])[0]
        if request.method == "POST":
            action = request.form_value("action") or action
        action = action or "checkout"
        if action not in {"checkout", "return"}:
            action = "checkout"

        assignment_obj: Optional[TruckAssignment] = None
        assignment_param = request.query.get("assignment", [None])[0]
        if request.method == "POST":
            assignment_param = request.form_value("assignment_id") or assignment_param
        assignment_id: Optional[int]
        if assignment_param:
            try:
                assignment_id = int(assignment_param)
            except ValueError:
                assignment_id = None
            else:
                assignment_obj = self.service.database.get_assignment(assignment_id)
                if not assignment_obj:
                    assignment_id = None
                    assignment_obj = None
        else:
            assignment_id = None
            assignment_obj = None

        if action == "return" and not assignment_obj:
            assignment_obj = self.service.get_active_assignment_for_ranger(user)
            if assignment_obj and assignment_obj.truck_id != truck.id:
                assignment_obj = None
            if assignment_obj:
                assignment_id = assignment_obj.id

        if action == "return":
            inspection_enum = InspectionType.RETURN

        fields = get_form_definition(inspection_enum)

        active_assignment_for_truck = self.service.get_active_assignment_for_truck(truck)
        ranger_assignment = self.service.get_active_assignment_for_ranger(user) if user.role == UserRole.RANGER else None
        if action == "checkout" and ranger_assignment and ranger_assignment.truck_id != truck.id:
            self._flash(request, "error", "You already have a vehicle checked out. Please return it before checking out another truck.")
            return self._redirect("/")

        if action == "checkout" and active_assignment_for_truck:
            if active_assignment_for_truck.ranger_id == user.id:
                self._flash(request, "info", "You already have this truck checked out. Please return it before starting another inspection.")
            else:
                self._flash(request, "error", "This truck is currently checked out by another ranger.")
            return self._redirect("/")
        if action == "return":
            if not assignment_obj:
                self._flash(request, "error", "No active checkout found for this truck.")
                return self._redirect("/")
            if assignment_obj.ranger_id != user.id and user.role != UserRole.SUPERVISOR:
                self._flash(request, "error", "You cannot return a truck you did not check out.")
                return self._redirect("/")

        if request.method == "POST":
            try:
                responses = self._collect_responses(request, inspection_enum)
                if inspection_enum is InspectionType.RETURN:
                    photos = []
                else:
                    photos = self._collect_photos(request)
                escalate = request.form_value("escalate_visibility") == "1"
                miles_value = responses.get("odometer_miles")
                if not isinstance(miles_value, int):
                    raise ValueError("Mileage must be provided as a number.")
                if action == "return" and assignment_obj and miles_value < assignment_obj.start_miles:
                    raise ValueError("Ending mileage must be greater than or equal to the starting mileage.")
                inspection = self.service.submit_inspection(
                    user=user,
                    truck=truck,
                    inspection_type=inspection_enum,
                    responses=responses,
                    photo_urls=photos,
                    escalate_visibility=escalate,
                )
                if action == "checkout":
                    self.service.checkout_truck(ranger=user, truck=truck, inspection=inspection)
                    self._flash(request, "success", "Truck checked out successfully.")
                else:
                    assert assignment_id is not None
                    self.service.return_truck(assignment_id=assignment_id, ranger=user, inspection=inspection)
                    self._flash(request, "success", "Truck returned successfully.")
                return self._redirect(f"/inspections/{inspection.id}")
            except ValueError as exc:
                self._flash(request, "error", str(exc))
                preserved = self._preserve_form_state(request)
        content = self._render_inspection_form(
            truck,
            inspection_enum,
            fields,
            action,
            assignment_id,
            preserved,
        )
        return self._page(f"{inspection_enum.value.title()} inspection", user, content)

    def _inspection_list(self, request: Request) -> Response:
        user = self._current_user(request)
        if not user:
            return self._redirect("/login")
        inspections = [self._build_inspection_view(insp) for insp in self.service.list_inspections(requester=user)]
        content = self._render_inspection_table("Inspections", inspections)
        return self._page("Inspections", user, content)

    def _inspection_detail(self, request: Request, *, inspection_id: str) -> Response:
        user = self._current_user(request)
        if not user:
            return self._redirect("/login")
        try:
            inspection = self.service.get_inspection(requester=user, inspection_id=int(inspection_id))
        except (ValueError, LookupError, PermissionError):
            return self._not_found()
        view = self._build_inspection_view(inspection, include_notes=True)
        content = self._render_inspection_detail(user, view)
        return self._page(f"Inspection {inspection.id}", user, content)

    def _add_note(self, request: Request, *, inspection_id: str) -> Response:
        user = self._current_user(request)
        if not user:
            return self._redirect("/login")
        try:
            inspection = self.service.get_inspection(requester=user, inspection_id=int(inspection_id))
        except (ValueError, LookupError, PermissionError):
            return self._not_found()
        content = (request.form_value("content") or "").strip()
        if not content:
            self._flash(request, "error", "Note content cannot be empty.")
            return self._redirect(f"/inspections/{inspection.id}")
        try:
            self.service.add_note(requester=user, inspection=inspection, content=content)
            self._flash(request, "success", "Note added.")
        except ValueError as exc:
            self._flash(request, "error", str(exc))
        return self._redirect(f"/inspections/{inspection.id}")

    def _dashboard(self, request: Request) -> Response:
        user = self._current_user(request)
        if not user:
            return self._redirect("/login")
        if user.role != UserRole.SUPERVISOR:
            return self._not_found()
        metrics = self.service.dashboard(supervisor=user)
        inspections = [self._build_inspection_view(insp) for insp in self.service.list_inspections(requester=user)]
        content = self._render_dashboard(metrics, inspections)
        return self._page("Supervisor dashboard", user, content)

    # Utility responses ----------------------------------------------------------
    def _page(
        self,
        title: str,
        user: Optional[User],
        content: str,
        *,
        body_class: Optional[str] = None,
        show_icons: bool = True,
    ) -> Response:
        nav = self._nav_links(user)
        icons = self._top_nav_icons() if show_icons else ""
        body_attr = f' class="{body_class}"' if body_class else ""
        body = f"""
        <!doctype html>
        <html lang=\"en\">
          <head>
            <meta charset=\"utf-8\" />
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
            <title>{html.escape(title)} - Truck Inspection App</title>
            <link rel=\"stylesheet\" href=\"/static/styles.css\" />
            <script src=\"/static/app.js\" defer></script>
          </head>
          <body{body_attr}>
            <header class=\"top-bar\">
              <div class=\"brand\">Truck Inspection App</div>
              <div class=\"top-bar-icons\">{icons}</div>
              <nav class=\"nav-links\">{nav}</nav>
            </header>
            <main class=\"content\">
              <!--FLASH-->
              {content}
            </main>
            <footer class=\"footer\"><small>&copy; 2024 Park Ranger Tools</small></footer>
          </body>
        </html>
        """
        return Response(body=body)

    def _top_nav_icons(self) -> str:
        available = sorted(self.service.list_available_trucks(), key=lambda truck: truck.identifier.upper())
        if not available:
            return ""
        icon_fragments: list[str] = []
        tracked_categories = {"full_size", "mid_size"}
        for truck in available:
            profile = self._truck_profile(truck)
            if profile["category"] not in tracked_categories:
                continue
            label = html.escape(truck.identifier.upper())
            icon_fragments.append(
                f'<span class="top-bar-icon" title="Truck {label} available">{profile["icon"]}</span>'
            )
        return "".join(icon_fragments)

    def _redirect(self, location: str) -> Response:
        response = Response(status=HTTPStatus.SEE_OTHER)
        response.add_header("Location", location)
        response.body = f"<html><body>Redirecting to <a href=\"{html.escape(location)}\">{html.escape(location)}</a></body></html>"
        return response

    def _not_found(self) -> Response:
        body = "<html><body><h1>404 Not Found</h1></body></html>"
        return Response(status=HTTPStatus.NOT_FOUND, headers=[("Content-Type", "text/html; charset=utf-8")], body=body)

    def _serve_static(self, filename: str) -> Response:
        static_root = self.static_dir.resolve()
        path = (self.static_dir / filename).resolve()
        try:
            path.relative_to(static_root)
        except ValueError:
            return self._not_found()
        if not path.exists() or not path.is_file():
            return self._not_found()
        content_type, encoding = mimetypes.guess_type(str(path))
        content_type = content_type or "application/octet-stream"
        if content_type.startswith("text/"):
            body = path.read_text(encoding="utf-8")
            return Response(headers=[("Content-Type", f"{content_type}; charset=utf-8")], body=body)
        data = path.read_bytes()
        response = Response(headers=[("Content-Type", content_type)], body=data)
        if encoding:
            response.add_header("Content-Encoding", encoding)
        return response

    def _serve_upload(self, filename: str) -> Response:
        safe_name = Path(filename).name
        path = self.upload_dir / safe_name
        if not path.exists() or not path.is_file():
            return self._not_found()
        content_type, _ = mimetypes.guess_type(str(path))
        content_type = content_type or "application/octet-stream"
        return Response(headers=[("Content-Type", content_type)], body=path.read_bytes())

    # Rendering helpers ----------------------------------------------------------
    def _nav_links(self, user: Optional[User]) -> str:
        links: list[str] = []
        if user:
            links.append('<a href="/">Home</a>')
            links.append('<a href="/inspections">Inspections</a>')
            if user.role == UserRole.SUPERVISOR:
                links.append('<a href="/dashboard">Dashboard</a>')
            links.append('<a href="/account">Account</a>')
            links.append('<a href="/logout">Sign out</a>')
        else:
            links.append('<a href="/login">Sign in</a>')
            links.append('<a href="/register">Register</a>')
            links.append('<a href="/password">Update password</a>')
        return "".join(links)

    def _render_messages(self, messages: Iterable[tuple[str, str]]) -> str:
        items = [f'<li class="flash {html.escape(cat)}">{html.escape(msg)}</li>' for cat, msg in messages]
        if not items:
            return ""
        return '<ul class="flash-messages">' + "".join(items) + "</ul>"

    def _render_login(self) -> str:
        return """
        <section class=\"card narrow\">
          <h1>Sign in</h1>
          <form method=\"post\" class=\"form\">
            <label for=\"email\">Email</label>
            <input type=\"email\" id=\"email\" name=\"email\" required autofocus />
            <label for=\"password\">Password</label>
            <input type=\"password\" id=\"password\" name=\"password\" required />
            <button type=\"submit\">Sign in</button>
          </form>
          <p class=\"hint\">Need access? <a href=\"/register\">Create an approved account</a> or <a href=\"/password\">update your password</a>.</p>
        </section>
        """

    def _render_register(self, *, name: str = "", email: str = "", ranger_number: str = "") -> str:
        return f"""
        <section class=\"card narrow\">
          <h1>Create account</h1>
          <form method=\"post\" class=\"form\">
            <label for=\"name\">Full name</label>
            <input type=\"text\" id=\"name\" name=\"name\" value=\"{html.escape(name)}\" required autofocus />
            <label for=\"reg-email\">Email</label>
            <input type=\"email\" id=\"reg-email\" name=\"email\" value=\"{html.escape(email)}\" required />
            <label for=\"reg-number\">Ranger number</label>
            <input type=\"text\" id=\"reg-number\" name=\"ranger_number\" value=\"{html.escape(ranger_number)}\" required />
            <label for=\"reg-password\">Password</label>
            <input type=\"password\" id=\"reg-password\" name=\"password\" required />
            <label for=\"reg-confirm\">Confirm password</label>
            <input type=\"password\" id=\"reg-confirm\" name=\"confirm_password\" required />
            <button type=\"submit\">Create account</button>
          </form>
          <p class=\"hint\">Only approved park ranger email addresses may register.</p>
        </section>
        """

    def _render_password(self, *, email: str = "") -> str:
        return f"""
        <section class=\"card narrow\">
          <h1>Update password</h1>
          <form method=\"post\" class=\"form\">
            <label for=\"pw-email\">Email</label>
            <input type=\"email\" id=\"pw-email\" name=\"email\" value=\"{html.escape(email)}\" required autofocus />
            <label for=\"pw-new\">New password</label>
            <input type=\"password\" id=\"pw-new\" name=\"password\" required />
            <label for=\"pw-confirm\">Confirm password</label>
            <input type=\"password\" id=\"pw-confirm\" name=\"confirm_password\" required />
            <button type=\"submit\">Update password</button>
          </form>
          <p class=\"hint\">Use an approved email address already added to the system.</p>
        </section>
        """

    def _render_account(self, user: User, *, name: str, ranger_number: str) -> str:
        number_value = html.escape(ranger_number)
        return f"""
        <section class=\"card narrow\">
          <h1>Account information</h1>
          <form method=\"post\" class=\"form\">
            <label for=\"acct-name\">Full name</label>
            <input type=\"text\" id=\"acct-name\" name=\"name\" value=\"{html.escape(name)}\" required autofocus />
            <label>Email</label>
            <input type=\"email\" value=\"{html.escape(user.email)}\" disabled />
            <label for=\"acct-number\">Ranger number</label>
            <input type=\"text\" id=\"acct-number\" name=\"ranger_number\" value=\"{number_value}\" required />
            <hr />
            <p class=\"muted\">Update your password (optional)</p>
            <label for=\"acct-password\">New password</label>
            <input type=\"password\" id=\"acct-password\" name=\"password\" />
            <label for=\"acct-confirm\">Confirm password</label>
            <input type=\"password\" id=\"acct-confirm\" name=\"confirm_password\" />
            <button type=\"submit\" class=\"primary-action\">Save changes</button>
          </form>
        </section>
        """

    def _render_ranger_home(
        self,
        user: User,
        available_trucks: list[Truck],
        assignment: Optional[TruckAssignment],
        assignment_truck: Optional[Truck],
        inspections: list[dict[str, Any]],
    ) -> str:
        available_cards = "".join(self._render_available_truck_card(truck) for truck in available_trucks)
        if not available_cards:
            available_cards = "<p class=\"muted\">No trucks available right now.</p>"

        assignment_html = ""
        if assignment and assignment_truck:
            assignment_html = self._render_assignment_card(assignment_truck, assignment)

        inspections_html = self._render_inspection_table("Your recent inspections", inspections)
        return f"""
        <section class=\"card\">
          <h1>Welcome, {html.escape(user.name)}!</h1>
          <p>Select an available truck to check out or return your current vehicle.</p>
          {assignment_html}
          <div class=\"grid\">{available_cards}</div>
        </section>
        {inspections_html}
        """

    def _render_supervisor_home(
        self,
        user: User,
        trucks: list[Truck],
        active_assignments: dict[int, TruckAssignment],
        inspections: list[dict[str, Any]],
    ) -> str:
        cards = "".join(self._render_supervisor_truck_card(truck, active_assignments.get(truck.id)) for truck in trucks)
        if not cards:
            cards = "<p class=\"muted\">No trucks configured.</p>"
        inspections_html = self._render_inspection_table("All inspections", inspections)
        return f"""
        <section class=\"card\">
          <h1>Fleet overview</h1>
          <div class=\"grid\">{cards}</div>
        </section>
        {inspections_html}
        """

    def _render_available_truck_card(self, truck: Truck) -> str:
        profile = self._truck_profile(truck)
        graphic_class = f"truck-card__graphic truck-card__graphic--{profile['badge_class']}"
        icon_html = profile["icon"]
        quick_url = f"/trucks/{truck.id}/inspect/{InspectionType.QUICK.value}?action=checkout"
        detailed_url = f"/trucks/{truck.id}/inspect/{InspectionType.DETAILED.value}?action=checkout"
        return f"""
        <article class=\"card truck-card\">
          <div class=\"{graphic_class}\">{icon_html}</div>
          <h2>{html.escape(truck.identifier)}</h2>
          <div class=\"actions\">
            <a class=\"button\" href=\"{quick_url}\">Check out (Quick)</a>
            <a class=\"button secondary\" href=\"{detailed_url}\">Check out (Detailed)</a>
          </div>
        </article>
        """

    def _render_assignment_card(self, truck: Truck, assignment: TruckAssignment) -> str:
        profile = self._truck_profile(truck)
        graphic_class = f"truck-card__graphic truck-card__graphic--{profile['badge_class']}"
        icon_html = profile["icon"]
        checked_out_at = assignment.checked_out_at.strftime("%Y-%m-%d %H:%M")
        return_url = f"/trucks/{truck.id}/inspect/{InspectionType.RETURN.value}?action=return&assignment={assignment.id}"
        return f"""
        <article class=\"card truck-card truck-card--assignment\">
          <div class=\"{graphic_class}\">{icon_html}</div>
          <h2>{html.escape(truck.identifier)} (Checked out)</h2>
          <p class=\"muted\">Started {checked_out_at} · Start miles: {assignment.start_miles}</p>
          <div class=\"actions\">
            <a class=\"button\" href=\"{return_url}\">Return vehicle</a>
          </div>
        </article>
        """

    def _render_supervisor_truck_card(self, truck: Truck, assignment: Optional[TruckAssignment]) -> str:
        profile = self._truck_profile(truck)
        graphic_class = f"truck-card__graphic truck-card__graphic--{profile['badge_class']}"
        icon_html = profile["icon"]
        actions = []
        status = "Available"
        if assignment:
            status = f"Checked out by ranger #{assignment.ranger_id} since {assignment.checked_out_at.strftime('%Y-%m-%d %H:%M')}"
            return_url = f"/trucks/{truck.id}/inspect/{InspectionType.RETURN.value}?action=return&assignment={assignment.id}"
            actions.append(f'<a class="button" href="{return_url}">Return vehicle</a>')
        else:
            quick_url = f"/trucks/{truck.id}/inspect/{InspectionType.QUICK.value}?action=checkout"
            detailed_url = f"/trucks/{truck.id}/inspect/{InspectionType.DETAILED.value}?action=checkout"
            actions.append(f'<a class="button" href="{quick_url}">Quick inspection</a>')
            actions.append(f'<a class="button secondary" href="{detailed_url}">Detailed inspection</a>')

        actions_html = ''.join(actions) if actions else ''
        return f"""
        <article class=\"card truck-card\">
          <div class=\"{graphic_class}\">{icon_html}</div>
          <h2>{html.escape(truck.identifier)}</h2>
          <p class=\"muted\">{html.escape(status)}</p>
          <div class=\"actions\">{actions_html}</div>
        </article>
        """

    def _render_truck_legend(self, trucks: list[Truck]) -> str:
        return ""

    def _render_inspection_table(self, heading: str, inspections: list[dict[str, Any]]) -> str:
        if not inspections:
            return f"<section class=\"card\"><h2>{html.escape(heading)}</h2><p class=\"muted\">No inspections recorded yet.</p></section>"
        rows = []
        for item in inspections:
            inspection = item["inspection"]
            truck = item["truck"]
            ranger = item["ranger"]
            escalated = (
                "<span class=\"badge badge-alert\">Escalated</span>"
                if inspection.escalate_visibility
                else "<span class=\"badge\">Normal</span>"
            )
            rows.append(
                """
                <tr>
                  <td>{id}</td>
                  <td class=\"muted\">{type}</td>
                  <td>{truck}</td>
                  <td>{ranger}</td>
                  <td>{created}</td>
                  <td>{escalated}</td>
                  <td><a href=\"/inspections/{id}\">View</a></td>
                </tr>
                """.format(
                    id=inspection.id,
                    type=html.escape(inspection.inspection_type.value.title()),
                    truck=html.escape(truck.identifier),
                    ranger=html.escape(ranger.name),
                    created=inspection.created_at.strftime("%Y-%m-%d %H:%M"),
                    escalated=escalated,
                )
            )
        return f"""
        <section class=\"card\">
          <h2>{html.escape(heading)}</h2>
          <table class=\"inspection-table\">
            <thead><tr><th>ID</th><th>Type</th><th>Truck</th><th>Ranger</th><th>Created</th><th>Escalated</th><th></th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </section>
        """

    def _render_inspection_form(
        self,
        truck: Truck,
        inspection_type: InspectionType,
        fields: Iterable[Any],
        action: str,
        assignment_id: Optional[int],
        preserved: dict[str, Any] | None = None,
    ) -> str:
        preserved = preserved or {}
        field_html: list[str] = []
        for field in fields:
            label = html.escape(field.label)
            if field.field_type is FieldType.BOOLEAN:
                yes_checked = "checked" if preserved.get(field.id) == "yes" else ""
                no_checked = "checked" if preserved.get(field.id) == "no" else ""
                field_html.append(
                    f"""
                    <div class=\"form-field\">
                      <label>{label}</label>
                      <div class=\"radio-group\" role=\"radiogroup\" aria-label=\"{label}\">
                        <label class=\"radio-option\">
                          <input type=\"radio\" name=\"{field.id}\" value=\"yes\" {yes_checked} required />
                          <span>Yes</span>
                        </label>
                        <label class=\"radio-option\">
                          <input type=\"radio\" name=\"{field.id}\" value=\"no\" {no_checked} required />
                          <span>No</span>
                        </label>
                      </div>
                    </div>
                    """
                )
            elif field.field_type is FieldType.TEXT:
                if field.id == "fuel_level":
                    fuel_value = preserved.get(field.id)
                    if fuel_value is None:
                        fuel_value = "50"
                    slider_value = html.escape(str(fuel_value))
                    ticks: list[str] = []
                    for tick_index in range(9):
                        value = tick_index * 12.5
                        angle = -90 + (value / 100) * 180
                        tick_class = "gauge-tick gauge-tick--major" if tick_index % 2 == 0 else "gauge-tick gauge-tick--minor"
                        ticks.append(
                            f'<span class="{tick_class}" style="--tick-rotation:{angle:.6f}deg"></span>'
                        )
                    field_html.append(
                        f"""
                        <div class=\"form-field fuel-field\">
                          <label>{label}</label>
                          <div class=\"fuel-gauge\" data-fuel-gauge>
                            <div class=\"gauge-dial\" data-fuel-dial role=\"slider\" tabindex=\"0\" aria-label=\"{label}\" aria-valuemin=\"0\" aria-valuemax=\"100\" aria-valuenow=\"{slider_value}\">
                              <div class=\"gauge-ticks\">{''.join(ticks)}</div>
                              <div class=\"gauge-needle\" data-fuel-needle></div>
                              <div class=\"gauge-center\"></div>
                              <div class=\"gauge-labels\"><span>E</span><span>1/2</span><span>F</span></div>
                            </div>
                          </div>
                          <div class=\"fuel-reading\"><span data-fuel-value>{slider_value}%</span></div>
                          <input type=\"hidden\" id=\"{field.id}\" name=\"{field.id}\" value=\"{slider_value}\" required />
                        </div>
                        """
                    )
                else:
                    required = " required" if field.required else ""
                    value = html.escape(str(preserved.get(field.id, "")))
                    field_html.append(
                        f"""
                        <div class=\"form-field\">
                          <label for=\"{field.id}\">{label}</label>
                          <textarea id=\"{field.id}\" name=\"{field.id}\"{required}>{value}</textarea>
                        </div>
                        """
                    )
            elif field.field_type is FieldType.NUMBER:
                required = " required" if field.required else ""
                value = html.escape(str(preserved.get(field.id, ""))) if field.id in preserved else ""
                value_attr = f" value=\"{value}\"" if value else ""
                field_html.append(
                    f"""
                    <div class=\"form-field\">
                      <label for=\"{field.id}\">{label}</label>
                      <input type=\"number\" id=\"{field.id}\" name=\"{field.id}\"{value_attr}{required} />
                    </div>
                    """
                )
        escalate_checked = "active" if preserved.get("escalate_visibility") == "1" else ""
        escalate_pressed = "true" if preserved.get("escalate_visibility") == "1" else "false"
        escalate_value = preserved.get("escalate_visibility", "0")
        action_value = html.escape(str(preserved.get("action", action)))
        assignment_value = preserved.get("assignment_id") or (str(assignment_id) if assignment_id is not None else None)
        assignment_input = (
            f'<input type="hidden" name="assignment_id" value="{html.escape(str(assignment_value))}" />'
            if assignment_value
            else ""
        )
        title_prefix = "Check out" if action_value == "checkout" else "Return"
        photos_section = ""
        escalate_section = ""
        if action_value != "return":
            photos_section = (
                """
            <div class=\"form-field\">
              <label for=\"photos\">Vehicle photos <span class=\"muted\">(Capture or upload 4-10 images)</span></label>
              <input type=\"file\" id=\"photos\" name=\"photos\" accept=\"image/*\" capture=\"environment\" multiple required />
            </div>
                """
            )
        else:
            photos_section = ""

        escalate_section = (
            f"""
        <div class=\"form-field escalate-field\">
          <input type=\"hidden\" name=\"escalate_visibility\" id=\"escalate_visibility\" value=\"{escalate_value}\" />
          <button type=\"button\" class=\"escalate-button {escalate_checked}\" data-escalate-toggle data-target=\"escalate_visibility\" aria-pressed=\"{escalate_pressed}\">
            Escalate to supervisors
          </button>
          <p class=\"muted small\">Use when immediate supervisor attention is required.</p>
        </div>
            """
        )
        return f"""
        <section class=\"card\">
          <h1>{title_prefix} {inspection_type.value.title()} inspection for {html.escape(truck.identifier)}</h1>
          <form method=\"post\" class=\"form\" enctype=\"multipart/form-data\">
            {''.join(field_html)}
            <input type=\"hidden\" name=\"__preserve__\" value=\"1\" />
            <input type=\"hidden\" name=\"action\" value=\"{action_value}\" />
            {assignment_input}
            {photos_section}
            {escalate_section}
            <button type=\"submit\" class=\"primary-action\">Submit inspection</button>
          </form>
        </section>
        """

    def _preserve_form_state(self, request: Request) -> dict[str, str]:
        if request.method != "POST":
            return {}
        preserved: dict[str, str] = {}
        for key, values in request.form.items():
            if not values or key == "__preserve__":
                continue
            preserved[key] = values[0]
        escalate = request.form_value("escalate_visibility")
        if escalate is not None:
            preserved["escalate_visibility"] = escalate
        return preserved

    def _render_inspection_detail(self, user: User, view: dict[str, Any]) -> str:
        inspection: Inspection = view["inspection"]
        truck: Truck = view["truck"]
        ranger: User = view["ranger"]
        fields = view["fields"]
        notes = view["notes"]
        response_items = []
        for field in fields:
            if field.id in inspection.responses:
                value = inspection.responses[field.id]
                if field.field_type is FieldType.BOOLEAN:
                    display = "Yes" if value else "No"
                elif field.id == "fuel_level":
                    display = f"{html.escape(str(value))}%"
                else:
                    display = html.escape(str(value))
                response_items.append(f"<li><strong>{html.escape(field.label)}:</strong> {display}</li>")
        note_items = []
        for entry in notes:
            note = entry["note"]
            author = entry["author"]
            note_items.append(
                f"""
                <li>
                  <div class=\"note-header\"><strong>{html.escape(author.name)}</strong><span class=\"muted\">{note.created_at.strftime('%Y-%m-%d %H:%M')}</span></div>
                  <p>{html.escape(note.content)}</p>
                </li>
                """
            )
        can_download = user.role == UserRole.SUPERVISOR or inspection.ranger_id == user.id
        photos = "".join(
            f"""
            <li>
              <button type=\"button\" class=\"photo-thumb\" data-photo-src=\"{html.escape(url)}\" aria-label=\"View vehicle photo {index + 1}\">
                <img src=\"{html.escape(url)}\" alt=\"Vehicle photo {index + 1}\" loading=\"lazy\" />
              </button>
              {(
                f'<div class="photo-thumb__actions"><a href="{html.escape(url)}" download class="photo-thumb__download">Download</a></div>'
                if can_download
                else ''
              )}
            </li>
            """
            for index, url in enumerate(inspection.photo_urls)
        )
        note_form = f"""
        <form method=\"post\" action=\"/inspections/{inspection.id}/notes\" class=\"form\">
          <label for=\"note-content\">Add a note</label>
          <textarea id=\"note-content\" name=\"content\" required></textarea>
          <button type=\"submit\">Add note</button>
        </form>
        """
        if user.role == UserRole.RANGER and inspection.ranger_id != user.id:
            note_form = ""
        notes_html = '<ul class="notes">' + ''.join(note_items) + '</ul>' if note_items else '<p class="muted">No notes yet.</p>'
        viewer_download = (
            """
            <a href=\"\" download class=\"photo-viewer__download\" data-photo-download hidden>Download</a>
            """
            if can_download
            else ""
        )

        photo_viewer = """
        <div class=\"photo-viewer\" data-photo-viewer hidden aria-hidden=\"true\" role=\"dialog\" aria-modal=\"true\" aria-label=\"Inspection photo viewer\" tabindex=\"-1\">
          <div class=\"photo-viewer__backdrop\" data-photo-close></div>
          <figure class=\"photo-viewer__figure\">
            <button type=\"button\" class=\"photo-viewer__close\" data-photo-close aria-label=\"Close photo\">&times;</button>
            <img src=\"\" alt=\"Inspection photo\" data-photo-image />
            {viewer_download}
          </figure>
        </div>
        """

        return f"""
        <section class=\"card\">
          <h1>Inspection {inspection.id}</h1>
          <dl class=\"meta\">
            <div><dt>Type</dt><dd>{html.escape(inspection.inspection_type.value.title())}</dd></div>
            <div><dt>Truck</dt><dd>{html.escape(truck.identifier)}</dd></div>
            <div><dt>Ranger</dt><dd>{html.escape(ranger.name)}</dd></div>
            <div><dt>Created</dt><dd>{inspection.created_at.strftime('%Y-%m-%d %H:%M')}</dd></div>
            <div><dt>Escalated</dt><dd>{'Yes' if inspection.escalate_visibility else 'No'}</dd></div>
          </dl>
          <h2>Checklist responses</h2>
          <ul class=\"responses\">{''.join(response_items)}</ul>
          <h2>Photos</h2>
          <ul class=\"photo-list\">{photos}</ul>
        </section>
        {photo_viewer}
        <section class=\"card\">
          <h2>Notes</h2>
          {notes_html}
          {note_form}
        </section>
        """

    def _render_dashboard(self, metrics: dict[str, Any], inspections: list[dict[str, Any]]) -> str:
        personnel_rows = []
        for entry in metrics["personnel_metrics"]:
            user = entry["user"]
            role_label = "Ranger" if user.role == UserRole.RANGER else "Supervisor"
            recent = entry["most_recent_inspection"]
            recent_text = recent.strftime("%Y-%m-%d %H:%M") if recent else "<span class=\"muted\">No inspections</span>"
            personnel_rows.append(
                f"<tr><td>{html.escape(user.name)}</td><td>{role_label}</td><td>{entry['inspections_completed']}</td><td>{recent_text}</td></tr>"
            )
        personnel_table = """
        <table class=\"inspection-table\">
          <thead><tr><th>Name</th><th>Role</th><th>Completed</th><th>Most recent</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """.format(rows="".join(personnel_rows))
        inspection_table = self._render_inspection_table("All inspections", inspections)
        return f"""
        <section class=\"card\">
          <h1>Supervisor dashboard</h1>
          <div class=\"metrics\">
            <div class=\"metric\"><span class=\"label\">Total inspections</span><span class=\"value\">{metrics['total_inspections']}</span></div>
            <div class=\"metric\"><span class=\"label\">Escalated</span><span class=\"value\">{metrics['escalated_inspections']}</span></div>
          </div>
          <h2>Team compliance</h2>
          {personnel_table}
        </section>
        {inspection_table}
        """

    # Data helpers ---------------------------------------------------------------
    def _collect_responses(self, request: Request, inspection_type: InspectionType) -> dict[str, Any]:
        responses: dict[str, Any] = {}
        for field in get_form_definition(inspection_type):
            raw = request.form_value(field.id)
            if raw is None:
                if field.required:
                    raise ValueError(f"Please provide '{field.label}'.")
                continue
            if field.field_type is FieldType.BOOLEAN:
                if raw not in {"yes", "no"}:
                    raise ValueError(f"Invalid selection for '{field.label}'.")
                responses[field.id] = raw == "yes"
            elif field.field_type is FieldType.TEXT:
                cleaned = raw.strip()
                if field.id == "fuel_level":
                    if not cleaned or not cleaned.isdigit():
                        raise ValueError("Please set the fuel gauge before submitting.")
                    value = int(cleaned)
                    if value < 0 or value > 100:
                        raise ValueError("Fuel level must be between 0 and 100.")
                    responses[field.id] = str(value)
                else:
                    if field.required and not cleaned:
                        raise ValueError(f"Please provide '{field.label}'.")
                    responses[field.id] = cleaned
            elif field.field_type is FieldType.NUMBER:
                cleaned = raw.strip()
                if not cleaned.isdigit():
                    raise ValueError(f"'{field.label}' must be a number.")
                responses[field.id] = int(cleaned)
        return responses

    def _truck_profile(self, truck: Truck) -> dict[str, str]:
        identifier = truck.identifier.upper()
        category = TRUCK_CATEGORY_MAP.get(identifier)
        if category is None:
            if identifier.startswith("S"):
                category = "full_size"
            elif identifier.startswith("P") or identifier.isdigit():
                category = "mid_size"
            elif identifier.startswith("T"):
                category = "maintenance"
            else:
                category = "default"
        info = TRUCK_CATEGORY_INFO.get(category, TRUCK_CATEGORY_INFO["default"])
        return {
            "category": category,
            "label": info["label"],
            "badge_class": info["badge_class"],
            "icon": info["icon"].strip(),
        }

    def _collect_photos(self, request: Request) -> list[str]:
        uploads = request.file_values("photos")
        if len(uploads) < 4 or len(uploads) > 10:
            raise ValueError("Please provide between 4 and 10 photos.")
        return self._store_uploaded_photos(uploads)

    def _store_uploaded_photos(self, uploads: Iterable[UploadedFile]) -> list[str]:
        saved: list[str] = []
        for upload in uploads:
            if not upload.content_type.startswith("image/"):
                raise ValueError("All uploads must be image files.")
            suffix = Path(upload.filename).suffix or ".jpg"
            filename = f"{uuid.uuid4().hex}{suffix}"
            path = self.upload_dir / filename
            path.write_bytes(upload.data)
            saved.append(f"/uploads/{filename}")
        return saved

    def _build_inspection_view(self, inspection: Inspection, include_notes: bool = False) -> dict[str, Any]:
        truck = self.service.get_truck(inspection.truck_id)
        ranger = self.service.database.get_user(inspection.ranger_id)
        result = {"inspection": inspection, "truck": truck, "ranger": ranger, "fields": get_form_definition(inspection.inspection_type)}
        if include_notes:
            notes = []
            for note in self.service.list_notes(inspection.id):
                author = self.service.database.get_user(note.author_id)
                if author:
                    notes.append({"note": note, "author": author})
            result["notes"] = notes
        else:
            result["notes"] = []
        return result


def create_app(database_path: Optional[Path | str] = None) -> TruckInspectionWebApp:
    path = Path(database_path) if database_path else Path("truck_inspections.db")
    return TruckInspectionWebApp(path)


app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    app.run()
