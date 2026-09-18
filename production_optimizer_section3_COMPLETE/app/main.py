import shutil
import re
from pathlib import Path
from datetime import date, datetime
from uuid import uuid4
from pydantic import BaseModel, Field
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from fastapi.middleware.cors import (
    CORSMiddleware
)
from app.shortage_prediction import (
    predict_material_shortage,
    predict_all_material_shortages,
)
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, DATASET_PATH

from app.database import (
    SessionLocal,
    get_db,
)

from app.models import (
    BOM,
    BreakdownEvent,
    Machine,
    MachineKPI,
    MachineEvent,
    MachineCalendar,
    Material,
    MaterialKPI,
    Order,
    OrderKPI,
    OptimizationRun,
    PlanningResult,
    Product,
    Routing,
    ScenarioOrder,
    SetupMatrix,
    Supplier,
    ProcurementPlan
)

from app.optimizer_service import (
    run_cp_sat,
    save_optimization_result,
)
from app.risk_service import (
    RISK_RANK,
    build_order_risk_map,
)
from app.plan_explainer import PlanExplainer
from app.repository import (
    get_run,
    save_breakdown,
    save_order,
    save_run,
)

from app.schemas import (
    BreakdownRequest,
    OptimizeRequest,
    OrderCreateRequest,
    PlanningOperationUpdate,
    PlanningOperationUpdateResponse,
)
class AssistantRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    run_id: str | None = None


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Automotive Production Optimizer API",
    description=(
        "Production planning optimization API "
        "for an automotive wiring harness factory."
    ),
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================


app.add_middleware(
    CORSMiddleware,

    allow_origin_regex=(
        r"https?://(localhost|127\.0\.0\.1):(5173|5174|5175|5176|5177|5178|5179|5180)"
    ),

    allow_credentials=True,

    allow_methods=[
        "*"
    ],

    allow_headers=[
        "*"
    ],
)


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "application":
            "Automotive Production Optimizer",

        "version":
            "1.0.0",

        "status":
            "running",
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health(
    db: Session = Depends(get_db),
):
    """Return API, database and dataset health without leaking tracebacks."""
    try:
        # A lightweight DB round-trip catches unavailable PostgreSQL early.
        from sqlalchemy import text
        db.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "ok",
            "dataset_exists": Path(DATASET_PATH).exists(),
            "dataset_path": str(Path(DATASET_PATH).resolve()),
            "machines": db.query(Machine).count(),
            "materials": db.query(Material).count(),
            "orders": db.query(Order).count(),
            "products": db.query(Product).count(),
            "suppliers": db.query(Supplier).count(),
        }
    except Exception as exc:
        # Keep CORS-friendly JSON instead of an unhandled 500.
        return {
            "status": "degraded",
            "database": "offline",
            "dataset_exists": Path(DATASET_PATH).exists(),
            "dataset_path": str(Path(DATASET_PATH).resolve()),
            "error": f"{type(exc).__name__}: {exc}",
        }


# ============================================================
# GET /orders
# ============================================================

