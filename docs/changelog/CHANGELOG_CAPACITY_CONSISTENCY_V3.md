# Capacity Consistency V3

## Improvement
Added a visible machine capacity consistency check between `capacity_units_hour` and `base_cycle_sec`.

## Rule
- implied capacity = 3600 / base_cycle_sec
- gap = abs(master capacity - implied capacity) / implied capacity
- <= 5%: CONSISTENT
- >5% and <=10%: WARNING
- >10%: ERROR

## Backend
`GET /machine-calendar` now returns `implied_capacity_units_hour`, `capacity_gap_pct`, and `capacity_consistency_status`.

## Frontend
Machine Management now displays: Capacity master, Implied from cycle, Gap, Check, and Effective capacity, plus a visible consistency banner.

## CP-SAT
The optimizer validates machine capacity master data at startup and rejects a machine with a >5% mismatch between `capacity_units_hour` and `base_cycle_sec`. Product-specific `operation_time_min_per_unit` remains the routing requirement; machine capacity is the physical machine constraint.

## Verification
Python compilation completed successfully. Frontend build was not executed because `node_modules` is not included in the archive.
