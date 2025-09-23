from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

from .models import InspectionType


class FieldType(str, Enum):
    BOOLEAN = "boolean"
    TEXT = "text"
    NUMBER = "number"


@dataclass(frozen=True)
class InspectionField:
    id: str
    label: str
    field_type: FieldType = FieldType.BOOLEAN
    required: bool = True


FORM_DEFINITIONS: dict[InspectionType, tuple[InspectionField, ...]] = {
    InspectionType.QUICK: (
        InspectionField("exterior_clean", "Exterior clean"),
        InspectionField("interior_clean", "Interior clean"),
        InspectionField("seatbelts_functioning", "Seatbelts functioning properly"),
        InspectionField("tire_inflation", "Tire inflation"),
        InspectionField("fuel_level", "Fuel level", FieldType.TEXT),
        InspectionField("odometer_miles", "Miles", FieldType.NUMBER),
        InspectionField("notes", "Notes section", FieldType.TEXT, required=False),
        InspectionField("inventory_items", "Inventory items", FieldType.TEXT, required=False),
    ),
    InspectionType.DETAILED: (
        InspectionField("exterior_clean", "Exterior clean"),
        InspectionField("interior_clean", "Interior clean"),
        InspectionField("seatbelts_functioning", "Seatbelts functioning properly"),
        InspectionField("tire_inflation", "Tire inflation"),
        InspectionField("fuel_level", "Fuel level", FieldType.TEXT),
        InspectionField("odometer_miles", "Miles", FieldType.NUMBER),
        InspectionField("notes", "Notes section", FieldType.TEXT, required=False),
        InspectionField("inventory_items", "Inventory items", FieldType.TEXT, required=False),
        InspectionField("engine_oil_ok", "Engine oil within acceptable limits"),
        InspectionField("fan_belts_ok", "Fan belts tight and show no obvious damage"),
        InspectionField("coolant_level_ok", "Coolant level acceptable"),
        InspectionField("washer_fluid_ok", "Washer fluid acceptable"),
        InspectionField("wipers_ok", "Windshield wipers"),
        InspectionField("tire_tread_ok", "Tire tread and sidewalls show no damage"),
        InspectionField("headlights_ok", "Headlights function on both hi and low beam"),
        InspectionField("turn_signals_ok", "Turn signals function (left/right)"),
        InspectionField("brake_lights_ok", "Brake lights function (including 3rd brake light)"),
        InspectionField("reverse_lights_ok", "Reverse lights function"),
        InspectionField("fluid_leak_detected", "Fluid leaking discovered"),
        InspectionField("engine_sound_ok", "How sounds", FieldType.TEXT, required=False),
        InspectionField("mirrors_ok", "Mirrors function and are clean"),
        InspectionField("emergency_system_ok", "Emergency lights and siren work"),
    ),
    InspectionType.RETURN: (
        InspectionField("odometer_miles", "Ending miles", FieldType.NUMBER),
        InspectionField("return_notes", "Return notes", FieldType.TEXT, required=False),
    ),
}


def get_form_definition(inspection_type: InspectionType) -> tuple[InspectionField, ...]:
    return FORM_DEFINITIONS[inspection_type]


def validate_responses(inspection_type: InspectionType, responses: Dict[str, Any]) -> Dict[str, Any]:
    expected = {field.id: field for field in get_form_definition(inspection_type)}
    cleaned: Dict[str, Any] = {}

    for field_id, field in expected.items():
        if field.required and field_id not in responses:
            raise ValueError(f"Missing required response for '{field.label}'")

    for key, value in responses.items():
        field = expected.get(key)
        if field is None:
            raise ValueError(f"Unexpected response field '{key}'")
        cleaned[key] = _coerce_value(field, value)

    return cleaned


def _coerce_value(field: InspectionField, value: Any) -> Any:
    if field.field_type is FieldType.BOOLEAN:
        if isinstance(value, bool):
            return value
        raise ValueError(f"Field '{field.label}' must be a boolean")
    if field.field_type is FieldType.TEXT:
        if isinstance(value, str):
            return value.strip()
        raise ValueError(f"Field '{field.label}' must be a string")
    if field.field_type is FieldType.NUMBER:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        raise ValueError(f"Field '{field.label}' must be a number")
    raise ValueError(f"Unsupported field type for '{field.label}'")
