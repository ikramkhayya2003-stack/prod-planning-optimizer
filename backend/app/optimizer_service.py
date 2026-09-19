from __future__ import annotations

from datetime import date, datetime, timedelta
from dataclasses import replace
import traceback

from sqlalchemy.orm import Session

from optimizer_cp_sat import (
    AvailabilityEvent,
    CalendarDay,
    MachineCalendarData,
    ObjectiveWeights,
    ProductionCPSATOptimizer,
    SupplierLeadTimeScenario,
)

from app.db_planning_loader import (
    load_planning_data_from_db,
)


def _build_scenario_calendar(data, start_date=None, end_date=None, include_weekends=False):
    """Return only the requested planning horizon, without changing DB data."""
    if not start_date and not end_date:
        return data

    start_date = start_date or min(d.calendar_date for d in data.calendar_days)
    end_date = end_date or max(d.calendar_date for d in data.calendar_days)
    if end_date < start_date:
        raise ValueError("Planning horizon end date must be on or after start date.")

    db_flags = {d.calendar_date: d.is_workday for d in data.calendar_days}
    days = []
    current = start_date
    while current <= end_date:
        is_weekday = current.weekday() < 5
        is_workday = True if include_weekends else db_flags.get(current, is_weekday)
        days.append(CalendarDay(calendar_date=current, is_workday=is_workday))
        current += timedelta(days=1)

    if not any(d.is_workday for d in days):
        raise ValueError("Selected planning horizon contains no working day.")

    # Keep machine calendars aligned with the selected horizon. When the user
    # explicitly enables weekends, synthesize a normal 16h weekend capacity
    # for dates absent from the workbook, using each machine's master
    # availability. This affects only the in-memory scenario copy.
    horizon_dates = {d.calendar_date for d in days}
    machine_calendars = {}
    for machine_id, rows in data.machine_calendars.items():
        by_date = {r.calendar_date: r for r in rows}
        filtered = []
        machine = data.machines.get(machine_id)
        for d in days:
            if d.calendar_date in by_date:
                filtered.append(by_date[d.calendar_date])
            elif d.is_workday and include_weekends and machine is not None:
                factor = float(machine.availability_pct)
                if factor > 1.0:
                    factor /= 100.0
                factor = max(0.0, min(factor, 1.0))
                filtered.append(
                    MachineCalendarData(
                        machine_id=machine_id,
                        calendar_date=d.calendar_date,
                        is_workday=True,
                        scheduled_hours=16.0,
                        maintenance_hours=0.0,
                        planned_available_hours=16.0 * factor,
                        availability_factor=factor,
                    )
                )
        machine_calendars[machine_id] = filtered

    return replace(
        data,
        calendar_days=days,
        machine_calendars=machine_calendars,
    )


def _apply_scenario(data, scenario):
    """Apply a what-if scenario to an in-memory PlanningData copy only."""
    if not scenario:
        return data, None

    stype = scenario.get("type")
    if stype == "demand_increase":
        pct = float(scenario.get("demand_increase_pct", 0))
        multiplier = 1.0 + pct / 100.0
        data = replace(
            data,
            orders=[
                replace(order, order_qty=max(1, round(order.order_qty * multiplier)))
                for order in data.orders
            ],
        )
        return data, {
            "type": stype,
            "demand_increase_pct": pct,
        }

    if stype == "machine_unavailable":
        machine_id = scenario.get("machine_id")
        start = datetime.fromisoformat(scenario["machine_start"])
        end = datetime.fromisoformat(scenario["machine_end"])
        if machine_id not in data.machines:
            raise ValueError(f"Machine '{machine_id}' not found.")
        event = AvailabilityEvent(
            event_id=f"SCENARIO-BREAKDOWN-{machine_id}",
            machine_id=machine_id,
            event_start=start,
            event_end=end,
            event_type="SCENARIO_BREAKDOWN",
            duration_h=(end - start).total_seconds() / 3600.0,
        )
        data = replace(
            data,
            availability_events=list(data.availability_events) + [event],
        )
        return data, {
            "type": stype,
            "machine_id": machine_id,
            "machine_start": start.isoformat(),
            "machine_end": end.isoformat(),
        }

    if stype == "supplier_lead_time":
        supplier_id = scenario.get("supplier_id")
        delta = int(scenario.get("lead_time_delta_days", 0))
        if not supplier_id:
            raise ValueError("supplier_id is required.")
        if delta <= 0:
            raise ValueError("lead_time_delta_days must be > 0.")
        return data, {
            "type": stype,
            "supplier_id": supplier_id,
            "lead_time_delta_days": delta,
        }

    raise ValueError(f"Unsupported scenario type: {stype}")


