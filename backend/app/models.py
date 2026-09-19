from datetime import date, datetime, time
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 1. SUPPLIERS
# ============================================================

class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    supplier_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    material_scope: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    lead_time_typical_days: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    otd_target_pct: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )


# ============================================================
# 1B. MATERIAL-SUPPLIER SOURCING
# ============================================================

class MaterialSupplier(Base):
    __tablename__ = "material_suppliers"

    material_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("materials.material_id"), primary_key=True
    )
    supplier_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("suppliers.supplier_id"), primary_key=True
    )
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False)
    unit_cost_eur: Mapped[float] = mapped_column(Float, nullable=False)
    min_order_qty: Mapped[float] = mapped_column(Float, nullable=False)
    lot_size: Mapped[float] = mapped_column(Float, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_qty_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    order_cost_eur: Mapped[float] = mapped_column(Float, nullable=False)
    reliability_pct: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ============================================================
# 2. MACHINES
# ============================================================

class Machine(Base):
    __tablename__ = "machines"

    machine_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    machine_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    machine_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    capacity_units_hour: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    base_cycle_sec: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    availability_pct: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    shift_pattern: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    setup_skill: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )


# ============================================================
# 3. PRODUCTS
# ============================================================

class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    product_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    family: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    customer_mix: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    revision: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    standard_batch_qty: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    min_batch_qty: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    max_batch_qty: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    product_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    cycle_time_min_per_unit: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    touch_time_min_per_unit: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )


# ============================================================
# 4. MATERIALS
# ============================================================

class Material(Base):
    __tablename__ = "materials"

    material_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    material_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    material_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    uom: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    on_hand_qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    safety_stock_qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    lead_time_days: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    supplier_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("suppliers.supplier_id"),
        nullable=False,
        index=True,
    )

    lot_size: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    horizon_requirement_qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    avg_daily_requirement: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    coverage_days: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )


# ============================================================
# 5. ROUTING
# ============================================================

class Routing(Base):
    __tablename__ = "routing"

    product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("products.product_id"),
        primary_key=True,
    )

    operation_seq: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    operation_code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    operation_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    machine_group: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    compatible_machines: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    operation_time_min_per_unit: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    setup_family: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )


# ============================================================
# 6. BOM
# ============================================================

class BOM(Base):
    __tablename__ = "bom"

    product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("products.product_id"),
        primary_key=True,
    )

    material_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("materials.material_id"),
        primary_key=True,
    )

    qty_per_unit: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    scrap_factor_pct: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    consumption_operation_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10
    )


# ============================================================
# 7. ORDERS
# ============================================================

class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    customer: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("products.product_id"),
        nullable=False,
        index=True,
    )

    order_qty: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    order_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    requested_due_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    priority_class: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    priority_weight: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    order_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    is_urgent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )


# ============================================================
# 8. MACHINE EVENTS
# ============================================================

class MachineEvent(Base):
    __tablename__ = "machine_events"

    event_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    machine_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("machines.machine_id"),
        nullable=False,
        index=True,
    )

    event_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    start_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )

    end_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    duration_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    within_horizon: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )


# ============================================================
# 9. MACHINE CALENDAR
# ============================================================

class MachineCalendar(Base):
    __tablename__ = "machine_calendar"

    machine_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("machines.machine_id"),
        primary_key=True,
    )

    calendar_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
    )

    is_workday: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    scheduled_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    maintenance_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    planned_available_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    availability_factor: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )


# ============================================================
# 10. SETUP MATRIX
# ============================================================

class SetupMatrix(Base):
    __tablename__ = "setup_matrix"

    machine_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("machines.machine_id"),
        primary_key=True,
    )

    from_product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("products.product_id"),
        primary_key=True,
    )

    to_product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("products.product_id"),
        primary_key=True,
    )

    setup_time_min: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )


# ============================================================
# 11. MACHINE CAPACITY SNAPSHOT
# ============================================================

