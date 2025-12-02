# ParkRangerTools

Software tools to help park rangers perform their jobs more effectively.

## Truck Inspection App (MVP)

The MVP is a lightweight Python application that pairs a SQLite database with a
minimal web interface. Rangers can log in, choose a truck, capture or upload the
required inspection photos, drag a fuel gauge to record fuel levels, answer the
quick or detailed checklist, add optional notes, and escalate issues for
supervisor visibility. Supervisors can sign in to review submissions, see
basic compliance metrics, and export the full inspection archive to an Excel
workbook that includes summary metrics, every checklist response, and embedded
photo evidence for quick sharing.

### Requirements

- Python 3.9 or newer
- `pip` (only required to install optional test dependencies)
- macOS, Linux, or Windows capable of running Python 3.9+

The only runtime dependency is `openpyxl`, used to assemble the Excel export;
everything else is handled with the Python standard library.

### Setup

1. Clone the repository and switch into it.
2. (Optional) Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3. (Optional) Install the development extras if you plan to run the tests:
   ```bash
   pip install -e .[dev]
   ```

### Database seeding and scripting

Run the backend module directly to create a local SQLite database seeded with
sample data. The script prints the default ranger and supervisor credentials and
leaves a `truck_inspections.db` file in the project root.

The default HQ fleet seeded into the database includes:

- Full-size ranger trucks: `SM88`, `P0106`
- Mid-size trucks: `P0101`, `P0103`, `427`
- Maintenance trucks: `T1`, `T2`, `T3`

```bash
python3 -m backend.app.app
```

You can then open a Python shell, import `TruckInspectionApp`, and call its
methods to exercise authentication, inspection submission, and reporting flows
programmatically.

### Running the web interface

Start the bundled WSGI server to explore the UI in a browser:

```bash
python3 -m frontend.app --host 0.0.0.0 --port 8000
```

Navigate to http://127.0.0.1:8000/ and sign in with one of the seeded accounts:

- Ranger: `ranger@email.com` / `password`
- Supervisor: `supervisor@email.com` / `password`

Uploaded photos are saved under `frontend/uploads/`, and the shared
`truck_inspections.db` file keeps inspection history for both roles.

Tip: When you bind to `0.0.0.0`, other devices on the same network (for example,
a phone or tablet) can reach the app by browsing to `http://<your-mac-ip>:8000/`.

### Quick deploy for demo (Render)

If you just need a public demo link (data is ephemeral on redeploy), you can point Render at this repo:

1. Keep the included `requirements.txt`.
2. Create a Render Web Service (Python), leave the build command blank, and set the start command to:
   ```
   python frontend/app.py --host 0.0.0.0 --port $PORT
   ```
3. Deploy on the free plan; expect uploads/DB to reset when the service redeploys or sleeps.

Rangers now check out a vehicle before taking it into the field. A checkout triggers
an inspection that records the starting mileage; the vehicle disappears from the
available list until it is returned. Returning a vehicle requires a second
inspection to capture ending mileage, ensuring the fleet log always reflects the
latest odometer values. The return flow is lightweight—only the final mileage is
required, with optional notes if the ranger wants to flag anything for follow-up.

Account creation is restricted to an allow list. Only approved addresses
(`ranger@email.com`, `supervisor@email.com` and a handful of helper test
accounts such as `test@email.com`) may be registered in the system. New accounts must provide a ranger number, and existing users can update
their profile (name and ranger number) or reset their password from the login
flow.

### Testing

Run the pytest suite (after installing the optional dev dependencies) to verify
the core flows:

```bash
pytest
```

The tests cover authentication, photo validation, inspection creation, follow-up
note windows, and supervisor dashboard metrics using an isolated temporary
database.

### Generating mock data

Need a fuller dataset for demos or manual QA? Seed the default database, then
run the helper script to create realistic checkout/return pairs (each with photo
evidence):

```bash
python3 -m backend.app.mock_data --pairs 60 --database truck_inspections.db
```

Adjust `--pairs` or point `--database` at another SQLite file to suit your
environment.
