from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from optimizer_cp_sat import (
    AvailabilityEvent,
    BomData,
    CalendarDay,
    MachineCalendarData,
    MachineData,
    MaterialData,
    MaterialSupplierData,
    ObjectiveWeights,
    OrderData,
    PlanningData,
    ProductData,
    RoutingData,
    PRIORITY_WEIGHT,
)

from app.models import (
    BOM,
    BreakdownEvent,
    Machine,
    MachineCalendar,
    MachineEvent,
    Material,
    MaterialSupplier,
    Order,
    Product,
    Routing,
    ScenarioOrder,
    SetupMatrix,
)


def load_planning_data_from_db(
    db: Session,
) -> PlanningData:

    # ========================================================
    # MACHINES
    # ========================================================

    machines: Dict[str, MachineData] = {}

    for row in db.query(Machine).all():
        machines[row.machine_id] = MachineData(
            machine_id=row.machine_id,
            stage=row.stage,
            capacity_units_hour=row.capacity_units_hour,
            base_cycle_sec=row.base_cycle_sec,
            availability_pct=row.availability_pct,
            setup_skill=row.setup_skill,
        )

    # ========================================================
    # PRODUCTS
    # ========================================================

    products: Dict[str, ProductData] = {}

    for row in db.query(Product).all():
        products[row.product_id] = ProductData(
            product_id=row.product_id,
        )

    # ========================================================
    # ROUTING
    # ========================================================

    routing: Dict[str, List[RoutingData]] = {}

    for row in db.query(Routing).all():

        compatible_machines = tuple(
            machine.strip()
            for machine in row.compatible_machines.split("|")
            if machine.strip()
        )

        routing.setdefault(
            row.product_id,
            [],
        ).append(
            RoutingData(
                product_id=row.product_id,
                operation_seq=row.operation_seq,
                operation_code=row.operation_code,
                operation_time_min_per_unit=row.operation_time_min_per_unit,
                compatible_machines=compatible_machines,
            )
        )

    # ========================================================
    # BOM
    # ========================================================

    bom: Dict[str, List[BomData]] = {}

    for row in db.query(BOM).all():

        bom.setdefault(
            row.product_id,
            [],
        ).append(
            BomData(
                product_id=row.product_id,
                material_id=row.material_id,
                qty_per_unit=float(row.qty_per_unit),
                scrap_factor_pct=float(row.scrap_factor_pct),
                consumption_operation_seq=int(row.consumption_operation_seq),
            )
        )

    # ========================================================
    # MATERIALS
    # ========================================================

    materials: Dict[str, MaterialData] = {}

    for row in db.query(Material).all():
        materials[row.material_id] = MaterialData(
            material_id=row.material_id,
            on_hand_qty=row.on_hand_qty,
            safety_stock_qty=row.safety_stock_qty,
            lead_time_days=int(row.lead_time_days),
            lot_size=row.lot_size,
            supplier_id=row.supplier_id,
        )

    # ========================================================
    # MATERIAL-SUPPLIER SOURCING
    # ========================================================

    material_suppliers: Dict[str, List[MaterialSupplierData]] = {}

    for row in db.query(MaterialSupplier).all():
        material_suppliers.setdefault(row.material_id, []).append(
            MaterialSupplierData(
                material_id=str(row.material_id),
                supplier_id=str(row.supplier_id),
                priority_rank=int(row.priority_rank),
                is_preferred=bool(row.is_preferred),
                unit_cost_eur=float(row.unit_cost_eur),
                min_order_qty=float(row.min_order_qty),
                lot_size=float(row.lot_size),
                lead_time_days=int(row.lead_time_days),
                max_qty_per_day=float(row.max_qty_per_day),
                order_cost_eur=float(row.order_cost_eur),
                reliability_pct=float(row.reliability_pct),
                active=bool(row.active),
            )
        )

    for values in material_suppliers.values():
        values.sort(key=lambda x: (x.priority_rank, x.supplier_id))

    # ========================================================
    # BASE ORDERS
    # ========================================================

    orders: List[OrderData] = []

    for row in db.query(Order).all():

        orders.append(
            OrderData(
                order_id=row.order_id,
                customer=row.customer,
                product_id=row.product_id,
                order_qty=row.order_qty,
                order_date=row.order_date,
                requested_due_date=row.requested_due_date,
                priority_class=row.priority_class,
                priority_weight=PRIORITY_WEIGHT.get(
                    row.priority_class,
                    1,
                ),
                is_urgent=row.is_urgent,
            )
        )

    # ========================================================
    # SCENARIO / URGENT ORDERS
    # ========================================================

    for row in (
        db.query(ScenarioOrder)
        .order_by(ScenarioOrder.created_at)
        .all()
    ):

        # V1:
        # created_at is used as release date for a scenario order.
        orders.append(
            OrderData(
                order_id=row.order_id,
                customer=row.customer,
                product_id=row.product_id,
                order_qty=row.order_qty,
                order_date=row.created_at,
                requested_due_date=row.requested_due_date,
                priority_class=row.priority_class,
                priority_weight=PRIORITY_WEIGHT.get(
                    row.priority_class,
                    1,
                ),
                is_urgent=row.is_urgent,
            )
        )

    # ========================================================
    # CALENDAR
    # ========================================================

    calendar_rows = (
        db.query(MachineCalendar)
        .order_by(MachineCalendar.calendar_date)
        .all()
    )

    unique_dates = {}
    machine_calendars: Dict[str, List[MachineCalendarData]] = {}

    for row in calendar_rows:
        unique_dates[row.calendar_date] = (
            unique_dates.get(row.calendar_date, False)
            or bool(row.is_workday)
        )
        machine_calendars.setdefault(row.machine_id, []).append(
            MachineCalendarData(
                machine_id=row.machine_id,
                calendar_date=row.calendar_date,
                is_workday=bool(row.is_workday),
                scheduled_hours=float(row.scheduled_hours),
                maintenance_hours=float(row.maintenance_hours),
                planned_available_hours=float(row.planned_available_hours),
                availability_factor=float(row.availability_factor),
            )
        )

    calendar_days = [
        CalendarDay(
            calendar_date=d,
            is_workday=is_workday,
        )
        for d, is_workday in sorted(unique_dates.items())
    ]

    for values in machine_calendars.values():
        values.sort(key=lambda x: x.calendar_date)

    # ========================================================
    # MACHINE EVENTS
    # ========================================================

    availability_events: List[AvailabilityEvent] = []

    # Existing historical/planned events
    for row in db.query(MachineEvent).all():

        event_start = datetime.combine(
            row.event_date,
            row.start_time,
        )

        event_end = datetime.combine(
            row.event_date,
            row.end_time,
        )

        # Support a midnight crossing.
        if event_end <= event_start:
            event_end += timedelta(days=1)

        availability_events.append(
            AvailabilityEvent(
                event_id=row.event_id,
                machine_id=row.machine_id,
                event_start=event_start,
                event_end=event_end,
                event_type=row.event_type,
                duration_h=row.duration_h,
            )
        )

    # Simulated breakdowns
    for row in db.query(BreakdownEvent).all():

        availability_events.append(
            AvailabilityEvent(
                event_id=row.event_id,
                machine_id=row.machine_id,
                event_start=row.start_datetime,
                event_end=row.end_datetime,
                event_type="SIMULATED_BREAKDOWN",
                duration_h=(
                    row.end_datetime - row.start_datetime
                ).total_seconds() / 3600,
            )
        )

    # ========================================================
    # SETUP MATRIX
    # ========================================================

    setup_minutes = {}

    for row in db.query(SetupMatrix).all():

        setup_minutes[
            (
                row.machine_id,
                row.from_product_id,
                row.to_product_id,
            )
        ] = int(row.setup_time_min)

    # ========================================================
    # FINAL OBJECT
    # ========================================================

    return PlanningData(
        machines=machines,
        products=products,
        routing=routing,
        orders=orders,
        bom=bom,
        materials=materials,
        material_suppliers=material_suppliers,
        calendar_days=calendar_days,
        machine_calendars=machine_calendars,
        availability_events=availability_events,
        setup_minutes=setup_minutes,
    )