def run_cp_sat(
    db: Session,
    run,
    config=None,
):
    """
    Load planning data from PostgreSQL,
    build CP-SAT model and solve it.
    """

    print("\n" + "=" * 80)
    print("[1/4] Loading planning data from PostgreSQL...")
    print("=" * 80)

    config = config or {}

    data = load_planning_data_from_db(db)
    data = _build_scenario_calendar(
        data,
        start_date=date.fromisoformat(config["planning_start_date"])
        if config.get("planning_start_date") else None,
        end_date=date.fromisoformat(config["planning_end_date"])
        if config.get("planning_end_date") else None,
        include_weekends=bool(config.get("include_weekends", False)),
    )
    data, scenario_meta = _apply_scenario(
        data,
        config.get("scenario"),
    )

    print(
        f"[DB] Machines   : {len(data.machines)}"
    )
    print(
        f"[DB] Products   : {len(data.products)}"
    )
    print(
        f"[DB] Orders     : {len(data.orders)}"
    )
    print(
        f"[DB] Materials  : {len(data.materials)}"
    )
    print(
        f"[DB] Routing    : "
        f"{sum(len(v) for v in data.routing.values())}"
    )
    print(
        f"[DB] BOM        : "
        f"{sum(len(v) for v in data.bom.values())}"
    )
    print(
        f"[DB] Setups     : "
        f"{len(data.setup_minutes)}"
    )
    print(
        f"[DB] Calendar   : "
        f"{len(data.calendar_days)}"
    )
    print(
        f"[DB] Events     : "
        f"{len(data.availability_events)}"
    )

    # ========================================================
    # OBJECTIVE
    # ========================================================

    print("\n" + "=" * 80)
    print("[2/4] Building objective weights...")
    print("=" * 80)

    objective = ObjectiveWeights(
        tardiness=run.weight_tardiness,
        setup=run.weight_setup,
        inventory=run.weight_inventory,
        idle=run.weight_idle,

        reference_tardiness_min=max(
            1,
            len(data.orders) * 8 * 60,
        ),

        reference_setup_min=10_000,

        reference_inventory_scaled=max(
            1,
            int(
                sum(
                    m.on_hand_qty
                    for m in data.materials.values()
                )
                * 100
                * max(
                    1,
                    len(data.calendar_days),
                )
            ),
        ),

        reference_idle_min=max(
            1,
            len(data.machines)
            * 16
            * 60
            * max(
                1,
                len(data.calendar_days),
            ),
        ),
    )

    print(
        f"[OBJECTIVE] tardiness = "
        f"{objective.tardiness}"
    )

    print(
        f"[OBJECTIVE] setup = "
        f"{objective.setup}"
    )

    print(
        f"[OBJECTIVE] inventory = "
        f"{objective.inventory}"
    )

    print(
        f"[OBJECTIVE] idle = "
        f"{objective.idle}"
    )

    # ========================================================
    # CREATE OPTIMIZER
    # ========================================================

    print("\n" + "=" * 80)
    print("[3/4] Building CP-SAT model...")
    print("=" * 80)

    supplier_scenario = None
    scenario = config.get("scenario") or {}
    if scenario.get("type") == "supplier_lead_time":
        supplier_scenario = SupplierLeadTimeScenario(
            supplier_id=scenario["supplier_id"],
            lead_time_delta_days=int(scenario["lead_time_delta_days"]),
        )

    optimizer = ProductionCPSATOptimizer(
        data,
        objective,
        supplier_lead_time_scenario=supplier_scenario,
        overtime_minutes=120 if config.get("include_overtime") else 0,
    )

    print("[CP-SAT] Model successfully created.")

    # ========================================================
    # SOLVE
    # ========================================================

    print("\n" + "=" * 80)
    print(
        "[4/4] Starting CP-SAT solver..."
    )
    print(
        f"[CP-SAT] Time limit     : "
        f"{run.max_time_seconds} seconds"
    )
    print(
        f"[CP-SAT] Workers        : "
        f"{run.num_workers}"
    )
    print(
        f"[CP-SAT] Random seed    : "
        f"{run.random_seed}"
    )
    print("=" * 80)

    start_time = datetime.utcnow()

    result = optimizer.solve(
        max_time_seconds=run.max_time_seconds,
        num_workers=run.num_workers,
        random_seed=run.random_seed,
        log_search_progress=False,
    )

    elapsed = (
        datetime.utcnow() - start_time
    ).total_seconds()

    print("\n" + "=" * 80)
    print("[CP-SAT] SOLVER FINISHED")
    print("=" * 80)

    print(
        f"[CP-SAT] Status       : "
        f"{result.status}"
    )

    print(
        f"[CP-SAT] Objective    : "
        f"{result.objective_value}"
    )

    print(
        f"[CP-SAT] Wall time    : "
        f"{elapsed:.2f} seconds"
    )

    print(
        f"[CP-SAT] Planning rows: "
        f"{len(result.planning_rows)}"
    )

    print(
        f"[CP-SAT] Order KPIs   : "
        f"{len(result.order_kpis)}"
    )

    print(
        f"[CP-SAT] Machine KPIs : "
        f"{len(result.machine_kpis)}"
    )

    print(
        f"[CP-SAT] Material KPIs: "
        f"{len(result.material_kpis)}"
    )

    return result


