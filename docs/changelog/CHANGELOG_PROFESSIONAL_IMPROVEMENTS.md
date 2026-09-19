# Production Optimizer — Corrections & professional improvements

## Fixed
- Fixed What-if page crash caused by rendering FastAPI validation objects directly in React.
- Fixed `/materials?limit=1000` by enforcing a safe frontend maximum of 500.
- Added robust API error-to-string handling for FastAPI validation errors.
- Removed the old persistent Demand/Breakdown scenario behavior from the What-if UI.
  Scenarios are now transient inputs to CP-SAT and do not modify production master data.
- Removed duplicate planning-operation PUT decorator in the backend.

## Planning Horizon
The optimizer now accepts:
- `planning_start_date`
- `planning_end_date`
- `include_weekends`
- `include_overtime`

The same horizon controls are available in:
- Optimization Center
- What-if Scenario Analysis

Overtime is modeled as an additional 120 working minutes per working day.

## What-if scenarios
The three scenarios are now modeled by the backend:

### Demand Increase
Temporarily increases order quantities in memory before CP-SAT.

### Machine Unavailable
Adds a temporary availability-blocking interval to the CP-SAT model.

### Supplier Lead Time
Temporarily increases lead time for materials belonging to the selected supplier:
`effective lead time = base lead time + scenario delay`.

No database master value is modified.

## Scenario comparison
The What-if page no longer displays fixed example KPI values.
It compares:
- latest completed run = baseline
- current scenario run = actual CP-SAT result

Metrics:
- On-time delivery
- Average machine utilization
- Late orders
- Average tardiness

## Validation
- Python source files pass AST/compile validation.
- All React JSX files pass Babel parser validation.
- Vite build could not be executed in the packaged Linux environment because the uploaded `node_modules` contains Windows/platform-specific Rollup optional dependencies. On Windows, run `npm install` (or `npm ci`) in the frontend directory before `npm run dev`.

## Start on Windows
Backend:
`python -m uvicorn app.main:app --reload`

Frontend:
`npm install`
`npm run dev`

API:
`http://127.0.0.1:8000`

Frontend:
`http://127.0.0.1:5173`
