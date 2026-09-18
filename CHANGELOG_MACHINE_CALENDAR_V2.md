# Machine Calendar & Capacity V2

- Added GET /machine-calendar with machine-specific horizon aggregates.
- Added Machine Calendar & Capacity table to Machines page.
- Shows scheduled, maintenance, planned available hours, calendar availability, master capacity and effective capacity.
- Effective capacity = capacity_units_hour × calendar availability ratio.
- Preserves the CP-SAT compressed time axis while using machine-specific calendar factors and explicit breakdown intervals.