def save_optimization_result(
    db: Session,
    run,
    result,
):
    """
    Persist CP-SAT result into PostgreSQL.
    """

    from app.models import (
        PlanningResult,
        OrderKPI,
        MachineKPI,
        MaterialKPI,
        ProcurementPlan,
    )

    print("\n" + "=" * 80)
    print("[SAVE] Saving optimization result...")
    print("=" * 80)

    # ========================================================
    # RUN
    # ========================================================

    run.status = "COMPLETED"

    run.solver_status = result.status

    run.objective_value = (
        result.objective_value
    )

    run.summary_kpis = (
        result.summary_kpis
    )

    run.finished_at = datetime.utcnow()

    db.flush()

    # ========================================================
    # PLANNING
    # ========================================================

    print(
        f"[SAVE] Planning rows: "
        f"{len(result.planning_rows)}"
    )

    for row in result.planning_rows:

        db.add(
            PlanningResult(
                run_id=run.run_id,

                order_id=row["order_id"],

                product_id=row["product_id"],

                operation_seq=row[
                    "operation_seq"
                ],

                operation_code=row[
                    "operation_code"
                ],

                machine_id=row[
                    "machine_id"
                ],

                start_min=row[
                    "start_min"
                ],

                end_min=row[
                    "end_min"
                ],

                start_datetime=datetime.fromisoformat(
                    row["start_datetime"]
                ),

                end_datetime=datetime.fromisoformat(
                    row["end_datetime"]
                ),

                processing_minutes=row[
                    "processing_minutes"
                ],

                setup_from_product=row[
                    "setup_from_product"
                ],

                setup_minutes=row[
                    "setup_minutes"
                ],
            )
        )

    # ========================================================
    # ORDER KPI
    # ========================================================

    print(
        f"[SAVE] Order KPIs: "
        f"{len(result.order_kpis)}"
    )

    for row in result.order_kpis:

        db.add(
            OrderKPI(
                run_id=run.run_id,

                order_id=row["order_id"],

                customer=row["customer"],

                product_id=row["product_id"],

                priority_class=row[
                    "priority_class"
                ],

                priority_weight=row[
                    "priority_weight"
                ],

                urgent=row["urgent"],

                due_datetime=datetime.fromisoformat(
                    row["due_datetime"]
                ),

                completion_datetime=datetime.fromisoformat(
                    row["completion_datetime"]
                ),

                tardiness_min=row[
                    "tardiness_min"
                ],

                tardiness_hours=row[
                    "tardiness_hours"
                ],

                on_time=row["on_time"],
            )
        )

    # ========================================================
    # MACHINE KPI
    # ========================================================

    print(
        f"[SAVE] Machine KPIs: "
        f"{len(result.machine_kpis)}"
    )

    for row in result.machine_kpis:

        db.add(
            MachineKPI(
                run_id=run.run_id,

                machine_id=row[
                    "machine_id"
                ],

                available_working_min=row[
                    "available_working_min"
                ],

                busy_processing_min=row[
                    "busy_processing_min"
                ],

                setup_min=row[
                    "setup_min"
                ],

                setup_count=row[
                    "setup_count"
                ],

                idle_internal_min=row[
                    "idle_internal_min"
                ],

                utilization_pct=row[
                    "utilization_pct"
                ],

                occupancy_pct=row[
                    "occupancy_pct"
                ],
            )
        )

    # ========================================================
    # MATERIAL KPI
    # ========================================================

    print(
        f"[SAVE] Material KPIs: "
        f"{len(result.material_kpis)}"
    )

    for row in result.material_kpis:

        db.add(
            MaterialKPI(
                run_id=run.run_id,

                material_id=row[
                    "material_id"
                ],

                avg_inventory_qty=row[
                    "avg_inventory_qty"
                ],

                ending_inventory_qty=row[
                    "ending_inventory_qty"
                ],

                min_inventory_qty=row[
                    "min_inventory_qty"
                ],

                safety_stock_qty=row[
                    "safety_stock_qty"
                ],

                planned_replenishment_qty=row[
                    "planned_replenishment_qty"
                ],
            )
        )

    # ========================================================
    # PROCUREMENT PLAN
    # ========================================================

    print(
        f"[SAVE] Procurement rows: {len(result.procurement_kpis)}"
    )

    for row in result.procurement_kpis:
        db.add(
            ProcurementPlan(
                run_id=run.run_id,
                material_id=row["material_id"],
                supplier_id=row["supplier_id"],
                order_date=date.fromisoformat(row["order_date"]),
                receipt_date=(date.fromisoformat(row["receipt_date"]) if row.get("receipt_date") else None),
                order_qty=row["order_qty"],
                unit_cost_eur=row["unit_cost_eur"],
                purchase_cost_eur=row["purchase_cost_eur"],
                lead_time_days=row["lead_time_days"],
                min_order_qty=row["min_order_qty"],
                lot_size=row["lot_size"],
                reliability_pct=row["reliability_pct"],
            )
        )

    print("[SAVE] Committing transaction...")

    db.commit()

    print("[SAVE] Database commit successful.")

    print(
        f"[SAVE] Run {run.run_id} completed."
    )

    return result