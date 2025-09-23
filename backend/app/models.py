from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class UserRole(str, Enum):
    RANGER = "ranger"
    SUPERVISOR = "supervisor"


@dataclass
class User:
    id: int
    name: str
    email: str
    password_hash: str
    role: UserRole
    created_at: datetime


@dataclass
class Truck:
    id: int
    identifier: str
    description: Optional[str]
    active: bool


class InspectionType(str, Enum):
    QUICK = "quick"
    DETAILED = "detailed"

@dataclass
class Inspection:
    id: int
    inspection_type: InspectionType
    truck_id: int
    ranger_id: int
    escalate_visibility: bool
    responses: Dict[str, Any]
    photo_urls: List[str]
    video_url: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class InspectionNote:
    id: int
    inspection_id: int
    author_id: int
    content: str
    created_at: datetime


@dataclass
class SessionToken:
    id: int
    user_id: int
    token: str
    created_at: datetime
    expires_at: datetime