class MachineCapacity(Base):
    """
    Capacity master/snapshot imported from Machine capacite.xlsx.
    Kept separate from Machine because this file represents
    planning capacity assumptions for the optimization horizon.
    """
    __tablename__ = "machine_capacity"

    machine_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("machines.machine_id"),
        primary_key=True,
    )

    stage: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    scheduled_hours_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    planned_maintenance_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    planned_available_hours_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    nominal_capacity_units_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )


# ============================================================
# 12. STAGE CAPACITY SNAPSHOT
# ============================================================

class StageCapacity(Base):
    __tablename__ = "stage_capacity"

    stage: Mapped[str] = mapped_column(
        String(30),
        primary_key=True,
    )

    required_processing_hours_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    planned_available_hours_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    load_ratio_pct: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    capacity_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )


# ============================================================
# 13. EXAMPLE SETUP MATRICES (ASM / CRP)
# ============================================================

class SetupExample(Base):
    """
    Normalized representation of Setup_ASM_Ex.xlsx and
    Setup_CRP_Ex.xlsx.

    Both source files use a wide matrix. Storing them normalized
    makes PostgreSQL querying and future UI editing much easier.
    """
    __tablename__ = "setup_examples"

    setup_type: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
    )

    from_product_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    to_product_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    setup_time_min: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )


# ============================================================
# 11. OPTIMIZATION RUNS
# ============================================================

class OptimizationRun(Base):
    __tablename__ = "optimization_runs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    run_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    solver_status: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    max_time_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    num_workers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    random_seed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    weight_tardiness: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    weight_setup: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    weight_inventory: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    weight_idle: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    objective_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    summary_kpis: Mapped[dict | None] = mapped_column(
    JSON,
    nullable=True,
)

# ============================================================
# 12. SCENARIO ORDERS
# ============================================================

class ScenarioOrder(Base):
    __tablename__ = "scenario_orders"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    order_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    customer: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("products.product_id"),
        nullable=False,
    )

    order_qty: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    requested_due_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    priority_class: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    is_urgent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


# ============================================================
# 13. BREAKDOWN EVENTS SIMULES
# ============================================================

class BreakdownEvent(Base):
    __tablename__ = "breakdown_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    event_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    machine_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("machines.machine_id"),
        nullable=False,
        index=True,
    )

    start_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    end_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    simulated: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
# ============================================================
# 14. PLANNING RESULTS
# ============================================================

class PlanningResult(Base):
    __tablename__ = "planning_results"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("optimization_runs.run_id"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    product_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    operation_seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    operation_code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    machine_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    start_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    end_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    start_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    end_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    processing_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    setup_from_product: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    setup_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


# ============================================================
# 15. ORDER KPIs
# ============================================================

# ============================================================
# 14B. PROCUREMENT PLAN
# ============================================================

class ProcurementPlan(Base):
    __tablename__ = "procurement_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("optimization_runs.run_id"), nullable=False, index=True)
    material_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    order_qty: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost_eur: Mapped[float] = mapped_column(Float, nullable=False)
    purchase_cost_eur: Mapped[float] = mapped_column(Float, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    min_order_qty: Mapped[float] = mapped_column(Float, nullable=False)
    lot_size: Mapped[float] = mapped_column(Float, nullable=False)
    reliability_pct: Mapped[float] = mapped_column(Float, nullable=False)


class OrderKPI(Base):
    __tablename__ = "order_kpis"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("optimization_runs.run_id"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    customer: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    product_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    priority_class: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    priority_weight: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    urgent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    due_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    completion_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    tardiness_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    tardiness_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    on_time: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )


# ============================================================
# 16. MACHINE KPIs
# ============================================================

class MachineKPI(Base):
    __tablename__ = "machine_kpis"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("optimization_runs.run_id"),
        nullable=False,
        index=True,
    )

    machine_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    available_working_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    busy_processing_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    setup_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    setup_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    idle_internal_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    utilization_pct: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    occupancy_pct: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )


# ============================================================
# 17. MATERIAL KPIs
# ============================================================

class MaterialKPI(Base):
    __tablename__ = "material_kpis"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("optimization_runs.run_id"),
        nullable=False,
        index=True,
    )

    material_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    avg_inventory_qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    ending_inventory_qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    min_inventory_qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    safety_stock_qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    planned_replenishment_qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )    