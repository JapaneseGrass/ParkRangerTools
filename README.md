# ParkRangerTools

Software tools to help park rangers perform their jobs more effectively.

## Truck Inspection App (MVP)

The initial iteration of the Truck Inspection App is implemented as a lightweight
Python service layer with an accompanying SQLite persistence layer. The service
covers core MVP workflows:

- User management with ranger and supervisor roles.
- Secure authentication tokens.
- Truck catalog management (supervisor only).
- Quick and detailed inspection flows with validated checklists.
- Photo-count enforcement (4–10 per inspection) with on-device photo capture/upload support and an interactive fuel gauge.
- Ranger follow-up notes within a 24-hour window.
- Supervisor dashboard metrics for accountability and escalations.

The code lives under `backend/app` and exposes a high-level
`TruckInspectionApp` class that coordinates authentication, inspection
processing, and reporting.

### Running the app manually

The module can be executed directly to create a local SQLite database with seed
data and provide credentials for exploratory scripting:

```bash
python -m backend.app.app
```

This generates `truck_inspections.db` in the current directory with seed users
and trucks. You can then import `TruckInspectionApp` in a Python REPL and use
its methods to drive the workflows programmatically.

### Running the web interface

Run the web layer directly to start a local HTTP server:

```bash
python -m frontend.app
```

The server seeds a local `truck_inspections.db` file the first time it runs. Use
the default accounts to explore the interface:

- Ranger: `alex.ranger@example.com` / `rangerpass`
- Supervisor: `sam.supervisor@example.com` / `supervisorpass`

### Testing

Install development dependencies (only `pytest`) if needed and run the tests:

```bash
pytest
```

The tests exercise the authentication, inspection creation, note policies, and
dashboard aggregation logic using a temporary database for isolation.