@app.get("/orders")
def get_orders(

    customer: str | None = Query(
        default=None
    ),

    product_id: str | None = Query(
        default=None
    ),

    priority_class: str | None = Query(
        default=None
    ),

    order_status: str | None = Query(
        default=None
    ),

    urgent_only: bool = Query(
        default=False
    ),

    run_id: str | None = Query(
        default=None
    ),

    risk: str | None = Query(
        default=None
    ),

    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),

    offset: int = Query(
        default=0,
        ge=0,
    ),

    db: Session = Depends(get_db),
):

    # --------------------------------------------------------
    # BASE QUERY
    # --------------------------------------------------------

    query = db.query(
        Order
    )

    # --------------------------------------------------------
    # FILTER CUSTOMER
    # --------------------------------------------------------

    if customer:

        query = query.filter(
            Order.customer.ilike(
                f"%{customer}%"
            )
        )

    # --------------------------------------------------------
    # FILTER PRODUCT
    # --------------------------------------------------------

    if product_id:

        query = query.filter(
            Order.product_id
            == product_id
        )

    # --------------------------------------------------------
    # FILTER PRIORITY
    # --------------------------------------------------------

    if priority_class:

        query = query.filter(
            Order.priority_class
            == priority_class.upper()
        )

    # --------------------------------------------------------
    # FILTER STATUS
    # --------------------------------------------------------

    if order_status:

        query = query.filter(
            Order.order_status
            == order_status
        )

    # --------------------------------------------------------
    # FILTER URGENT
    # --------------------------------------------------------

    if urgent_only:

        query = query.filter(
            Order.is_urgent.is_(True)
        )

    # --------------------------------------------------------
    # RISK MAP
    # --------------------------------------------------------

    risk_map = build_order_risk_map(
        db,
        run_id,
    )

    # --------------------------------------------------------
    # RISK FILTER
    # --------------------------------------------------------

    if risk:

        risk_value = (
            risk.upper()
        )

        matching_order_ids = [

            order_id

            for order_id, risk_data
            in risk_map.items()

            if risk_data[
                "risk"
            ] == risk_value
        ]

        query = query.filter(
            Order.order_id.in_(
                matching_order_ids
            )
        )

    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------

    total = query.count()

    # --------------------------------------------------------
    # PAGINATION
    # --------------------------------------------------------

    rows = (
        query
        .order_by(
            Order.requested_due_date.asc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    # --------------------------------------------------------
    # BUILD RESPONSE
    # --------------------------------------------------------

    orders_response = []

    for row in rows:

        risk_data = risk_map.get(
            row.order_id,
            {}
        )

        orders_response.append(

            {

                "order_id":
                    row.order_id,

                "customer":
                    row.customer,

                "product_id":
                    row.product_id,

                "order_qty":
                    row.order_qty,

                "order_date":
                    row.order_date,

                "requested_due_date":
                    row.requested_due_date,

                "priority_class":
                    row.priority_class,

                "priority_weight":
                    row.priority_weight,

                "order_status":
                    row.order_status,

                "is_urgent":
                    row.is_urgent,

                # --------------------------------------------
                # RISK
                # --------------------------------------------

                "risk":
                    risk_data.get(
                        "risk",
                        "LOW"
                    ),

                "risk_reasons":
                    risk_data.get(
                        "reasons",
                        [
                            "No critical risk detected"
                        ]
                    ),

                "expected_completion":
                    risk_data.get(
                        "expected_completion"
                    ),

                "delay_hours":
                    risk_data.get(
                        "delay_hours",
                        0
                    ),

                "delay_days":
                    risk_data.get(
                        "delay_days",
                        0
                    ),

                "material_risks":
                    risk_data.get(
                        "material_risks",
                        []
                    ),

                "material_ids":
                    risk_data.get(
                        "material_ids",
                        []
                    ),

                "machine_risks":
                    risk_data.get(
                        "machine_risks",
                        []
                    ),
            }
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {

        "total":
            total,

        "limit":
            limit,

        "offset":
            offset,

        "count":
            len(orders_response),

        "orders":
            orders_response,
    }
# ============================================================
# GET /orders/risk
# ============================================================

@app.get("/orders/risk")
def get_order_risk(

    run_id: str | None = Query(
        default=None
    ),

    risk: str | None = Query(
        default=None
    ),

    db: Session = Depends(get_db),
):

    risk_map = build_order_risk_map(
        db,
        run_id,
    )

    orders = list(
        risk_map.values()
    )

    # --------------------------------------------------------
    # FILTER RISK
    # --------------------------------------------------------

    if risk:

        risk_value = (
            risk.upper()
        )

        orders = [
            row
            for row in orders
            if row["risk"]
            == risk_value
        ]

    # --------------------------------------------------------
    # SORT HIGH -> LOW
    # --------------------------------------------------------

    orders.sort(
        key=lambda row: (
            -RISK_RANK.get(
                row["risk"],
                1
            ),

            -float(
                row["delay_hours"]
                or 0
            ),
        )
    )

    return {

        "run_id":
            run_id,

        "count":
            len(orders),

        "high":
            sum(
                row["risk"]
                == "HIGH"
                for row in orders
            ),

        "medium":
            sum(
                row["risk"]
                == "MEDIUM"
                for row in orders
            ),

        "low":
            sum(
                row["risk"]
                == "LOW"
                for row in orders
            ),

        "orders":
            orders,
    }
# ============================================================
# GET /machines
# ============================================================

@app.get("/machines")
def get_machines(

    stage: str | None = Query(
        default=None
    ),

    machine_type: str | None = Query(
        default=None
    ),

    db: Session = Depends(get_db),
):

    query = db.query(
        Machine
    )

    if stage:

        query = query.filter(
            Machine.stage
            == stage
        )

    if machine_type:

        query = query.filter(
            Machine.machine_type
            == machine_type
        )

    rows = (
        query
        .order_by(
            Machine.machine_id
        )
        .all()
    )

    return {

        "total":
            len(rows),

        "machines": [

            {

                "machine_id":
                    row.machine_id,

                "machine_name":
                    row.machine_name,

                "machine_type":
                    row.machine_type,

                "stage":
                    row.stage,

                "capacity_units_hour":
                    row.capacity_units_hour,

                "base_cycle_sec":
                    row.base_cycle_sec,

                "availability_pct":
                    row.availability_pct,

                "shift_pattern":
                    row.shift_pattern,

                "setup_skill":
                    row.setup_skill,
            }

            for row in rows
        ],
    }


# ============================================================
# GET /machine-calendar
# ============================================================
@app.get("/machine-calendar")
def get_machine_calendar(
    machine_id: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return machine-specific calendar capacity for the selected horizon."""
    query = db.query(MachineCalendar)
    if machine_id:
        query = query.filter(MachineCalendar.machine_id == machine_id)
    if start_date:
        query = query.filter(MachineCalendar.calendar_date >= start_date)
    if end_date:
        query = query.filter(MachineCalendar.calendar_date <= end_date)
    rows = query.order_by(MachineCalendar.machine_id, MachineCalendar.calendar_date).all()
    grouped = {}
    for row in rows:
        grouped.setdefault(row.machine_id, []).append({
            "machine_id": row.machine_id,
            "date": row.calendar_date.isoformat(),
            "is_workday": bool(row.is_workday),
            "scheduled_hours": float(row.scheduled_hours or 0),
            "maintenance_hours": float(row.maintenance_hours or 0),
            "planned_available_hours": float(row.planned_available_hours or 0),
            "availability_factor": float(row.availability_factor or 0),
        })
    machine_map = {m.machine_id: m for m in db.query(Machine).all()}
    machines = []
    for mid, items in grouped.items():
        master = machine_map.get(mid)
        scheduled = sum(x["scheduled_hours"] for x in items if x["is_workday"])
        maintenance = sum(x["maintenance_hours"] for x in items if x["is_workday"])
        available = sum(x["planned_available_hours"] for x in items if x["is_workday"])
        factor = available / scheduled if scheduled else 0
        cap = float(master.capacity_units_hour) if master else 0
        base_cycle_sec = float(master.base_cycle_sec) if master else 0
        implied_cap = 3600.0 / base_cycle_sec if base_cycle_sec > 0 else 0.0
        gap_pct = (abs(cap - implied_cap) / implied_cap * 100.0) if implied_cap > 0 else None
        consistency_status = (
            "CONSISTENT" if gap_pct is not None and gap_pct <= 5.0
            else "WARNING" if gap_pct is not None and gap_pct <= 10.0
            else "ERROR" if gap_pct is not None else "MISSING"
        )
        machines.append({
            "machine_id": mid,
            "machine_name": master.machine_name if master else mid,
            "capacity_units_hour": cap,
            "base_cycle_sec": base_cycle_sec,
            "implied_capacity_units_hour": implied_cap,
            "capacity_gap_pct": gap_pct,
            "capacity_consistency_status": consistency_status,
            "master_availability_pct": float(master.availability_pct) if master else 0,
            "scheduled_hours": scheduled,
            "maintenance_hours": maintenance,
            "planned_available_hours": available,
            "calendar_availability_pct": factor * 100,
            "effective_capacity_units_hour": cap * factor,
            "calendar": items,
        })
    return {"total_machines": len(machines), "machines": machines}


# ============================================================
# GET /materials
# ============================================================

@app.get("/materials")
def get_materials(

    material_type: str | None = Query(
        default=None
    ),

    supplier_id: str | None = Query(
        default=None
    ),

    critical_only: bool = Query(
        default=False
    ),

    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),

    offset: int = Query(
        default=0,
        ge=0,
    ),

    db: Session = Depends(get_db),
):

    query = db.query(
        Material
    )

    if material_type:

        query = query.filter(
            Material.material_type
            == material_type
        )

    if supplier_id:

        query = query.filter(
            Material.supplier_id
            == supplier_id
        )

    if critical_only:

        query = query.filter(
            Material.coverage_days
            < 7
        )

    total = query.count()

    rows = (
        query
        .order_by(
            Material.coverage_days.asc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {

        "total":
            total,

        "limit":
            limit,

        "offset":
            offset,

        "count":
            len(rows),

        "materials": [

            {

                "material_id":
                    row.material_id,

                "material_name":
                    row.material_name,

                "material_type":
                    row.material_type,

                "uom":
                    row.uom,

                "on_hand_qty":
                    row.on_hand_qty,

                "safety_stock_qty":
                    row.safety_stock_qty,

                "lead_time_days":
                    row.lead_time_days,

                "supplier_id":
                    row.supplier_id,

                "lot_size":
                    row.lot_size,

                "horizon_requirement_qty":
                    row.horizon_requirement_qty,

                "avg_daily_requirement":
                    row.avg_daily_requirement,

                "coverage_days":
                    row.coverage_days,

                "risk_level":
                    (
                        "HIGH"
                        if row.coverage_days < 7
                        else (
                            "MEDIUM"
                            if row.coverage_days < 14
                            else "LOW"
                        )
                    ),
            }

            for row in rows
        ],
    }


# ============================================================
# GET /products
# ============================================================

@app.get("/products")
def get_products(

    family: str | None = Query(
        default=None
    ),

    product_status: str | None = Query(
        default=None
    ),

    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),

    offset: int = Query(
        default=0,
        ge=0,
    ),

    db: Session = Depends(get_db),
):

    query = db.query(
        Product
    )

    if family:

        query = query.filter(
            Product.family
            == family
        )

    if product_status:

        query = query.filter(
            Product.product_status
            == product_status
        )

    total = query.count()

    rows = (
        query
        .order_by(
            Product.product_id
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {

        "total":
            total,

        "limit":
            limit,

        "offset":
            offset,

        "count":
            len(rows),

        "products": [

            {

                "product_id":
                    row.product_id,

                "product_name":
                    row.product_name,

                "family":
                    row.family,

                "customer_mix":
                    row.customer_mix,

                "revision":
                    row.revision,

                "standard_batch_qty":
                    row.standard_batch_qty,

                "min_batch_qty":
                    row.min_batch_qty,

                "max_batch_qty":
                    row.max_batch_qty,

                "product_status":
                    row.product_status,

                "cycle_time_min_per_unit":
                    row.cycle_time_min_per_unit,

                "touch_time_min_per_unit":
                    row.touch_time_min_per_unit,
            }

            for row in rows
        ],
    }


# ============================================================
# GET /products/{product_id}
# ============================================================

@app.get(
    "/products/{product_id}"
)
def get_product_detail(

    product_id: str,

    db: Session = Depends(get_db),
):

    product = (
        db.query(
            Product
        )
        .filter(
            Product.product_id
            == product_id
        )
        .first()
    )

    if product is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Product "
                f"'{product_id}' "
                "not found."
            ),
        )

    bom_rows = (
        db.query(
            BOM
        )
        .filter(
            BOM.product_id
            == product_id
        )
        .all()
    )

    routing_rows = (
        db.query(
            Routing
        )
        .filter(
            Routing.product_id
            == product_id
        )
        .order_by(
            Routing.operation_seq
        )
        .all()
    )

    return {

        "product": {

            "product_id":
                product.product_id,

            "product_name":
                product.product_name,

            "family":
                product.family,

            "customer_mix":
                product.customer_mix,

            "revision":
                product.revision,

            "product_status":
                product.product_status,

            "cycle_time_min_per_unit":
                product.cycle_time_min_per_unit,
        },

        "bom": [

            {

                "material_id":
                    row.material_id,

                "qty_per_unit":
                    row.qty_per_unit,

                "scrap_factor_pct":
                    row.scrap_factor_pct,
            }

            for row in bom_rows
        ],

        "routing": [

            {

                "operation_seq":
                    row.operation_seq,

                "operation_code":
                    row.operation_code,

                "operation_name":
                    row.operation_name,

                "machine_group":
                    row.machine_group,

                "compatible_machines":
                    row.compatible_machines,

                "operation_time_min_per_unit":
                    row.operation_time_min_per_unit,

                "setup_family":
                    row.setup_family,
            }

            for row in routing_rows
        ],
    }


# ============================================================
# OPTIMIZATION WORKER
# ============================================================

# ============================================================
# OPTIMIZATION WORKER
# ============================================================

def optimization_worker(
    run_id: str,
    config: dict | None = None,
):
    """
    Execute one CP-SAT optimization run in background.

    The worker is deliberately defensive:
    - every terminal state is persisted;
    - solver errors cannot leave the run in RUNNING;
    - database errors during error handling are caught;
    - solver_status remains compact.
    """

    db = SessionLocal()

    try:

        # ----------------------------------------------------
        # LOAD RUN
        # ----------------------------------------------------

        run = get_run(
            db,
            run_id,
        )

        if run is None:

            print(
                f"[ERROR] Run not found: {run_id}"
            )

            return

        # ----------------------------------------------------
        # MARK RUNNING
        # ----------------------------------------------------

        run.status = "RUNNING"

        run.started_at = (
            datetime.utcnow()
        )

        db.commit()

        print()
        print("=" * 70)
        print(
            f"START OPTIMIZATION - RUN {run_id}"
        )
        print("=" * 70)

        # ====================================================
        # EXECUTE SOLVER
        # ====================================================

        try:

            print(
                "[WORKER] Calling CP-SAT..."
            )

            result = run_cp_sat(
                db,
                run,
                config=config or {},
            )

            print()
            print(
                "=" * 70
            )
            print(
                "[WORKER] CP-SAT RETURNED"
            )
            print(
                "=" * 70
            )

            print(
                f"Status        : "
                f"{result.status}"
            )

            print(
                f"Objective     : "
                f"{result.objective_value}"
            )

            print(
                f"Planning rows : "
                f"{len(result.planning_rows)}"
            )

            print(
                f"Order KPIs    : "
                f"{len(result.order_kpis)}"
            )

            print(
                f"Machine KPIs  : "
                f"{len(result.machine_kpis)}"
            )

            print(
                f"Material KPIs : "
                f"{len(result.material_kpis)}"
            )

            # =================================================
            # UNKNOWN
            # =================================================

            if result.status == "UNKNOWN":

                print(
                    "[CP-SAT] "
                    "No feasible solution found "
                    "within the configured time limit."
                )

                # ------------------------------------------------
                # IMPORTANT:
                # Keep API state compatible with React.
                # React expects FAILED as terminal state.
                # ------------------------------------------------

                run.status = "FAILED"

                run.solver_status = (
                    "UNKNOWN_TIMEOUT"
                )

                # Do not store a misleading objective
                # when no planning solution exists.
                run.objective_value = None

                run.finished_at = (
                    datetime.utcnow()
                )

                db.commit()

                print(
                    "[WORKER] "
                    "Run saved as FAILED / UNKNOWN_TIMEOUT."
                )

                return

            # =================================================
            # OTHER UNSUCCESSFUL STATES
            # =================================================

            if result.status not in {
                "FEASIBLE",
                "OPTIMAL",
            }:

                print(
                    "[CP-SAT] "
                    "Solver returned "
                    f"status={result.status}"
                )

                run.status = "FAILED"

                # Compact and database-safe.
                run.solver_status = (
                    str(
                        result.status
                    )[:500]
                )

                run.objective_value = None

                run.finished_at = (
                    datetime.utcnow()
                )

                db.commit()

                print(
                    "[WORKER] "
                    "Run saved as FAILED."
                )

                return

            # =================================================
            # FEASIBLE / OPTIMAL
            # =================================================

            print(
                "[WORKER] "
                "Saving planning and KPI results..."
            )

            save_optimization_result(
                db,
                run,
                result,
            )

            print()
            print("=" * 70)
            print(
                f"SUCCESS - RUN {run_id}"
            )
            print("=" * 70)

        # ====================================================
        # SOLVER / DATABASE ERROR
        # ====================================================

        except Exception as exc:

            import traceback

            print()
            print("=" * 70)
            print(
                "OPTIMIZATION WORKER ERROR"
            )
            print("=" * 70)

            traceback.print_exc()

            print("=" * 70)

            # ------------------------------------------------
            # ROLLBACK
            # ------------------------------------------------

            try:
                db.rollback()
            except Exception:
                pass

            # ------------------------------------------------
            # SAVE FAILURE SAFELY
            # ------------------------------------------------

            try:

                failed_run = get_run(
                    db,
                    run_id,
                )

                if failed_run is not None:

                    failed_run.status = (
                        "FAILED"
                    )

                    # IMPORTANT:
                    # Do NOT store the complete traceback.
                    # Only store a compact error.
                    error_text = (
                        f"{type(exc).__name__}: "
                        f"{str(exc)}"
                    )

                    failed_run.solver_status = (
                        error_text[:500]
                    )

                    failed_run.objective_value = (
                        None
                    )

                    failed_run.finished_at = (
                        datetime.utcnow()
                    )

                    db.commit()

                    print(
                        "[WORKER] "
                        "Failure status persisted."
                    )

            except Exception as status_error:

                try:
                    db.rollback()
                except Exception:
                    pass

                print()
                print("=" * 70)
                print(
                    "FAILED TO PERSIST ERROR STATUS"
                )
                print("=" * 70)

                print(
                    f"Original error: "
                    f"{type(exc).__name__}: "
                    f"{str(exc)}"
                )

                print(
                    f"Status error: "
                    f"{type(status_error).__name__}: "
                    f"{str(status_error)}"
                )

                print("=" * 70)

    finally:

        db.close()

        print(
            f"[WORKER] Database session closed "
            f"for run {run_id}."
        )
# ============================================================
# POST /optimize
# ============================================================

@app.post(
    "/optimize",
    status_code=status.HTTP_202_ACCEPTED,
)
def optimize(

    request: OptimizeRequest,

    background_tasks:
        BackgroundTasks,

    db: Session = Depends(get_db),
):

    run_id = uuid4().hex

    run = OptimizationRun(

        run_id=run_id,

        status="QUEUED",

        max_time_seconds=
            request.max_time_seconds,

        num_workers=
            request.num_workers,

        random_seed=
            request.random_seed,

        weight_tardiness=
            request.weights.tardiness,

        weight_setup=
            request.weights.setup,

        weight_inventory=
            request.weights.inventory,

        weight_idle=
            request.weights.idle,

        created_at=
            datetime.utcnow(),
    )

    save_run(
        db,
        run,
    )

    background_tasks.add_task(
        optimization_worker,
        run_id,
        request.model_dump(mode="json"),
    )

    return {

        "run_id":
            run_id,

        "status":
            "QUEUED",

        "message":
            "Optimization submitted successfully.",

        "planning_horizon": {
            "start_date": request.planning_start_date.isoformat() if request.planning_start_date else None,
            "end_date": request.planning_end_date.isoformat() if request.planning_end_date else None,
            "include_weekends": request.include_weekends,
            "include_overtime": request.include_overtime,
        },

        "scenario": request.scenario.model_dump(mode="json") if request.scenario else None,

        "status_url":
            f"/runs/{run_id}",

        "planning_url":
            f"/planning/{run_id}",

        "kpis_url":
            f"/kpis/{run_id}",
    }


# ============================================================
# PLANNING ASSISTANT
# ============================================================

@app.post("/assistant/ask")
def planning_assistant(
    payload: AssistantRequest,
    db: Session = Depends(get_db),
):
    """Explain the current planning data using deterministic, auditable rules.

    This first version intentionally does not invent information and does not
    require an external LLM/API key. It is therefore safe for a portfolio/demo
    environment and can later be connected to an LLM as a natural-language layer.
    """
    question = payload.question.strip()
    q = question.lower()

    run = None
    if payload.run_id:
        run = db.query(OptimizationRun).filter(OptimizationRun.run_id == payload.run_id).first()
    if run is None:
        run = db.query(OptimizationRun).order_by(OptimizationRun.created_at.desc(), OptimizationRun.id.desc()).first()

    if run is None:
        return {
            "answer": "I can analyze the planning data once an optimization run is available. Please run the optimizer first.",
            "facts": [],
        }

    run_id = run.run_id
    planning = db.query(PlanningResult).filter(PlanningResult.run_id == run_id).all()
    risk_map = build_order_risk_map(db, run_id)
    orders = {o.order_id: o for o in db.query(Order).all()}
    for o in db.query(ScenarioOrder).all():
        orders[o.order_id] = o

    # ----- specific order question -----------------------------------------
    order_match = re.search(r"\b(?:ord(?:er)?[-_ ]?)?([a-z]{0,4}[-_]?[0-9]{2,})\b", question, re.I)
    if order_match:
        token = order_match.group(1).upper().replace("_", "-")
        candidates = [oid for oid in orders if oid.upper() == token or oid.upper().endswith(token)]
        order_id = candidates[0] if candidates else token
        if order_id in orders or order_id in risk_map:
            risk = risk_map.get(order_id, {})
            rows = [r for r in planning if r.order_id == order_id]
            order = orders.get(order_id)
            reasons = list(risk.get("reasons") or [])
            material = risk.get("material_risks") or []
            machine = risk.get("machine_risks") or []
            if not reasons:
                reasons.append("No major risk reason was recorded for this order.")
            details = []
            if machine:
                details.append("Machine constraint: " + ", ".join(str(x) for x in machine[:3]))
            if material:
                details.append("Material constraint: " + ", ".join(str(x) for x in material[:3]))
            if order and getattr(order, "priority_class", None):
                details.append(f"Priority class: {order.priority_class}")
            completion = risk.get("expected_completion")
            due = risk.get("due_datetime")
            delay = float(risk.get("delay_hours") or 0)
            answer = f"{order_id} is classified as {risk.get('risk', 'LOW')} risk.\n"
            answer += "Main explanation: " + "; ".join(str(x) for x in reasons[:3]) + ".\n"
            if details:
                answer += "\n".join(details) + "\n"
            if due:
                answer += f"Due date: {due}. "
            if completion:
                answer += f"Expected completion: {completion}. "
            if delay > 0:
                answer += f"Estimated delay: {delay:.1f} h."
            else:
                answer += "No delay is currently recorded."
            return {"answer": answer, "facts": [f"Risk: {risk.get('risk', 'LOW')}", f"Operations: {len(rows)}", f"Run: {run_id}"]}

    # ----- machine question ------------------------------------------------
    if any(word in q for word in ("machine", "capacity", "loaded", "charge", "utilization", "utilisation")):
        machine_load = {}
        for r in planning:
            machine_load.setdefault(r.machine_id, 0.0)
            machine_load[r.machine_id] += float(r.processing_minutes or 0) + float(r.setup_minutes or 0)
        ranked = sorted(machine_load.items(), key=lambda x: x[1], reverse=True)
        if ranked:
            top = ranked[:5]
            lines = [f"{mid}: {mins/60:.1f} scheduled hours" for mid, mins in top]
            return {"answer": "The most loaded machines in the active plan are:\n" + "\n".join(lines) + "\n\nThis ranking is based on scheduled processing plus setup time in the selected run.", "facts": [f"Machines scheduled: {len(machine_load)}", f"Run: {run_id}"]}

    # ----- material question ------------------------------------------------
    if any(word in q for word in ("material", "stock", "shortage", "matière", "rupture")):
        materials = db.query(Material).all()
        critical = [m for m in materials if float(m.on_hand_qty or 0) < float(m.safety_stock_qty or 0)]
        critical.sort(key=lambda m: (float(m.on_hand_qty or 0) - float(m.safety_stock_qty or 0)))
        if critical:
            lines = [f"{m.material_id}: stock {m.on_hand_qty:g} < safety {m.safety_stock_qty:g} (coverage {m.coverage_days:.1f} d)" for m in critical[:8]]
            return {"answer": "The materials currently below safety stock are:\n" + "\n".join(lines) + "\n\nThese are risk indicators; a true shortage date requires future consumption/replenishment data.", "facts": [f"Critical materials: {len(critical)}", f"Run: {run_id}"]}
        return {"answer": "No material is currently below its safety-stock threshold in the database.", "facts": [f"Materials checked: {len(materials)}", f"Run: {run_id}"]}

    # ----- risk question ----------------------------------------------------
    if any(word in q for word in ("risk", "late", "retard", "urgent", "critical")):
        unique = {}
        for oid, data in risk_map.items():
            unique[oid] = data
        ranked = sorted(unique.items(), key=lambda x: (RISK_RANK.get(str(x[1].get("risk", "LOW")).upper(), 0), float(x[1].get("delay_hours") or 0)), reverse=True)
        top = ranked[:8]
        if top:
            lines = [f"{oid}: {data.get('risk', 'LOW')} — delay {float(data.get('delay_hours') or 0):.1f} h" for oid, data in top]
            return {"answer": "The highest-risk orders in the active run are:\n" + "\n".join(lines), "facts": [f"Orders analyzed: {len(unique)}", f"Run: {run_id}"]}

    # ----- generic plan explanation ----------------------------------------
    if any(word in q for word in ("plan", "planning", "planning actuel", "explain", "explique", "schedule")):
        late = len({r.order_id for r in planning if float((risk_map.get(r.order_id) or {}).get("delay_hours") or 0) > 0})
        machines = len({r.machine_id for r in planning})
        setup = sum(float(r.setup_minutes or 0) for r in planning)
        processing = sum(float(r.processing_minutes or 0) for r in planning)
        answer = (f"The active plan contains {len(planning)} scheduled operations across {machines} machines.\n"
                  f"Scheduled processing time is {processing/60:.1f} h and setup time is {setup/60:.1f} h.\n"
                  f"{late} orders are currently associated with a positive delay.\n\n"
                  "The plan is generated by the CP-SAT optimizer and reflects the constraints represented in the system, including routing, machine assignment, setups, priorities and material-risk information.")
        return {"answer": answer, "facts": [f"Solver: {run.solver_status or run.status}", f"Objective: {run.objective_value}", f"Run: {run_id}"]}

    return {
        "answer": "I can currently answer questions about order delays/risk, machine load and capacity, material/stock risks, and the active production plan. Try: ‘Why is ORD104 late?’",
        "facts": ["Data-grounded assistant", f"Run: {run_id}"],
    }


# ============================================================
# GET /runs/latest-completed
# ============================================================

@app.get("/runs/latest-completed")
def get_latest_completed_run(
    db: Session = Depends(get_db),
):
    run = (
        db.query(OptimizationRun)
        .filter(OptimizationRun.status == "COMPLETED")
        .order_by(OptimizationRun.finished_at.desc())
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="No completed optimization run is available.",
        )

    return {
        "run_id": run.run_id,
        "status": run.status,
        "solver_status": run.solver_status,
        "objective_value": run.objective_value,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "summary": run.summary_kpis,
    }


# ============================================================
# GET /runs/latest
# ============================================================

@app.get("/runs/latest")
def get_latest_run(
    db: Session = Depends(get_db),
):
    """
    Return the most recently created optimization run.
    """

    run = (
        db.query(OptimizationRun)
        .order_by(
            OptimizationRun.created_at.desc(),
            OptimizationRun.id.desc(),
        )
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="No optimization run found.",
        )

    return {
        "run_id": run.run_id,
        "status": run.status,
        "solver_status": run.solver_status,
        "objective_value": run.objective_value,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


# ============================================================
# GET /runs/{run_id}
# ============================================================

@app.get("/runs/{run_id}")
def get_run_status(
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    Return the status of one optimization run.
    """

    run = (
        db.query(OptimizationRun)
        .filter(
            OptimizationRun.run_id == run_id
        )
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    return {
        "run_id": run.run_id,
        "status": run.status,
        "solver_status": run.solver_status,
        "objective_value": run.objective_value,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }

# ============================================================
# GET /procurement/{run_id}
# ============================================================

@app.get("/procurement/{run_id}")
def get_procurement_plan(
    run_id: str,
    db: Session = Depends(get_db),
):
    run = (
        db.query(OptimizationRun)
        .filter(OptimizationRun.run_id == run_id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    rows = (
        db.query(ProcurementPlan)
        .filter(ProcurementPlan.run_id == run_id)
        .order_by(ProcurementPlan.order_date, ProcurementPlan.material_id)
        .all()
    )
    return {
        "run_id": run_id,
        "count": len(rows),
        "rows": [
            {
                "material_id": r.material_id,
                "supplier_id": r.supplier_id,
                "order_date": r.order_date,
                "receipt_date": r.receipt_date,
                "order_qty": r.order_qty,
                "unit_cost_eur": r.unit_cost_eur,
                "purchase_cost_eur": r.purchase_cost_eur,
                "lead_time_days": r.lead_time_days,
                "min_order_qty": r.min_order_qty,
                "lot_size": r.lot_size,
                "reliability_pct": r.reliability_pct,
            }
            for r in rows
        ],
    }

# ============================================================
# GET /planning/{run_id}
# ============================================================

@app.get("/planning/{run_id}")
def get_planning(
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    Return the optimized production plan enriched
    with decision-support information.
    """

    # --------------------------------------------------------
    # CHECK RUN
    # --------------------------------------------------------

    run = get_run(
        db,
        run_id,
    )

    if run is None:

        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    # --------------------------------------------------------
    # LOAD PLANNING
    # --------------------------------------------------------

    rows = (
        db.query(
            PlanningResult
        )
        .filter(
            PlanningResult.run_id == run_id
        )
        .order_by(
            PlanningResult.machine_id.asc(),
            PlanningResult.start_min.asc(),
        )
        .all()
    )

    # --------------------------------------------------------
    # RISK ANALYSIS
    # --------------------------------------------------------

    risk_map = build_order_risk_map(
        db,
        run_id,
    )

    # --------------------------------------------------------
    # ORDERS MAP
    # --------------------------------------------------------

    orders_map = {
        order.order_id: order
        for order in db.query(Order).all()
    }

    # Include scenario orders created by the What-if module.
    scenario_orders = db.query(ScenarioOrder).all()
    for order in scenario_orders:
        orders_map[order.order_id] = order

    # --------------------------------------------------------
    # RESPONSE ROWS
    # --------------------------------------------------------

    planning_response = []

    for row in rows:

        risk_data = risk_map.get(
            row.order_id,
            {},
        )

        order = orders_map.get(
            row.order_id
        )

        planning_response.append(
            {
                # --------------------------------------------
                # BASIC PLANNING
                # --------------------------------------------
                "id": row.id,
                "order_id":
                    row.order_id,

                "product_id":
                    row.product_id,

                "operation_seq":
                    row.operation_seq,

                "operation_code":
                    row.operation_code,

                "machine_id":
                    row.machine_id,

                "start_min":
                    row.start_min,

                "end_min":
                    row.end_min,

                "start_datetime":
                    row.start_datetime,

                "end_datetime":
                    row.end_datetime,

                "processing_minutes":
                    row.processing_minutes,

                # --------------------------------------------
                # SETUP
                # --------------------------------------------

                "setup_from_product":
                    row.setup_from_product,

                "setup_minutes":
                    row.setup_minutes,

                # --------------------------------------------
                # ORDER PRIORITY
                # --------------------------------------------

                "priority_class":
                    (
                        order.priority_class
                        if order
                        else None
                    ),

                "priority_weight":
                    (
                        order.priority_weight
                        if order
                        else None
                    ),

                "urgent":
                    (
                        bool(
                            order.is_urgent
                        )
                        if order
                        else False
                    ),

                # --------------------------------------------
                # DATES
                # --------------------------------------------

                "due_date":
                    risk_data.get(
                        "due_datetime"
                    ),

                "expected_completion":
                    risk_data.get(
                        "expected_completion"
                    ),

                # --------------------------------------------
                # DELAY
                # --------------------------------------------

                "delay_hours":
                    risk_data.get(
                        "delay_hours",
                        0,
                    ),

                "delay_days":
                    risk_data.get(
                        "delay_days",
                        0,
                    ),

                # --------------------------------------------
                # RISK
                # --------------------------------------------

                "risk":
                    risk_data.get(
                        "risk",
                        "LOW",
                    ),

                "risk_reasons":
                    risk_data.get(
                        "reasons",
                        [],
                    ),

                # --------------------------------------------
                # MATERIAL RISK
                # --------------------------------------------

                "material_risks":
                    risk_data.get(
                        "material_risks",
                        [],
                    ),

                # --------------------------------------------
                # MACHINE RISK
                # --------------------------------------------

                "machine_risks":
                    risk_data.get(
                        "machine_risks",
                        [],
                    ),
            }
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    high_risk = sum(
        row["risk"] == "HIGH"
        for row in planning_response
    )

    medium_risk = sum(
        row["risk"] == "MEDIUM"
        for row in planning_response
    )

    low_risk = sum(
        row["risk"] == "LOW"
        for row in planning_response
    )

    total_setup = sum(
        float(
            row["setup_minutes"]
            or 0
        )
        for row in planning_response
    )

    total_processing = sum(
        float(
            row["processing_minutes"]
            or 0
        )
        for row in planning_response
    )

    late_orders = len({
        row["order_id"]
        for row in planning_response
        if float(
            row["delay_hours"]
            or 0
        ) > 0
    })

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {
        "run_id":
            run_id,

        "status":
            run.status,

        "solver_status":
            run.solver_status,

        "objective_value":
            run.objective_value,

        "count":
            len(planning_response),

        "summary": {
            "operations":
                len(planning_response),

            "total_setup_minutes":
                round(
                    total_setup,
                    2,
                ),

            "total_processing_minutes":
                round(
                    total_processing,
                    2,
                ),

            "late_orders":
                late_orders,

            "high_risk_operations":
                high_risk,

            "medium_risk_operations":
                medium_risk,

            "low_risk_operations":
                low_risk,
        },

        "planning":
            planning_response,
    }

    
# ============================================================
# GET /kpis/{run_id}
# ============================================================

@app.get(
    "/kpis/{run_id}"
)
def get_kpis(

    run_id: str,

    db: Session = Depends(get_db),
):

    run = get_run(
        db,
        run_id,
    )

    if run is None:

        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    machine_rows = (
        db.query(
            MachineKPI
        )
        .filter(
            MachineKPI.run_id
            == run_id
        )
        .all()
    )

    material_rows = (
        db.query(
            MaterialKPI
        )
        .filter(
            MaterialKPI.run_id
            == run_id
        )
        .all()
    )

    order_rows = (
        db.query(
            OrderKPI
        )
        .filter(
            OrderKPI.run_id
            == run_id
        )
        .all()
    )

    return {

        "run_id":
            run_id,

        "status":
            run.status,

        "objective_value":
            run.objective_value,

        "summary":
            run.summary_kpis,

        "machines": [

            {

                "machine_id":
                    row.machine_id,

                "available_working_min":
                    row.available_working_min,

                "busy_processing_min":
                    row.busy_processing_min,

                "setup_min":
                    row.setup_min,

                "setup_count":
                    row.setup_count,

                "idle_internal_min":
                    row.idle_internal_min,

                "utilization_pct":
                    row.utilization_pct,

                "occupancy_pct":
                    row.occupancy_pct,
            }

            for row in machine_rows
        ],

        "materials": [

            {

                "material_id":
                    row.material_id,

                "avg_inventory_qty":
                    row.avg_inventory_qty,

                "ending_inventory_qty":
                    row.ending_inventory_qty,

                "min_inventory_qty":
                    row.min_inventory_qty,

                "safety_stock_qty":
                    row.safety_stock_qty,

                "planned_replenishment_qty":
                    row.planned_replenishment_qty,
            }

            for row in material_rows
        ],

        "orders": [

            {

                "order_id":
                    row.order_id,

                "customer":
                    row.customer,

                "product_id":
                    row.product_id,

                "priority_class":
                    row.priority_class,

                "priority_weight":
                    row.priority_weight,

                "urgent":
                    row.urgent,

                "due_datetime":
                    row.due_datetime,

                "completion_datetime":
                    row.completion_datetime,

                "tardiness_min":
                    row.tardiness_min,

                "tardiness_hours":
                    row.tardiness_hours,

                "on_time":
                    row.on_time,
            }

            for row in order_rows
        ],
    }


# ============================================================
# POST /orders
# ============================================================

@app.post("/orders")
def create_order(

    request: OrderCreateRequest,

    db: Session = Depends(get_db),
):

    product = (
        db.query(
            Product
        )
        .filter(
            Product.product_id
            == request.product_id
        )
        .first()
    )

    if product is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Product "
                f"'{request.product_id}' "
                "not found."
            ),
        )

    order_id = (
        f"URG-"
        f"{uuid4().hex[:8].upper()}"
    )

    order = ScenarioOrder(

        order_id=
            order_id,

        customer=
            request.customer,

        product_id=
            request.product_id,

        order_qty=
            request.order_qty,

        requested_due_date=
            request.requested_due_date,

        priority_class=
            request.priority_class,

        is_urgent=
            request.is_urgent,
    )

    saved = save_order(
        db,
        order,
    )

    return {

        "message":
            "Scenario order added successfully.",

        "order": {

            "order_id":
                saved.order_id,

            "customer":
                saved.customer,

            "product_id":
                saved.product_id,

            "order_qty":
                saved.order_qty,

            "requested_due_date":
                saved.requested_due_date,

            "priority_class":
                saved.priority_class,

            "is_urgent":
                saved.is_urgent,
        },
    }


# ============================================================
# POST /machines/{machine_id}/breakdown
# ============================================================

@app.post(
    "/machines/{machine_id}/breakdown"
)
def create_breakdown(

    machine_id: str,

    request: BreakdownRequest,

    db: Session = Depends(get_db),
):

    machine = (
        db.query(
            Machine
        )
        .filter(
            Machine.machine_id
            == machine_id
        )
        .first()
    )

    if machine is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Machine "
                f"'{machine_id}' "
                "not found."
            ),
        )

    event_id = (
        f"SIM-"
        f"{uuid4().hex[:8].upper()}"
    )

    event = BreakdownEvent(

        event_id=
            event_id,

        machine_id=
            machine_id,

        start_datetime=
            request.start,

        end_datetime=
            request.end,

        reason=
            request.reason,

        simulated=
            True,
    )

    saved = save_breakdown(
        db,
        event,
    )

    return {

        "message":
            "Breakdown added successfully.",

        "event": {

            "event_id":
                saved.event_id,

            "machine_id":
                saved.machine_id,

            "start":
                saved.start_datetime,

            "end":
                saved.end_datetime,

            "reason":
                saved.reason,

            "simulated":
                saved.simulated,
        },
    }


# ============================================================
# POST /data/import
# ============================================================

@app.post(
    "/data/import"
)
async def import_dataset(

    dataset_key: str = Form(...),

    file: UploadFile = File(...),
):

    # --------------------------------------------------------
    # ALLOWED DATASETS
    # --------------------------------------------------------

    allowed_datasets = {

        "Suppliers",
        "Machines",
        "Products",
        "Materials",
        "Routing",
        "BOM",
        "Orders",
        "Machine_Events",
        "Machine_Calendar",
        "Setup_Matrix",
    }

    # --------------------------------------------------------
    # DATASET KEY
    # --------------------------------------------------------

    if dataset_key not in allowed_datasets:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported dataset key: "
                f"{dataset_key}"
            ),
        )

    # --------------------------------------------------------
    # FILE
    # --------------------------------------------------------

    if not file.filename:

        raise HTTPException(
            status_code=400,
            detail="No file selected.",
        )

    # --------------------------------------------------------
    # EXTENSION
    # --------------------------------------------------------

    extension = (
        Path(
            file.filename
        )
        .suffix
        .lower()
    )

    if extension not in {
        ".xlsx",
        ".xls",
        ".csv",
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "Only .xlsx, .xls "
                "and .csv files are supported."
            ),
        )

    # --------------------------------------------------------
    # UPLOAD DIRECTORY
    # --------------------------------------------------------

    upload_dir = BACKEND_DIR / "uploads"

    upload_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_filename = (
        f"{uuid4().hex}_"
        f"{Path(file.filename).name}"
    )

    destination = (
        upload_dir /
        safe_filename
    )

    try:

        # ----------------------------------------------------
        # SAVE FILE
        # ----------------------------------------------------

        with destination.open(
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                file.file,
                buffer,
            )

        print()
        print("=" * 70)
        print(
            f"DATASET UPLOAD: {dataset_key}"
        )
        print("=" * 70)

        print(
            f"Original file : "
            f"{file.filename}"
        )

        print(
            f"Saved file    : "
            f"{destination}"
        )

        # ----------------------------------------------------
        # QUALITY VALIDATION
        # ----------------------------------------------------

        from app.data_quality import (
            validate_single_dataset,
        )

        quality = (
            validate_single_dataset(
                dataset_key,
                str(destination),
            )
        )

        print(
            f"Quality valid : "
            f"{quality['valid']}"
        )

        print(
            f"Quality score : "
            f"{quality['quality_score']}"
        )

        # ----------------------------------------------------
        # REJECT INVALID
        # ----------------------------------------------------

        if not quality["valid"]:

            print(
                "[IMPORT] REJECTED"
            )

            return {

                "status":
                    "REJECTED",

                "message":
                    "Dataset validation failed.",

                "dataset_key":
                    dataset_key,

                "filename":
                    file.filename,

                "quality":
                    quality,
            }

        # ----------------------------------------------------
        # IMPORT INTO POSTGRESQL
        # ----------------------------------------------------

        from app.import_data import (
            import_single_dataset,
        )

        result = (
            import_single_dataset(
                dataset_key,
                str(destination),
            )
        )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        print(
            "[IMPORT] SUCCESS"
        )

        return {

            "status":
                "IMPORTED",

            "message":
                (
                    f"{dataset_key} "
                    "imported successfully."
                ),

            "dataset_key":
                dataset_key,

            "filename":
                file.filename,

            "rows_imported":
                result[
                    "rows_imported"
                ],

            "quality":
                quality,
        }

    except HTTPException:

        raise

    except Exception as exc:

        import traceback

        print()
        print("=" * 70)
        print("DATA IMPORT ERROR")
        print("=" * 70)

        traceback.print_exc()

        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                f"Dataset import failed: "
                f"{type(exc).__name__}: "
                f"{str(exc)}"
            ),
        )

    finally:

        await file.close()


# ============================================================
# GET /data/quality
# ============================================================

@app.get(
    "/data/quality"
)
def get_data_quality(
    db: Session = Depends(get_db),
):

    errors = []

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    orders = (
        db.query(
            Order
        ).all()
    )

    products = (
        db.query(
            Product
        ).all()
    )

    machines = (
        db.query(
            Machine
        ).all()
    )

    materials = (
        db.query(
            Material
        ).all()
    )

    routing = (
        db.query(
            Routing
        ).all()
    )

    bom = (
        db.query(
            BOM
        ).all()
    )

    setups = (
        db.query(
            SetupMatrix
        ).all()
    )

    suppliers = (
        db.query(
            Supplier
        ).all()
    )

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    counts = {

        "orders":
            len(orders),

        "products":
            len(products),

        "machines":
            len(machines),

        "materials":
            len(materials),

        "routing_rows":
            len(routing),

        "bom_rows":
            len(bom),

        "setup_rows":
            len(setups),

        "suppliers":
            len(suppliers),
    }

    # --------------------------------------------------------
    # PRODUCT -> ROUTING
    # --------------------------------------------------------

    product_ids = {
        row.product_id
        for row in products
    }

    routed_products = {
        row.product_id
        for row in routing
    }

    missing_routing = sorted(
        product_ids -
        routed_products
    )

    if missing_routing:

        errors.append(
            "Products without routing: "
            +
            ", ".join(
                missing_routing
            )
        )

    # --------------------------------------------------------
    # PRODUCT -> BOM
    # --------------------------------------------------------

    bom_products = {
        row.product_id
        for row in bom
    }

    missing_bom = sorted(
        product_ids -
        bom_products
    )

    # --------------------------------------------------------
    # BOM -> MATERIAL
    # --------------------------------------------------------

    material_ids = {
        row.material_id
        for row in materials
    }

    bom_material_ids = {
        row.material_id
        for row in bom
    }

    missing_materials = sorted(
        bom_material_ids -
        material_ids
    )

    if missing_materials:

        errors.append(
            "BOM references unknown materials: "
            +
            ", ".join(
                missing_materials
            )
        )

    # --------------------------------------------------------
    # MATERIAL -> SUPPLIER
    # --------------------------------------------------------

    supplier_ids = {
        row.supplier_id
        for row in suppliers
    }

    material_supplier_ids = {
        row.supplier_id
        for row in materials
    }

    missing_suppliers = sorted(
        material_supplier_ids -
        supplier_ids
    )

    if missing_suppliers:

        errors.append(
            "Materials reference unknown suppliers: "
            +
            ", ".join(
                missing_suppliers
            )
        )

    # --------------------------------------------------------
    # ORDER -> PRODUCT
    # --------------------------------------------------------

    order_product_ids = {
        row.product_id
        for row in orders
    }

    unknown_order_products = sorted(
        order_product_ids -
        product_ids
    )

    if unknown_order_products:

        errors.append(
            "Orders reference unknown products: "
            +
            ", ".join(
                unknown_order_products
            )
        )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    quality_score = max(
        0,
        100 -
        (
            len(errors) * 10
        ),
    )

    return {

        "status":
            (
                "PASS"
                if not errors
                else "WARNING"
            ),

        "quality_score":
            quality_score,

        "counts":
            counts,

        "products_without_bom":
            missing_bom,

        "errors":
            errors,
    }
# ============================================================
# GET /planning/{run_id}/operations/{operation_id}/explain
# ============================================================

@app.get("/planning/{run_id}/operations/{operation_id}/explain")
def explain_planning_operation(
    run_id: str,
    operation_id: int,
    db: Session = Depends(get_db),
):
    """Explain the selected machine assignment using evidence from the final plan."""
    run = (
        db.query(OptimizationRun)
        .filter(OptimizationRun.run_id == run_id)
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Optimization run not found.",
        )

    try:
        return PlanExplainer(db, run_id).explain_operation(operation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to explain planning operation: {type(exc).__name__}: {exc}",
        ) from exc


# ============================================================
# PUT /planning/{run_id}/operations/{operation_id}
# ============================================================

@app.put(
    "/planning/{run_id}/operations/{operation_id}",
    response_model=PlanningOperationUpdateResponse,
)
def update_planning_operation(
    run_id: str,
    operation_id: int,
    payload: PlanningOperationUpdate,
    db: Session = Depends(get_db),
):
    """
    Manually move an operation from the React Gantt.

    The operation is updated only when all validations pass.
    """

    # ========================================================
    # 1. CHECK RUN
    # ========================================================

    run = (
        db.query(OptimizationRun)
        .filter(
            OptimizationRun.run_id == run_id
        )
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Optimization run not found.",
        )

    # ========================================================
    # 2. CHECK OPERATION
    # ========================================================

    operation = (
        db.query(PlanningResult)
        .filter(
            PlanningResult.id == operation_id,
            PlanningResult.run_id == run_id,
        )
        .first()
    )

    if operation is None:
        raise HTTPException(
            status_code=404,
            detail="Planning operation not found.",
        )

    # ========================================================
    # 3. BASIC DATE VALIDATION
    # ========================================================

    validation_errors = []

    if payload.end_min <= payload.start_min:
        validation_errors.append(
            "End time must be greater than start time."
        )

    # ========================================================
    # 4. CHECK MACHINE
    # ========================================================

    machine = (
        db.query(Machine)
        .filter(
            Machine.machine_id == payload.machine_id
        )
        .first()
    )

    if machine is None:
        validation_errors.append(
            f"Machine '{payload.machine_id}' does not exist."
        )

    # ========================================================
    # 5. CHECK MACHINE OVERLAP
    # ========================================================

    if machine is not None:

        other_operations = (
            db.query(PlanningResult)
            .filter(
                PlanningResult.run_id == run_id,
                PlanningResult.machine_id == payload.machine_id,
                PlanningResult.id != operation_id,
            )
            .all()
        )

        for other in other_operations:

            overlap = (
                payload.start_min < other.end_min
                and payload.end_min > other.start_min
            )

            if overlap:

                validation_errors.append(
                    f"Machine '{payload.machine_id}' is already "
                    f"occupied by operation {other.id} "
                    f"between {other.start_min} and {other.end_min}."
                )

    # ========================================================
    # 6. CHECK MACHINE EVENTS / MAINTENANCE
    # ========================================================

    if machine is not None:

        events = (
            db.query(MachineEvent)
            .filter(
                MachineEvent.machine_id == payload.machine_id
            )
            .all()
        )

        for event in events:

            # MachineEvent stores date + time separately.
            # Convert event time to minutes since midnight.

            event_start_min = (
                event.start_time.hour * 60
                + event.start_time.minute
            )

            event_end_min = (
                event.end_time.hour * 60
                + event.end_time.minute
            )

            # Only compare events occurring on the same
            # planning day.
            event_date = event.event_date

            new_date = operation.start_datetime.date()

            if event_date == new_date:

                overlap = (
                    payload.start_min < event_end_min
                    and payload.end_min > event_start_min
                )

                if overlap:

                    validation_errors.append(
                        f"Machine '{payload.machine_id}' has "
                        f"a maintenance/event conflict on "
                        f"{event_date}."
                    )

    # ========================================================
    # 7. REJECT IF INVALID
    # ========================================================

    if validation_errors:

        db.rollback()

        return PlanningOperationUpdateResponse(
            valid=False,
            status="REJECTED",
            message="Operation move rejected.",
            operation_id=operation.id,
            machine_id=operation.machine_id,
            start_min=operation.start_min,
            end_min=operation.end_min,
            start_datetime=operation.start_datetime,
            end_datetime=operation.end_datetime,
            validation_errors=validation_errors,
        )

    # ========================================================
    # 8. CALCULATE NEW DATETIME
    # ========================================================

    duration_minutes = (
        operation.end_min
        - operation.start_min
    )

    # Keep the original calendar date.
    base_date = operation.start_datetime.date()

    from datetime import datetime, timedelta

    new_start_datetime = datetime.combine(
        base_date,
        datetime.min.time(),
    ) + timedelta(
        minutes=payload.start_min
    )

    new_end_datetime = (
        new_start_datetime
        + timedelta(
            minutes=payload.end_min
            - payload.start_min
        )
    )

    # ========================================================
    # 9. UPDATE DATABASE
    # ========================================================

    operation.machine_id = payload.machine_id

    operation.start_min = payload.start_min

    operation.end_min = payload.end_min

    operation.start_datetime = new_start_datetime

    operation.end_datetime = new_end_datetime

    db.commit()

    db.refresh(operation)

    # ========================================================
    # 10. SUCCESS
    # ========================================================

    return PlanningOperationUpdateResponse(
        valid=True,
        status="VALID",
        message="Operation successfully moved.",
        operation_id=operation.id,
        machine_id=operation.machine_id,
        start_min=operation.start_min,
        end_min=operation.end_min,
        start_datetime=operation.start_datetime,
        end_datetime=operation.end_datetime,
        validation_errors=[],
    )



@app.get("/shortage-prediction/{material_id}")
def shortage_prediction(
    material_id: str,
    calculation_date: date | None = None,
    horizon_days: int = 120,
    db: Session = Depends(get_db),
):
    """
    Prévision de rupture d'une matière.
    """

    try:

        prediction = predict_material_shortage(
            db=db,
            material_id=material_id,
            calculation_date=calculation_date,
            horizon_days=horizon_days,
        )

    except ValueError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    return {
        "material_id":
            prediction.material_id,

        "current_stock":
            prediction.current_stock,

        "daily_consumption":
            prediction.daily_consumption,

        "lead_time_days":
            prediction.lead_time_days,

        "shortage_date":
            (
                prediction.shortage_date.isoformat()
                if prediction.shortage_date
                else None
            ),

        "days_to_shortage":
            prediction.days_to_shortage,

        "shortage_qty":
            prediction.shortage_qty,

        "supplier_arrival_date":
            (
                prediction.supplier_arrival_date.isoformat()
                if prediction.supplier_arrival_date
                else None
            ),

        "affected_orders":
            prediction.affected_orders,

        "risk_level":
            prediction.risk_level,

        "supplier_can_arrive_before_shortage":
            prediction.supplier_can_arrive_before_shortage,
    }





