from __future__ import annotations

"""Excel loader for production_optimizer_dataset_v2.xlsx."""

from datetime import datetime
from typing import Dict, List

import pandas as pd

from optimizer_cp_sat import (
    AvailabilityEvent,
    BomData,
    CalendarDay,
    MachineCalendarData,
    MachineData,
    MaterialData,
    ObjectiveWeights,
    OrderData,
    PlanningData,
    ProductData,
    RoutingData,
)


def parse_datetime(value) -> datetime:
    return pd.to_datetime(value).to_pydatetime()


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_excel(path: str) -> PlanningData:
    """Load the generated workbook into the optimizer data model."""
    xls = pd.ExcelFile(path)

    required_sheets = {
        "Machines",
        "Products",
        "Routing",
        "BOM",
        "Materials",
        "Orders",
        "Machine_Calendar",
        "Machine_Events",
        "Setup_Matrix",
    }
    missing = required_sheets.difference(set(xls.sheet_names))
    if missing:
        raise ValueError(
            f"Missing Excel sheets: {sorted(missing)}"
        )

    # -------------------------
    # Machines
    # -------------------------
    machines_df = pd.read_excel(xls, "Machines")
    machines: Dict[str, MachineData] = {}
    for row in machines_df.itertuples(index=False):
        machines[row.machine_id] = MachineData(
            machine_id=str(row.machine_id),
            stage=str(row.stage),
            capacity_units_hour=float(row.capacity_units_hour),
            base_cycle_sec=float(row.base_cycle_sec),
            availability_pct=float(row.availability_pct),
            setup_skill=str(row.setup_skill),
        )

    # -------------------------
    # Products
    # -------------------------
    products_df = pd.read_excel(xls, "Products")
    products = {
        str(row.product_id): ProductData(
            product_id=str(row.product_id)
        )
        for row in products_df.itertuples(index=False)
    }

    # -------------------------
    # Routing
    # -------------------------
    routing_df = pd.read_excel(xls, "Routing")
    routing: Dict[str, List[RoutingData]] = {}
    for row in routing_df.itertuples(index=False):
        compatible = tuple(
            machine.strip()
            for machine in str(row.compatible_machines).split("|")
            if machine.strip()
        )
        routing.setdefault(str(row.product_id), []).append(
            RoutingData(
                product_id=str(row.product_id),
                operation_seq=int(row.operation_seq),
                operation_code=str(row.operation_code),
                operation_time_min_per_unit=float(
                    row.operation_time_min_per_unit
                ),
                compatible_machines=compatible,
            )
        )

    # -------------------------
    # BOM
    # -------------------------
    bom_df = pd.read_excel(xls, "BOM")
    bom: Dict[str, List[BomData]] = {}
    for row in bom_df.itertuples(index=False):
        bom.setdefault(str(row.product_id), []).append(
            BomData(
                product_id=str(row.product_id),
                material_id=str(row.material_id),
                qty_per_unit=float(row.qty_per_unit),
                scrap_factor_pct=float(row.scrap_factor_pct),
            )
        )

    # -------------------------
    # Materials
    # -------------------------
    materials_df = pd.read_excel(xls, "Materials")
    materials: Dict[str, MaterialData] = {}
    for row in materials_df.itertuples(index=False):
        materials[str(row.material_id)] = MaterialData(
            material_id=str(row.material_id),
            on_hand_qty=float(row.on_hand_qty),
            safety_stock_qty=float(row.safety_stock_qty),
            lead_time_days=int(row.lead_time_days),
            lot_size=float(row.lot_size),
            supplier_id=str(row.supplier_id) if hasattr(row, "supplier_id") else None,
        )

    # -------------------------
    # Orders
    # -------------------------
    orders_df = pd.read_excel(xls, "Orders")
    orders: List[OrderData] = []
    for row in orders_df.itertuples(index=False):
        orders.append(
            OrderData(
                order_id=str(row.order_id),
                customer=str(row.customer),
                product_id=str(row.product_id),
                order_qty=int(row.order_qty),
                order_date=parse_datetime(row.order_date),
                requested_due_date=parse_datetime(row.requested_due_date),
                priority_class=str(row.priority_class).upper(),
                # Business priority is normalized in the optimizer: A=3,B=2,C=1.
                priority_weight={"A": 3, "B": 2, "C": 1}.get(
                    str(row.priority_class).upper(),
                    1,
                ),
                is_urgent=parse_bool(row.is_urgent),
            )
        )

    # -------------------------
    # Factory calendar
    # -------------------------
    calendar_df = pd.read_excel(xls, "Machine_Calendar")
    # The workbook stores one row per machine/day. Keep both a factory date
    # axis and the machine-specific capacity calendar.
    date_status = (
        calendar_df.groupby("calendar_date", as_index=False)["is_workday"]
        .any()
        .sort_values("calendar_date")
    )
    calendar_days = [
        CalendarDay(
            calendar_date=pd.to_datetime(row.calendar_date).date(),
            is_workday=parse_bool(row.is_workday),
        )
        for row in date_status.itertuples(index=False)
    ]

    machine_calendars: Dict[str, List[MachineCalendarData]] = {}
    for row in calendar_df.itertuples(index=False):
        machine_id = str(row.machine_id)
        machine_calendars.setdefault(machine_id, []).append(
            MachineCalendarData(
                machine_id=machine_id,
                calendar_date=pd.to_datetime(row.calendar_date).date(),
                is_workday=parse_bool(row.is_workday),
                scheduled_hours=float(row.scheduled_hours),
                maintenance_hours=float(row.maintenance_hours),
                planned_available_hours=float(row.planned_available_hours),
                availability_factor=float(row.availability_factor),
            )
        )

    # -------------------------
    # Machine events
    # -------------------------
    events_df = pd.read_excel(xls, "Machine_Events")
    events: List[AvailabilityEvent] = []
    for row in events_df.itertuples(index=False):
        event_date = pd.to_datetime(row.event_date).date()
        start_hour, start_minute = map(
            int,
            str(row.start_time).split(":")[:2],
        )
        end_hour, end_minute = map(
            int,
            str(row.end_time).split(":")[:2],
        )
        events.append(
            AvailabilityEvent(
                event_id=str(row.event_id),
                machine_id=str(row.machine_id),
                event_start=datetime.combine(
                    event_date,
                    datetime.min.time(),
                ).replace(hour=start_hour, minute=start_minute),
                event_end=datetime.combine(
                    event_date,
                    datetime.min.time(),
                ).replace(hour=end_hour, minute=end_minute),
                event_type=str(row.event_type),
                duration_h=float(row.duration_h),
            )
        )

    # -------------------------
    # Setup matrix
    # -------------------------
    setup_df = pd.read_excel(xls, "Setup_Matrix")
    setup_minutes = {}
    for row in setup_df.itertuples(index=False):
        setup_minutes[
            (
                str(row.machine_id),
                str(row.from_product_id),
                str(row.to_product_id),
            )
        ] = int(row.setup_time_min)

    return PlanningData(
        machines=machines,
        products=products,
        routing=routing,
        orders=orders,
        bom=bom,
        materials=materials,
        calendar_days=calendar_days,
        machine_calendars=machine_calendars,
        availability_events=events,
        setup_minutes=setup_minutes,
    )
