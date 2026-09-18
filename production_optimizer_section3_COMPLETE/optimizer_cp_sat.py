from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from math import ceil
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import math
from ortools.sat.python import cp_model


# =============================================================================
# BUSINESS CONSTANTS
# =============================================================================

PRIORITY_WEIGHT = {
    "A": 3,
    "B": 2,
    "C": 1,
}

# Preserve 2 decimal places for cables/components/material quantities.
MATERIAL_SCALE = 100


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass(frozen=True)
class MachineData:
    machine_id: str
    stage: str
    capacity_units_hour: float
    base_cycle_sec: float
    availability_pct: float
    setup_skill: str


@dataclass(frozen=True)
class ProductData:
    product_id: str


@dataclass(frozen=True)
class RoutingData:
    product_id: str
    operation_seq: int
    operation_code: str
    operation_time_min_per_unit: float
    compatible_machines: Tuple[str, ...]


@dataclass(frozen=True)
class OrderData:
    order_id: str
    customer: str
    product_id: str
    order_qty: int
    order_date: datetime
    requested_due_date: datetime
    priority_class: str
    priority_weight: int = 1
    is_urgent: bool = False


@dataclass(frozen=True)
class BomData:
    product_id: str
    material_id: str
    qty_per_unit: float
    scrap_factor_pct: float
    consumption_operation_seq: int = 10


@dataclass(frozen=True)
class MaterialData:
    material_id: str
    on_hand_qty: float
    safety_stock_qty: float
    lead_time_days: int
    lot_size: float
    supplier_id: Optional[str] = None




@dataclass(frozen=True)
class MaterialSupplierData:
    material_id: str
    supplier_id: str
    priority_rank: int
    is_preferred: bool
    unit_cost_eur: float
    min_order_qty: float
    lot_size: float
    lead_time_days: int
    max_qty_per_day: float
    order_cost_eur: float
    reliability_pct: float
    active: bool = True


@dataclass(frozen=True)
class CalendarDay:
    calendar_date: date
    is_workday: bool


@dataclass(frozen=True)
class MachineCalendarData:
    machine_id: str
    calendar_date: date
    is_workday: bool
    scheduled_hours: float
    maintenance_hours: float
    planned_available_hours: float
    availability_factor: float


@dataclass(frozen=True)
class AvailabilityEvent:
    event_id: str
    machine_id: str
    event_start: datetime
    event_end: datetime
    event_type: str
    duration_h: float


@dataclass(frozen=True)
class ObjectiveWeights:
    """
    Weights and normalization references for the weighted-sum objective.
    """

    tardiness: float = 0.50
    setup: float = 0.20
    inventory: float = 0.15
    idle: float = 0.15

    reference_tardiness_min: int = 1
    reference_setup_min: int = 1
    reference_inventory_scaled: int = 1
    reference_idle_min: int = 1

    integer_scale: int = 1_000_000

    def validate(self) -> None:
        weights = [
            self.tardiness,
            self.setup,
            self.inventory,
            self.idle,
        ]

        if any(w < 0 for w in weights):
            raise ValueError(
                "Objective weights must be non-negative."
            )

        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError(
                "Objective weights must sum to 1.0."
            )

        refs = [
            self.reference_tardiness_min,
            self.reference_setup_min,
            self.reference_inventory_scaled,
            self.reference_idle_min,
        ]

        if any(r <= 0 for r in refs):
            raise ValueError(
                "All normalization references must be > 0."
            )

        if self.integer_scale <= 0:
            raise ValueError(
                "integer_scale must be > 0."
            )


@dataclass(frozen=True)
class SupplierLeadTimeScenario:
    """
    Temporary supplier lead-time what-if scenario.

    Database values are NEVER modified.
    """

    supplier_id: str
    lead_time_delta_days: int = 0

    def validate(self) -> None:
        if not self.supplier_id:
            raise ValueError(
                "Supplier scenario requires a supplier_id."
            )

        if self.lead_time_delta_days < 0:
            raise ValueError(
                "lead_time_delta_days must be >= 0."
            )


@dataclass
class PlanningData:
    machines: Dict[str, MachineData]
    products: Dict[str, ProductData]
    routing: Dict[str, List[RoutingData]]
    orders: List[OrderData]
    bom: Dict[str, List[BomData]]
    materials: Dict[str, MaterialData]

    # Required fields before fields with defaults
    calendar_days: List[CalendarDay]

    material_suppliers: Dict[str, List[MaterialSupplierData]] = field(
        default_factory=dict
    )
    machine_calendars: Dict[str, List[MachineCalendarData]] = field(
        default_factory=dict
    )
    availability_events: List[AvailabilityEvent] = field(
        default_factory=list
    )
    setup_minutes: Dict[Tuple[str, str, str], int] = field(
        default_factory=dict
    )

@dataclass(frozen=True)
class TaskSpec:
    """
    One schedulable operation of one customer order.

    Task key:
        (order_id, operation_seq)
    """

    key: Tuple[str, int]
    order_id: str
    product_id: str
    operation_seq: int
    operation_code: str
    quantity: int
    routing: RoutingData


@dataclass
class MachineVars:
    assignment: Dict[
        Tuple[str, int],
        cp_model.IntVar,
    ] = field(default_factory=dict)

    interval: Dict[
        Tuple[str, int],
        cp_model.IntervalVar,
    ] = field(default_factory=dict)

    transition: Dict[
        Tuple[Tuple[str, int], Tuple[str, int]],
        cp_model.IntVar,
    ] = field(default_factory=dict)

    machine_used: Optional[cp_model.IntVar] = None
    machine_idle: Optional[cp_model.IntVar] = None


@dataclass
class OptimizationResult:
    status: str
    objective_value: float
    planning_rows: List[dict]
    machine_kpis: List[dict]
    material_kpis: List[dict]
    procurement_kpis: List[dict]
    order_kpis: List[dict]
    summary_kpis: dict


# =============================================================================
# WORKING-TIME CALENDAR
# =============================================================================

class WorkingCalendar:
    """
    Convert real datetimes into a continuous working-minute clock.

    Base shift:
        07:00 -> 23:00

    16 productive hours/day.
    """

    SHIFT_START = time(7, 0)
    SHIFT_END = time(23, 0)

    MINUTES_PER_WORKDAY = 16 * 60

    def __init__(
        self,
        days: Sequence[CalendarDay],
        *,
        overtime_minutes: int = 0,
    ) -> None:

        self.work_days = sorted(
            d.calendar_date
            for d in days
            if d.is_workday
        )

        self.overtime_minutes = max(0, int(overtime_minutes))
        self.workday_minutes = (
            self.MINUTES_PER_WORKDAY
            + self.overtime_minutes
        )

        if not self.work_days:
            raise ValueError(
                "Machine calendar contains no workday."
            )

        self.day_start_offset: Dict[date, int] = {}

        offset = 0

        for d in self.work_days:
            self.day_start_offset[d] = offset
            offset += self.workday_minutes

        self.total_working_minutes = offset

    def to_working_minute(
        self,
        dt: datetime,
        *,
        prefer_end_of_day: bool = False,
    ) -> int:
        """
        Convert a real datetime into compressed working minutes.
        """

        d = dt.date()

        if d not in self.day_start_offset:

            future = [
                x
                for x in self.work_days
                if x > d
            ]

            if future:
                return self.day_start_offset[future[0]]

            previous = [
                x
                for x in self.work_days
                if x < d
            ]

            if previous:
                return (
                    self.day_start_offset[previous[-1]]
                    + self.workday_minutes
                )

            return 0

        day_start = self.day_start_offset[d]

        if prefer_end_of_day:
            return day_start + self.workday_minutes

        minutes_since_midnight = dt.hour * 60 + dt.minute
        shift_start = self.SHIFT_START.hour * 60 + self.SHIFT_START.minute
        shift_end = self.SHIFT_END.hour * 60 + self.SHIFT_END.minute

        # Base shift: 07:00 -> 23:00.
        if shift_start < minutes_since_midnight < shift_end:
            return day_start + minutes_since_midnight - shift_start

        # Optional overtime continues after 23:00 and may cross midnight.
        if self.overtime_minutes > 0:
            if minutes_since_midnight >= shift_end:
                overtime_elapsed = minutes_since_midnight - shift_end
                if overtime_elapsed <= self.overtime_minutes:
                    return day_start + self.MINUTES_PER_WORKDAY + overtime_elapsed
            if minutes_since_midnight < shift_start:
                previous = [x for x in self.work_days if x < d]
                if previous:
                    prev_day = previous[-1]
                    prev_start = self.day_start_offset[prev_day]
                    overtime_elapsed = minutes_since_midnight
                    if overtime_elapsed <= self.overtime_minutes:
                        return prev_start + self.MINUTES_PER_WORKDAY + overtime_elapsed

        if minutes_since_midnight <= shift_start:
            return day_start

        return day_start + self.workday_minutes

    def from_working_minute(
        self,
        minute: int,
    ) -> datetime:
        """
        Convert compressed working minutes back to real datetime.
        """

        minute = max(
            0,
            min(
                int(minute),
                self.total_working_minutes,
            ),
        )

        if minute == self.total_working_minutes:
            return (
                datetime.combine(
                    self.work_days[-1],
                    self.SHIFT_START,
                )
                + timedelta(minutes=self.workday_minutes)
            )

        for d in self.work_days:

            day_start = self.day_start_offset[d]

            day_end = (
                day_start
                + self.workday_minutes
            )

            if day_start <= minute < day_end:

                delta = minute - day_start

                return (
                    datetime.combine(
                        d,
                        self.SHIFT_START,
                    )
                    + timedelta(
                        minutes=delta
                    )
                )

        return datetime.combine(
            self.work_days[-1],
            self.SHIFT_END,
        )

    def add_working_days(
        self,
        start_date: date,
        working_days: int,
    ) -> date:
        """
        Add working days to a date.

        If working_days = 0, returns the first working day
        on or after start_date.

        Example:
            Friday + 1 working day = Monday
        """

        working_days = max(
            0,
            int(working_days),
        )

        for work_day in self.work_days:

            if work_day < start_date:
                continue

            if working_days == 0:
                return work_day

            working_days -= 1

        return self.work_days[-1]


# =============================================================================
# CP-SAT OPTIMIZER
# =============================================================================

class ProductionCPSATOptimizer:
    """
    Build and solve the production scheduling model.
    """

    def __init__(
        self,
        data: PlanningData,
        objective: ObjectiveWeights,
        *,
        material_scale: int = MATERIAL_SCALE,
        supplier_lead_time_scenario: Optional[
            SupplierLeadTimeScenario
        ] = None,
        overtime_minutes: int = 0,
    ) -> None:

        objective.validate()

        if material_scale <= 0:
            raise ValueError(
                "material_scale must be > 0."
            )

        if supplier_lead_time_scenario is not None:
            supplier_lead_time_scenario.validate()

        self.data = data
        self.objective = objective
        self.material_scale = material_scale
        self._validate_machine_capacity_master()

        # Temporary what-if scenario.
        # Database is NEVER modified.
        self.supplier_lead_time_scenario = (
            supplier_lead_time_scenario
        )

        self.calendar = WorkingCalendar(
            data.calendar_days,
            overtime_minutes=overtime_minutes,
        )
        self.overtime_minutes = max(0, int(overtime_minutes))

        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # ---------------------------------------------------------------------
        # Tasks
        # ---------------------------------------------------------------------

        self.tasks = self._build_tasks()

        self.task_by_key = {
            task.key: task
            for task in self.tasks
        }

        self.order_by_id = {
            order.order_id: order
            for order in data.orders
        }

        # ---------------------------------------------------------------------
        # Scheduling variables
        # ---------------------------------------------------------------------

        self.start: Dict[
            str,
            cp_model.IntVar,
        ] = {}

        self.end: Dict[
            str,
            cp_model.IntVar,
        ] = {}

        self.tardiness: Dict[
            str,
            cp_model.IntVar,
        ] = {}

        self.assignment: Dict[
            Tuple[Tuple[str, int], str],
            cp_model.IntVar,
        ] = {}

        self.machine_vars: Dict[
            str,
            MachineVars,
        ] = {}

        self.inventory_end: Dict[Tuple[str, date], cp_model.IntVar] = {}
        self.shortage_end: Dict[Tuple[str, date], cp_model.IntVar] = {}

        # V2 integrated procurement decisions.
        self.purchase_qty: Dict[Tuple[str, str, date], cp_model.IntVar] = {}
        self.purchase_order: Dict[Tuple[str, str, date], cp_model.IntVar] = {}
        self.procurement_receipts: Dict[Tuple[str, date], List[cp_model.IntVar]] = {}
        self._purchase_meta: Dict[Tuple[str, str, date], MaterialSupplierData] = {}
        self._material_requirements_scaled = self._total_material_requirements_scaled()
        self._build_procurement_variables()

        self.max_operation_minutes = (
            self._max_operation_minutes()
        )

        self.max_setup_minutes = (
            self._max_setup_minutes()
        )

        self.big_m = (
            self.calendar.total_working_minutes
            + self.max_operation_minutes
            + self.max_setup_minutes
            + 10
        )

        # ---------------------------------------------------------------------
        # Build model
        # ---------------------------------------------------------------------

        self._build_model()

    # =========================================================================
    # SUPPLIER LEAD TIME SCENARIO
    # =========================================================================

    def _effective_lead_time(
        self,
        material: MaterialData,
    ) -> int:
        """
        Return effective supplier lead time.

        Base:
            material.lead_time_days

        Scenario:
            material.lead_time_days + delta

        Original MaterialData is never modified.
        """

        base_lead_time = max(
            0,
            int(material.lead_time_days),
        )

        scenario = (
            self.supplier_lead_time_scenario
        )

        if scenario is None:
            return base_lead_time

        if (
            material.supplier_id
            != scenario.supplier_id
        ):
            return base_lead_time

        return (
            base_lead_time
            + max(
                0,
                int(
                    scenario.lead_time_delta_days
                ),
            )
        )

    # =========================================================================
    # 3.2 - REPRESENTATION OF AN OPERATION
    # =========================================================================

    def _build_tasks(
        self,
    ) -> List[TaskSpec]:

        tasks: List[TaskSpec] = []

        for order in self.data.orders:

            if order.order_qty <= 0:
                raise ValueError(
                    f"Order {order.order_id} has invalid quantity."
                )

            if order.product_id not in self.data.products:
                raise ValueError(
                    f"Unknown product {order.product_id} "
                    f"for order {order.order_id}."
                )

            routes = sorted(
                self.data.routing.get(
                    order.product_id,
                    [],
                ),
                key=lambda r: r.operation_seq,
            )

            if not routes:
                raise ValueError(
                    f"No routing found for product "
                    f"{order.product_id}."
                )

            expected_seq = [
                r.operation_seq
                for r in routes
            ]

            if len(expected_seq) != len(
                set(expected_seq)
            ):
                raise ValueError(
                    f"Duplicate operation_seq for "
                    f"product {order.product_id}."
                )

            for route in routes:

                if route.operation_time_min_per_unit <= 0:
                    raise ValueError(
                        f"Invalid operation time for "
                        f"{order.product_id} / "
                        f"OP{route.operation_seq}."
                    )

                candidates = tuple(
                    route.compatible_machines
                )

                if not candidates:
                    raise ValueError(
                        f"No compatible machine for "
                        f"{order.product_id} / "
                        f"OP{route.operation_seq}."
                    )

                for machine_id in candidates:

                    if machine_id not in self.data.machines:
                        raise ValueError(
                            f"Unknown machine "
                            f"{machine_id} used by routing "
                            f"{order.product_id} / "
                            f"OP{route.operation_seq}."
                        )

                tasks.append(
                    TaskSpec(
                        key=(
                            order.order_id,
                            route.operation_seq,
                        ),
                        order_id=order.order_id,
                        product_id=order.product_id,
                        operation_seq=route.operation_seq,
                        operation_code=route.operation_code,
                        quantity=order.order_qty,
                        routing=route,
                    )
                )

        return tasks

    # =========================================================================
    # DATA PREPARATION
    # =========================================================================

    def _validate_machine_capacity_master(self) -> None:
        """Ensure capacity_units_hour and base_cycle_sec are coherent.

        They describe the same physical machine speed in different units. A
        tolerance is allowed for rounding, but a material mismatch is rejected
        instead of letting two contradictory capacity sources silently coexist.
        """
        for machine in self.data.machines.values():
            if machine.capacity_units_hour <= 0 or machine.base_cycle_sec <= 0:
                raise ValueError(
                    f"Machine {machine.machine_id}: capacity_units_hour and "
                    "base_cycle_sec must both be > 0."
                )
            implied_capacity = 3600.0 / float(machine.base_cycle_sec)
            relative_gap = abs(float(machine.capacity_units_hour) - implied_capacity) / implied_capacity
            if relative_gap > 0.05:
                raise ValueError(
                    f"Machine {machine.machine_id}: capacity_units_hour="
                    f"{machine.capacity_units_hour:.2f} conflicts with "
                    f"base_cycle_sec={machine.base_cycle_sec:.2f}. "
                    f"Expected about {implied_capacity:.2f} units/hour (gap {relative_gap:.1%})."
                )

    def _normalized_availability(
        self,
        machine: MachineData,
    ) -> float:
        """
        Normalize machine availability.

        Accepted:
            0.80
            80

        Both mean 80%.
        """

        value = float(
            machine.availability_pct
        )

        if value > 1.0:
            value /= 100.0

        return max(
            0.01,
            min(
                value,
                1.0,
            ),
        )

    def _machine_calendar_factor(self, machine_id: str) -> float:
        """Aggregate planned machine availability over the selected horizon.

        The optimizer uses a compressed working-time axis so long operations can
        continue into the next working day. Therefore Machine_Calendar is
        represented as an aggregate capacity factor, while exact maintenance
        and breakdown events remain explicit blocked intervals.
        """
        rows = self.data.machine_calendars.get(machine_id, [])
        if not rows:
            return self._normalized_availability(self.data.machines[machine_id])

        scheduled = 0.0
        available = 0.0
        for row in rows:
            if not row.is_workday:
                continue
            scheduled_min = max(0.0, float(row.scheduled_hours)) * 60.0
            scheduled += scheduled_min
            planned_min = max(0.0, float(row.planned_available_hours)) * 60.0
            if planned_min <= 0.0 and scheduled_min > 0.0:
                factor = float(row.availability_factor)
                if factor > 1.0:
                    factor /= 100.0
                factor = max(0.0, min(factor, 1.0))
                planned_min = max(0.0, scheduled_min - max(0.0, float(row.maintenance_hours)) * 60.0) * factor
            available += planned_min

        if scheduled <= 0.0:
            return self._normalized_availability(self.data.machines[machine_id])
        return max(0.05, min(1.0, available / scheduled))

    def _effective_duration(
        self,
        task: TaskSpec,
        machine_id: str,
    ) -> int:
        """Return processing time from the coherent machine/product capacity model.

        Routing provides the product-specific cycle time. Machine capacity and
        base_cycle_sec provide the physical lower bound. Availability is handled
        by the machine calendar, maintenance and breakdown constraints, not by
        inflating processing time a second time.
        """
        machine = self.data.machines[machine_id]
        if machine.capacity_units_hour <= 0:
            raise ValueError(f"Machine {machine_id} has invalid capacity_units_hour.")
        if machine.base_cycle_sec <= 0:
            raise ValueError(f"Machine {machine_id} has invalid base_cycle_sec.")

        routing_cycle = max(0.0, float(task.routing.operation_time_min_per_unit))
        capacity_cycle = 60.0 / float(machine.capacity_units_hour)
        base_cycle = float(machine.base_cycle_sec) / 60.0
        unit_cycle = max(routing_cycle, capacity_cycle, base_cycle)
        calendar_factor = self._machine_calendar_factor(machine_id)
        return max(1, int(ceil(task.quantity * unit_cycle / calendar_factor)))

    def _max_operation_minutes(self) -> int:

        if not self.tasks:
            return 1

        return max(
            self._effective_duration(
                task,
                machine_id,
            )
            for task in self.tasks
            for machine_id
            in task.routing.compatible_machines
        )

    def _max_setup_minutes(self) -> int:

        return max(
            self.data.setup_minutes.values(),
            default=0,
        )

    def _bom_consumption_scaled(
        self,
        order: OrderData,
    ) -> Dict[str, int]:
        """
        Calculate BOM consumption using MATERIAL_SCALE.
        """

        result: Dict[str, int] = {}

        for line in self.data.bom.get(
            order.product_id,
            [],
        ):

            if line.qty_per_unit < 0:
                raise ValueError(
                    f"Negative BOM quantity for "
                    f"{order.product_id} / "
                    f"{line.material_id}."
                )

            if line.scrap_factor_pct < 0:
                raise ValueError(
                    f"Negative scrap factor for "
                    f"{order.product_id} / "
                    f"{line.material_id}."
                )

            effective_qty = (
                line.qty_per_unit
                * (
                    1.0
                    + line.scrap_factor_pct / 100.0
                )
            )

            scaled = ceil(
                order.order_qty
                * effective_qty
                * self.material_scale
            )

            result[line.material_id] = (
                result.get(
                    line.material_id,
                    0,
                )
                + int(scaled)
            )

        return result

    # =========================================================================
    # REPLENISHMENT
    # =========================================================================

    def _total_material_requirements_scaled(self) -> Dict[str, int]:
        result = {mid: 0 for mid in self.data.materials}
        for order in self.data.orders:
            for mid, qty in self._bom_consumption_scaled(order).items():
                if mid not in self.data.materials:
                    raise ValueError(f"Material {mid} used in BOM but not found in material master.")
                result[mid] = result.get(mid, 0) + qty
        return result

    def _receipt_workday(self, order_date: date, lead_days: int) -> Optional[date]:
        target = order_date + timedelta(days=max(0, int(lead_days)))
        for d in self.calendar.work_days:
            if d >= target:
                return d
        return None

    def _build_procurement_variables(self) -> None:
        """Create CP-SAT purchase decisions: quantity, order day and supplier.

        A purchase is received after the selected supplier lead time. MOQ, lot
        size and daily supplier capacity are enforced directly in CP-SAT.
        """
        work_days = self.calendar.work_days
        if not work_days:
            raise ValueError("No working day available for procurement planning.")

        for mid, material in self.data.materials.items():
            options = [o for o in self.data.material_suppliers.get(mid, []) if o.active]
            if not options:
                # Backward-compatible fallback to the legacy single supplier.
                sid = material.supplier_id
                if sid:
                    options = [MaterialSupplierData(
                        material_id=mid, supplier_id=sid, priority_rank=1,
                        is_preferred=True, unit_cost_eur=1.0,
                        min_order_qty=max(1.0, material.lot_size),
                        lot_size=max(1.0, material.lot_size),
                        lead_time_days=max(0, material.lead_time_days),
                        max_qty_per_day=max(1.0, self._material_requirements_scaled.get(mid, 1) / self.material_scale),
                        order_cost_eur=0.0, reliability_pct=100.0, active=True
                    )]
            if not options:
                raise ValueError(f"No active supplier option for material {mid}.")

            demand = self._material_requirements_scaled.get(mid, 0)
            safety = int(ceil(max(0.0, material.safety_stock_qty) * self.material_scale))
            max_total_actual = max(1.0, demand / self.material_scale + safety / self.material_scale + max(1.0, material.lot_size) * 2)
            max_total_scaled = int(ceil(max_total_actual * self.material_scale))

            for option in options:
                lot_scaled = max(1, int(ceil(max(0.0, option.lot_size) * self.material_scale)))
                min_scaled = max(lot_scaled, int(ceil(max(0.0, option.min_order_qty) * self.material_scale)))
                max_day_scaled = max(lot_scaled, int(ceil(max(0.0, option.max_qty_per_day) * self.material_scale)))
                max_mult = max(1, max_day_scaled // lot_scaled + 1)
                receipt_candidates = []
                for d in work_days:
                    rd = self._receipt_workday(d, self._effective_supplier_lead_time(option))
                    if rd is None:
                        continue
                    key = (mid, option.supplier_id, d)
                    order_bool = self.model.new_bool_var(f"purchase_order__{mid}__{option.supplier_id}__{d.isoformat()}")
                    mult = self.model.new_int_var(0, max_mult, f"purchase_lot_mult__{mid}__{option.supplier_id}__{d.isoformat()}")
                    qty = self.model.new_int_var(0, max_day_scaled, f"purchase_qty__{mid}__{option.supplier_id}__{d.isoformat()}")
                    self.model.add(qty == lot_scaled * mult)
                    self.model.add(mult == 0).only_enforce_if(order_bool.Not())
                    self.model.add(mult >= max(1, math.ceil(min_scaled / lot_scaled))).only_enforce_if(order_bool)
                    self.model.add(qty <= max_day_scaled * order_bool)
                    self.purchase_qty[key] = qty
                    self.purchase_order[key] = order_bool
                    self._purchase_meta[key] = option
                    self.procurement_receipts.setdefault((mid, rd), []).append(qty)
                    receipt_candidates.append(key)

        # Supplier daily capacity shared by all materials.
        for sid in sorted({o.supplier_id for opts in self.data.material_suppliers.values() for o in opts if o.active}):
            for d in work_days:
                terms=[]; cap=None
                for key, qty in self.purchase_qty.items():
                    mid, supplier_id, od = key
                    if supplier_id != sid or od != d:
                        continue
                    terms.append(qty)
                    cap = self._purchase_meta[key].max_qty_per_day if cap is None else min(cap, self._purchase_meta[key].max_qty_per_day)
                if terms and cap is not None:
                    # Capacity is modeled in physical units. Material quantities may
                    # have different UOMs, so enforce the capacity per supplier only
                    # when all linked materials share the same UOM family.
                    # The dataset uses supplier scopes to keep this consistent.
                    self.model.add(sum(terms) <= int(ceil(cap * self.material_scale)))

    def _effective_supplier_lead_time(self, option: MaterialSupplierData) -> int:
        delta = 0
        scenario = self.supplier_lead_time_scenario
        if scenario and scenario.supplier_id == option.supplier_id:
            delta = max(0, int(scenario.lead_time_delta_days))
        return max(0, int(option.lead_time_days) + delta)

    def _procurement_cost_expr(self):
        terms=[]
        for key, qty in self.purchase_qty.items():
            option=self._purchase_meta[key]
            unit_cost_cents=int(round(max(0.0, option.unit_cost_eur) * 100))
            order_cost_cents=int(round(max(0.0, option.order_cost_eur) * 100))
            reliability_penalty=max(0, int(round(100.0-option.reliability_pct)))
            terms.append(unit_cost_cents * qty // self.material_scale if False else unit_cost_cents * qty)
            terms.append(order_cost_cents * self.purchase_order[key])
            terms.append(reliability_penalty * 10 * self.purchase_order[key])
        return sum(terms) if terms else 0

    def _procurement_kpis(self) -> List[dict]:
        result=[]
        for (mid, sid, d), qty in self.purchase_qty.items():
            q=self.solver.value(qty)
            if q <= 0:
                continue
            option=self._purchase_meta[(mid,sid,d)]
            rd=self._receipt_workday(d, self._effective_supplier_lead_time(option))
            result.append({
                "material_id": mid,
                "supplier_id": sid,
                "order_date": d.isoformat(),
                "receipt_date": rd.isoformat() if rd else None,
                "order_qty": q / self.material_scale,
                "unit_cost_eur": option.unit_cost_eur,
                "purchase_cost_eur": (q / self.material_scale) * option.unit_cost_eur,
                "lead_time_days": self._effective_supplier_lead_time(option),
                "min_order_qty": option.min_order_qty,
                "lot_size": option.lot_size,
                "reliability_pct": option.reliability_pct,
            })
        return sorted(result, key=lambda r:(r["order_date"],r["material_id"],r["supplier_id"]))

    def _build_replenishment_plan(
        self,
    ) -> Dict[str, List[Tuple[date, int]]]:
        """
        Create deterministic V1 receipts.

        Supplier lead-time scenario is applied temporarily.

        Database values are never modified.
        """

        total_requirement: Dict[str, int] = {
            material_id: 0
            for material_id in self.data.materials
        }

        for order in self.data.orders:

            consumption = (
                self._bom_consumption_scaled(
                    order
                )
            )

            for material_id, qty in (
                consumption.items()
            ):

                if material_id not in self.data.materials:
                    raise ValueError(
                        f"Material {material_id} "
                        f"used in BOM but not found "
                        f"in material master."
                    )

                total_requirement[material_id] = (
                    total_requirement.get(
                        material_id,
                        0,
                    )
                    + qty
                )

        first_workday = (
            self.calendar.work_days[0]
        )

        plan: Dict[
            str,
            List[Tuple[date, int]],
        ] = {
            material_id: []
            for material_id in self.data.materials
        }

        for material_id, material in (
            self.data.materials.items()
        ):

            on_hand = int(
                ceil(
                    max(
                        0.0,
                        material.on_hand_qty,
                    )
                    * self.material_scale
                )
            )

            safety = int(
                ceil(
                    max(
                        0.0,
                        material.safety_stock_qty,
                    )
                    * self.material_scale
                )
            )

            lot = max(
                1,
                int(
                    ceil(
                        max(
                            0.0,
                            material.lot_size,
                        )
                        * self.material_scale
                    )
                ),
            )

            shortage = max(
                0,
                total_requirement.get(
                    material_id,
                    0,
                )
                + safety
                - on_hand,
            )

            if shortage <= 0:
                continue

            number_of_lots = int(
                ceil(
                    shortage / lot
                )
            )

            effective_lead_time = (
                self._effective_lead_time(
                    material
                )
            )

            receipt_date = (
                self.calendar.add_working_days(
                    first_workday,
                    effective_lead_time,
                )
            )

            plan[material_id].append(
                (
                    receipt_date,
                    number_of_lots * lot,
                )
            )

        return plan

    # =========================================================================
    # MODEL CONSTRUCTION
    # =========================================================================

    def _build_model(self) -> None:

        self._create_time_variables()

        self._add_assignment_and_intervals()

        self._add_routing_precedence()

        self._add_machine_sequence_and_setups()

        self._add_material_constraints()

        self._add_objective()

        validation = self.model.validate()

        if validation:
            raise ValueError(
                f"Invalid CP-SAT model:\n{validation}"
            )

    # =========================================================================
    # 3.5 - TIME VARIABLES
    # =========================================================================

    def _create_time_variables(self) -> None:

        horizon = (
            self.calendar.total_working_minutes
        )

        for task in self.tasks:

            task_id = self.task_id(
                task.key
            )

            self.start[task_id] = (
                self.model.new_int_var(
                    0,
                    horizon,
                    f"start__{task_id}",
                )
            )

            self.end[task_id] = (
                self.model.new_int_var(
                    0,
                    horizon
                    + self.max_operation_minutes,
                    f"end__{task_id}",
                )
            )

            # Do not allow operations to finish
            # after the planning horizon.
            self.model.add(
                self.end[task_id]
                <= horizon
            )

        for order in self.data.orders:

            last_key = self.last_operation_key(
                order.order_id
            )

            completion = self.end[
                self.task_id(last_key)
            ]

            due = (
                self.calendar.to_working_minute(
                    order.requested_due_date,
                    prefer_end_of_day=True,
                )
            )

            tardy = (
                self.model.new_int_var(
                    0,
                    horizon
                    + self.max_operation_minutes,
                    f"tardiness__{order.order_id}",
                )
            )

            self.model.add_max_equality(
                tardy,
                [
                    completion - due,
                    0,
                ],
            )

            self.tardiness[
                order.order_id
            ] = tardy

    # =========================================================================
    # MACHINE ASSIGNMENT + OPTIONAL INTERVALS
    # =========================================================================

    def _add_assignment_and_intervals(
        self,
    ) -> None:

        machine_intervals: Dict[
            str,
            List[cp_model.IntervalVar],
        ] = {
            machine_id: []
            for machine_id in self.data.machines
        }

        for task in self.tasks:

            task_id = self.task_id(
                task.key
            )

            candidates = (
                task.routing.compatible_machines
            )

            assignment_literals: List[
                cp_model.IntVar
            ] = []

            for machine_id in candidates:

                x = self.model.new_bool_var(
                    f"assign__"
                    f"{task_id}__"
                    f"{machine_id}"
                )

                duration = (
                    self._effective_duration(
                        task,
                        machine_id,
                    )
                )

                interval = (
                    self.model.new_optional_interval_var(
                        self.start[task_id],
                        duration,
                        self.end[task_id],
                        x,
                        f"interval__"
                        f"{task_id}__"
                        f"{machine_id}",
                    )
                )

                assignment_literals.append(x)

                self.assignment[
                    (
                        task.key,
                        machine_id,
                    )
                ] = x

                machine_intervals[
                    machine_id
                ].append(interval)

                mv = self.machine_vars.setdefault(
                    machine_id,
                    MachineVars(),
                )

                mv.assignment[
                    task.key
                ] = x

                mv.interval[
                    task.key
                ] = interval

            self.model.add_exactly_one(
                assignment_literals
            )

            order = self.order_by_id[
                task.order_id
            ]

            release_dt = (
                order.order_date.replace(
                    hour=7,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            )

            release = (
                self.calendar.to_working_minute(
                    release_dt
                )
            )

            self.model.add(
                self.start[task_id]
                >= release
            )

        for machine_id, intervals in (
            machine_intervals.items()
        ):

            if intervals:
                self.model.add_no_overlap(
                    intervals
                )

    # =========================================================================
    # ROUTING PRECEDENCE
    # =========================================================================

    def _add_routing_precedence(
        self,
    ) -> None:

        for order in self.data.orders:

            route = sorted(
                self.data.routing[
                    order.product_id
                ],
                key=lambda r: r.operation_seq,
            )

            for previous, next_operation in zip(
                route,
                route[1:],
            ):

                previous_task = self.task_id(
                    (
                        order.order_id,
                        previous.operation_seq,
                    )
                )

                next_task = self.task_id(
                    (
                        order.order_id,
                        next_operation.operation_seq,
                    )
                )

                self.model.add(
                    self.start[next_task]
                    >= self.end[previous_task]
                )

    # =========================================================================
    # SEQUENCE-DEPENDENT SETUPS
    # =========================================================================

    def _add_machine_sequence_and_setups(
        self,
    ) -> None:

        tasks_by_machine: Dict[
            str,
            List[TaskSpec],
        ] = {
            machine_id: []
            for machine_id in self.data.machines
        }

        for task in self.tasks:

            for machine_id in (
                task.routing.compatible_machines
            ):

                tasks_by_machine[
                    machine_id
                ].append(task)

        for machine_id, tasks in (
            tasks_by_machine.items()
        ):

            if not tasks:
                continue

            mv = self.machine_vars[
                machine_id
            ]

            used = self.model.new_bool_var(
                f"machine_used__{machine_id}"
            )

            mv.machine_used = used

            self.model.add_max_equality(
                used,
                [
                    mv.assignment[
                        t.key
                    ]
                    for t in tasks
                ],
            )

            # -----------------------------------------------------------------
            # Maintenance / breakdown intervals
            # -----------------------------------------------------------------

            blocked_intervals: List[
                cp_model.IntervalVar
            ] = []

            for event in self.data.availability_events:

                if event.machine_id != machine_id:
                    continue

                event_start = (
                    self.calendar.to_working_minute(
                        event.event_start
                    )
                )

                event_end = (
                    self.calendar.to_working_minute(
                        event.event_end
                    )
                )

                duration = max(
                    0,
                    event_end - event_start,
                )

                if duration <= 0:
                    continue

                blocked = (
                    self.model.new_fixed_size_interval_var(
                        event_start,
                        duration,
                        f"blocked__"
                        f"{event.event_id}__"
                        f"{machine_id}",
                    )
                )

                blocked_intervals.append(
                    blocked
                )

            if blocked_intervals:

                self.model.add_no_overlap(
                    blocked_intervals
                    + list(mv.interval.values())
                )

            # -----------------------------------------------------------------
            # Circuit
            # -----------------------------------------------------------------

            node_of = {
                task.key: index + 1
                for index, task in enumerate(tasks)
            }

            arcs = [
                (
                    0,
                    0,
                    used.Not(),
                )
            ]

            start_arcs: List[
                cp_model.IntVar
            ] = []

            end_arcs: List[
                cp_model.IntVar
            ] = []

            for task in tasks:

                node = node_of[
                    task.key
                ]

                assigned = mv.assignment[
                    task.key
                ]

                # Unassigned task -> self-loop.
                arcs.append(
                    (
                        node,
                        node,
                        assigned.Not(),
                    )
                )

                first_on_machine = (
                    self.model.new_bool_var(
                        f"first__"
                        f"{machine_id}__"
                        f"{node}"
                    )
                )

                last_on_machine = (
                    self.model.new_bool_var(
                        f"last__"
                        f"{machine_id}__"
                        f"{node}"
                    )
                )

                self.model.add(
                    first_on_machine
                    <= assigned
                )

                self.model.add(
                    last_on_machine
                    <= assigned
                )

                start_arcs.append(
                    first_on_machine
                )

                end_arcs.append(
                    last_on_machine
                )

                arcs.append(
                    (
                        0,
                        node,
                        first_on_machine,
                    )
                )

                arcs.append(
                    (
                        node,
                        0,
                        last_on_machine,
                    )
                )

            self.model.add(
                sum(start_arcs)
                == used
            )

            self.model.add(
                sum(end_arcs)
                == used
            )

            # -----------------------------------------------------------------
            # Transition arcs
            # -----------------------------------------------------------------

            for previous in tasks:

                for following in tasks:

                    if previous.key == following.key:
                        continue

                    a = node_of[
                        previous.key
                    ]

                    b = node_of[
                        following.key
                    ]

                    next_arc = (
                        self.model.new_bool_var(
                            f"next__"
                            f"{machine_id}__"
                            f"{a}__"
                            f"{b}"
                        )
                    )

                    previous_assigned = (
                        mv.assignment[
                            previous.key
                        ]
                    )

                    following_assigned = (
                        mv.assignment[
                            following.key
                        ]
                    )

                    self.model.add(
                        next_arc
                        <= previous_assigned
                    )

                    self.model.add(
                        next_arc
                        <= following_assigned
                    )

                    arcs.append(
                        (
                            a,
                            b,
                            next_arc,
                        )
                    )

                    mv.transition[
                        (
                            previous.key,
                            following.key,
                        )
                    ] = next_arc

                    setup = (
                        self.get_setup_minutes(
                            machine_id,
                            previous.product_id,
                            following.product_id,
                        )
                    )

                    self.model.add(
                        self.start[
                            self.task_id(
                                following.key
                            )
                        ]
                        >= self.end[
                            self.task_id(
                                previous.key
                            )
                        ]
                        + setup
                        - self.big_m
                        * (
                            1 - next_arc
                        )
                    )

            self.model.add_circuit(
                arcs
            )

            # -----------------------------------------------------------------
            # Internal machine idle
            # -----------------------------------------------------------------

            first_time = (
                self.model.new_int_var(
                    0,
                    self.calendar.total_working_minutes,
                    f"machine_first__"
                    f"{machine_id}",
                )
            )

            last_time = (
                self.model.new_int_var(
                    0,
                    self.calendar.total_working_minutes,
                    f"machine_last__"
                    f"{machine_id}",
                )
            )

            first_candidates = []
            last_candidates = []

            for task in tasks:

                assigned = mv.assignment[
                    task.key
                ]

                task_id = self.task_id(
                    task.key
                )

                first_candidate = (
                    self.model.new_int_var(
                        0,
                        self.big_m,
                        f"first_candidate__"
                        f"{machine_id}__"
                        f"{task_id}",
                    )
                )

                self.model.add(
                    first_candidate
                    == self.start[task_id]
                ).only_enforce_if(
                    assigned
                )

                self.model.add(
                    first_candidate
                    == self.big_m
                ).only_enforce_if(
                    assigned.Not()
                )

                first_candidates.append(
                    first_candidate
                )

                last_candidate = (
                    self.model.new_int_var(
                        0,
                        self.big_m,
                        f"last_candidate__"
                        f"{machine_id}__"
                        f"{task_id}",
                    )
                )

                self.model.add(
                    last_candidate
                    == self.end[task_id]
                ).only_enforce_if(
                    assigned
                )

                self.model.add(
                    last_candidate
                    == 0
                ).only_enforce_if(
                    assigned.Not()
                )

                last_candidates.append(
                    last_candidate
                )

            self.model.add_min_equality(
                first_time,
                first_candidates,
            )

            self.model.add_max_equality(
                last_time,
                last_candidates,
            )

            busy_terms = []

            for task in tasks:

                duration = (
                    self._effective_duration(
                        task,
                        machine_id,
                    )
                )

                busy_terms.append(
                    duration
                    * mv.assignment[
                        task.key
                    ]
                )

            setup_terms = []

            for (
                (
                    a_key,
                    b_key,
                ),
                transition,
            ) in mv.transition.items():

                a_task = self.task_by_key[
                    a_key
                ]

                b_task = self.task_by_key[
                    b_key
                ]

                setup = (
                    self.get_setup_minutes(
                        machine_id,
                        a_task.product_id,
                        b_task.product_id,
                    )
                )

                setup_terms.append(
                    setup * transition
                )

            busy_expr = (
                sum(busy_terms)
                if busy_terms
                else 0
            )

            setup_expr = (
                sum(setup_terms)
                if setup_terms
                else 0
            )

            idle = (
                self.model.new_int_var(
                    0,
                    self.big_m
                    * max(
                        1,
                        len(tasks),
                    ),
                    f"machine_idle__"
                    f"{machine_id}",
                )
            )

            self.model.add(
                idle
                == (
                    last_time
                    - first_time
                    - busy_expr
                    - setup_expr
                )
            )

            mv.machine_idle = idle

    # =========================================================================
    # MATERIAL CONSTRAINTS
    # =========================================================================

    def _add_material_constraints(self) -> None:
        """Material balance with operation-level consumption and optimized receipts."""
        work_days = self.calendar.work_days
        order_material_lines = {
            order.order_id: self.data.bom.get(order.product_id, [])
            for order in self.data.orders
        }
        for material_id, material in self.data.materials.items():
            on_hand = int(ceil(max(0.0, material.on_hand_qty) * self.material_scale))
            safety = int(ceil(max(0.0, material.safety_stock_qty) * self.material_scale))
            max_possible = on_hand + self._material_requirements_scaled.get(material_id, 0) + safety
            for d in work_days:
                day_end = self.calendar.day_start_offset[d] + self.calendar.MINUTES_PER_WORKDAY
                consumed_terms=[]
                for order in self.data.orders:
                    for line in order_material_lines[order.order_id]:
                        if line.material_id != material_id:
                            continue
                        required = int(ceil(order.order_qty * line.qty_per_unit * (1.0 + line.scrap_factor_pct/100.0) * self.material_scale))
                        task_key=(order.order_id, int(line.consumption_operation_seq))
                        if task_key not in self.task_by_key:
                            raise ValueError(f"BOM consumption operation {line.consumption_operation_seq} not found for {order.product_id} / {material_id}.")
                        started=self.model.new_bool_var(f"material_started__{order.order_id}__{material_id}__{d.isoformat()}")
                        first_start=self.start[self.task_id(task_key)]
                        self.model.add(first_start <= day_end).only_enforce_if(started)
                        self.model.add(first_start >= day_end + 1).only_enforce_if(started.Not())
                        consumed_terms.append(required * started)
                receipts=sum(self.procurement_receipts.get((material_id,d), []))
                cumulative_prior=[]
                for rd in work_days:
                    if rd > d: break
                    cumulative_prior.extend(self.procurement_receipts.get((material_id,rd), []))
                cumulative_receipts=sum(cumulative_prior)
                inventory=self.model.new_int_var(0,max(1,max_possible),f"inventory__{material_id}__{d.isoformat()}")
                shortage=self.model.new_int_var(0,max(1,self._material_requirements_scaled.get(material_id,0)),f"shortage__{material_id}__{d.isoformat()}")
                self.inventory_end[(material_id,d)]=inventory
                self.shortage_end[(material_id,d)]=shortage
                consumed=sum(consumed_terms) if consumed_terms else 0
                self.model.add(inventory - shortage == on_hand + cumulative_receipts - consumed)
                self.model.add(inventory >= safety)

    # =========================================================================
    # MULTI-OBJECTIVE
    # =========================================================================

    def _add_objective(
        self,
    ) -> None:
        """
        Weighted normalized objective.

        Z =
            wt * tardiness/reference
          + ws * setup/reference
          + wi * inventory/reference
          + widle * idle/reference
        """

        scale = (
            self.objective.integer_scale
        )

        coeff_t = (
            self._normalized_coefficient(
                self.objective.tardiness,
                self.objective.reference_tardiness_min,
                scale,
            )
        )

        coeff_s = (
            self._normalized_coefficient(
                self.objective.setup,
                self.objective.reference_setup_min,
                scale,
            )
        )

        coeff_i = (
            self._normalized_coefficient(
                self.objective.inventory,
                self.objective.reference_inventory_scaled,
                scale,
            )
        )

        coeff_idle = (
            self._normalized_coefficient(
                self.objective.idle,
                self.objective.reference_idle_min,
                scale,
            )
        )

        weighted_tardiness = sum(
            (
                self.priority_weight(order)
                * self.tardiness[
                    order.order_id
                ]
            )
            for order in self.data.orders
        )

        weighted_setup = sum(
            self.setup_cost_terms()
        )

        total_inventory = sum(
            self.inventory_end.values()
        )

        total_idle = sum(
            mv.machine_idle
            for mv in self.machine_vars.values()
            if mv.machine_idle is not None
        )

        total_shortage = sum(self.shortage_end.values())
        procurement_cost = self._procurement_cost_expr()
        # Procurement is a secondary economic criterion; shortage remains a
        # very strong service constraint. Cost is normalized to keep scales sane.
        procurement_reference = max(1, int(self._material_requirements_scaled.get(next(iter(self.data.materials), ""), 1)))
        procurement_coeff = max(1, int(round(0.05 * scale / max(1, procurement_reference))))
        shortage_coeff = max(100, int(round(2.0 * scale / self.material_scale)))

        objective_expr = (
            coeff_t
            * weighted_tardiness
            + coeff_s
            * weighted_setup
            + coeff_i
            * total_inventory
            + coeff_idle
            * total_idle
            + procurement_coeff * procurement_cost
            + shortage_coeff * total_shortage
        )

        # Keep the expression so solve() can temporarily remove the objective
        # and run a pure feasibility pass when CP-SAT cannot find a solution
        # quickly enough with the full weighted objective.
        self.objective_expr = objective_expr

        self.model.minimize(
            objective_expr
        )

    @staticmethod
    def _normalized_coefficient(
        weight: float,
        reference: int,
        scale: int,
    ) -> int:

        if weight <= 0:
            return 0

        return max(
            1,
            int(
                round(
                    weight
                    * scale
                    / reference
                )
            ),
        )

    def setup_cost_terms(
        self,
    ) -> Iterable[cp_model.LinearExpr]:

        for machine_id, mv in (
            self.machine_vars.items()
        ):

            for (
                (
                    a_key,
                    b_key,
                ),
                transition,
            ) in mv.transition.items():

                a = self.task_by_key[
                    a_key
                ]

                b = self.task_by_key[
                    b_key
                ]

                yield (
                    self.get_setup_minutes(
                        machine_id,
                        a.product_id,
                        b.product_id,
                    )
                    * transition
                )

    # =========================================================================
    # SOLVE
    # =========================================================================

    def solve(
        self,
        *,
        max_time_seconds: float = 60.0,
        num_workers: int = 8,
        random_seed: int = 42,
        log_search_progress: bool = False,
    ) -> OptimizationResult:
        """
        Solve the production planning model with a robust two-phase strategy.

        Phase 1
        --------
        Solve the complete optimization model for most of the available time.

        Phase 2
        --------
        If CP-SAT returns UNKNOWN (typically because the time limit expires
        before a feasible solution is found), remove the objective and solve
        the exact same constraints as a pure feasibility problem.

        This does NOT remove production, routing, machine, calendar, setup,
        inventory, BOM or procurement constraints. It only prevents the
        weighted objective from blocking the first feasible schedule.
        """

        total_time = max(
            1.0,
            float(max_time_seconds),
        )

        # Give the full optimization model most of the time.
        optimization_time = max(
            1.0,
            total_time * 0.70,
        )
        feasibility_time = max(
            1.0,
            total_time - optimization_time,
        )

        # Keep CP-SAT configuration explicit and reproducible.
        self.solver.parameters.num_workers = max(
            1,
            int(num_workers),
        )
        self.solver.parameters.random_seed = int(
            random_seed
        )
        self.solver.parameters.log_search_progress = bool(
            log_search_progress
        )
        self.solver.parameters.cp_model_presolve = True
        self.solver.parameters.symmetry_level = 2

        print(
            f"[CP-SAT] Optimization time : {optimization_time:.1f} seconds"
        )
        print(
            f"[CP-SAT] Feasibility time  : {feasibility_time:.1f} seconds"
        )
        print(
            f"[CP-SAT] Workers          : {max(1, int(num_workers))}"
        )
        print(
            f"[CP-SAT] Random seed      : {int(random_seed)}"
        )

        # ------------------------------------------------------------------
        # PHASE 1 - Full optimization
        # ------------------------------------------------------------------
        self.solver.parameters.max_time_in_seconds = optimization_time

        status = self.solver.solve(
            self.model
        )

        status_name = self.solver.status_name(
            status
        )

        print(
            f"[CP-SAT] Phase 1 status  : {status_name}"
        )
        print(
            f"[CP-SAT] Phase 1 wall    : {self.solver.wall_time:.2f}s"
        )

        if status in (
            cp_model.OPTIMAL,
            cp_model.FEASIBLE,
        ):
            result = self._extract_result(
                status_name
            )

            # Add diagnostic information without changing the existing KPI
            # structure expected by the API/frontend.
            result.summary_kpis[
                "optimization_mode"
            ] = "FULL_OPTIMIZATION"
            result.summary_kpis[
                "objective_optimized"
            ] = True

            return result

        # ------------------------------------------------------------------
        # PHASE 2 - Feasibility fallback
        # ------------------------------------------------------------------
        # UNKNOWN means CP-SAT did not prove infeasibility and did not return
        # a usable FEASIBLE/OPTIMAL solution within the first time slice.
        # Do not label it INFEASIBLE. Instead, give the same constraints a
        # second chance without the expensive objective search.
        print(
            "[CP-SAT] Phase 1 did not return a usable solution."
        )
        print(
            "[CP-SAT] Starting feasibility fallback..."
        )

        try:
            self.model.clear_objective()
        except AttributeError:
            # Compatibility fallback for older OR-Tools versions.
            # Rebuild the model objective-free is not available here, so
            # report the original failure instead of silently changing the
            # mathematical model.
            print(
                "[CP-SAT] clear_objective() is unavailable in this OR-Tools version."
            )
            return OptimizationResult(
                status=status_name,
                objective_value=(
                    self.solver.objective_value
                ),
                planning_rows=[],
                machine_kpis=[],
                material_kpis=[],
                procurement_kpis=[],
                order_kpis=[],
                summary_kpis={
                    "status": status_name,
                    "optimization_mode": "FAILED_NO_FALLBACK",
                    "objective_optimized": False,
                    "wall_time_seconds": (
                        self.solver.wall_time
                    ),
                },
            )

        self.solver.parameters.max_time_in_seconds = feasibility_time

        feasibility_status = self.solver.solve(
            self.model
        )

        feasibility_status_name = self.solver.status_name(
            feasibility_status
        )

        print(
            f"[CP-SAT] Phase 2 status  : {feasibility_status_name}"
        )
        print(
            f"[CP-SAT] Phase 2 wall    : {self.solver.wall_time:.2f}s"
        )

        if feasibility_status in (
            cp_model.OPTIMAL,
            cp_model.FEASIBLE,
        ):
            result = self._extract_result(
                feasibility_status_name
            )

            # The schedule satisfies all hard constraints but was not selected
            # by minimizing the weighted business objective.
            result.summary_kpis[
                "optimization_mode"
            ] = "FEASIBILITY_FALLBACK"
            result.summary_kpis[
                "objective_optimized"
            ] = False
            result.summary_kpis[
                "phase_1_status"
            ] = status_name
            result.summary_kpis[
                "phase_2_status"
            ] = feasibility_status_name

            return result

        # ------------------------------------------------------------------
        # Final failure
        # ------------------------------------------------------------------
        # IMPORTANT: UNKNOWN is not the same as INFEASIBLE.
        return OptimizationResult(
            status=feasibility_status_name,
            objective_value=(
                self.solver.objective_value
            ),
            planning_rows=[],
            machine_kpis=[],
            material_kpis=[],
            procurement_kpis=[],
            order_kpis=[],
            summary_kpis={
                "status": feasibility_status_name,
                "optimization_mode": "FAILED",
                "objective_optimized": False,
                "phase_1_status": status_name,
                "phase_2_status": feasibility_status_name,
                "wall_time_seconds": (
                    self.solver.wall_time
                ),
            },
        )

    # =========================================================================
    # RESULT EXTRACTION
    # =========================================================================

    def _extract_result(
        self,
        status_name: str,
    ) -> OptimizationResult:

        planning_rows: List[dict] = []

        predecessor: Dict[
            Tuple[str, int],
            Optional[Tuple[str, int]],
        ] = {}

        # ---------------------------------------------------------------------
        # Recover selected predecessor.
        # ---------------------------------------------------------------------

        for machine_id, mv in (
            self.machine_vars.items()
        ):

            for (
                task_key,
                assignment,
            ) in mv.assignment.items():

                if self.solver.value(
                    assignment
                ) != 1:
                    continue

                pred = None

                for (
                    (
                        a_key,
                        b_key,
                    ),
                    transition,
                ) in mv.transition.items():

                    if (
                        b_key == task_key
                        and self.solver.value(
                            transition
                        ) == 1
                    ):

                        pred = a_key
                        break

                predecessor[
                    task_key
                ] = pred

        # ---------------------------------------------------------------------
        # Build planning rows.
        # ---------------------------------------------------------------------

        for task in self.tasks:

            task_id = self.task_id(
                task.key
            )

            selected_machine = None

            for machine_id in (
                task.routing.compatible_machines
            ):

                assignment = self.assignment[
                    (
                        task.key,
                        machine_id,
                    )
                ]

                if self.solver.value(
                    assignment
                ) == 1:

                    selected_machine = (
                        machine_id
                    )

                    break

            if selected_machine is None:
                continue

            pred_key = predecessor.get(
                task.key
            )

            setup_from_product = (
                self.task_by_key[
                    pred_key
                ].product_id
                if pred_key is not None
                else None
            )

            setup_minutes = (
                self.get_setup_minutes(
                    selected_machine,
                    setup_from_product,
                    task.product_id,
                )
                if setup_from_product
                else 0
            )

            start = self.solver.value(
                self.start[task_id]
            )

            end = self.solver.value(
                self.end[task_id]
            )

            planning_rows.append(
                {
                    "order_id": task.order_id,
                    "product_id": task.product_id,
                    "operation_seq": task.operation_seq,
                    "operation_code": task.operation_code,
                    "machine_id": selected_machine,
                    "start_min": start,
                    "end_min": end,
                    "start_datetime": (
                        self.calendar
                        .from_working_minute(
                            start
                        )
                        .isoformat(
                            sep=" "
                        )
                    ),
                    "end_datetime": (
                        self.calendar
                        .from_working_minute(
                            end
                        )
                        .isoformat(
                            sep=" "
                        )
                    ),
                    "processing_minutes": (
                        end - start
                    ),
                    "setup_from_product": (
                        setup_from_product
                    ),
                    "setup_minutes": (
                        setup_minutes
                    ),
                }
            )

        machine_kpis = (
            self._machine_kpis()
        )

        material_kpis = (
            self._material_kpis()
        )

        procurement_kpis = self._procurement_kpis()

        order_kpis = (
            self._order_kpis()
        )

        summary = self._summary_kpis(
            order_kpis,
            machine_kpis,
            material_kpis,
        )

        summary[
            "solver_wall_time_seconds"
        ] = self.solver.wall_time

        summary[
            "solver_best_bound"
        ] = self.solver.best_objective_bound

        summary[
            "solver_status"
        ] = status_name

        return OptimizationResult(
            status=status_name,
            objective_value=(
                self.solver.objective_value
            ),
            planning_rows=sorted(
                planning_rows,
                key=lambda row: (
                    row["machine_id"],
                    row["start_min"],
                    row["order_id"],
                    row["operation_seq"],
                ),
            ),
            machine_kpis=machine_kpis,
            material_kpis=material_kpis,
            procurement_kpis=procurement_kpis,
            order_kpis=order_kpis,
            summary_kpis=summary,
        )

    # =========================================================================
    # MACHINE KPIs
    # =========================================================================

    def _machine_kpis(
        self,
    ) -> List[dict]:

        result: List[dict] = []

        for machine_id, mv in (
            self.machine_vars.items()
        ):

            busy = 0

            for (
                task_key,
                assignment,
            ) in mv.assignment.items():

                if self.solver.value(
                    assignment
                ) != 1:
                    continue

                task = self.task_by_key[
                    task_key
                ]

                busy += (
                    self._effective_duration(
                        task,
                        machine_id,
                    )
                )

            setup_minutes = 0
            setup_count = 0

            for (
                (
                    a_key,
                    b_key,
                ),
                transition,
            ) in mv.transition.items():

                if self.solver.value(
                    transition
                ) != 1:
                    continue

                a = self.task_by_key[
                    a_key
                ]

                b = self.task_by_key[
                    b_key
                ]

                setup_minutes += (
                    self.get_setup_minutes(
                        machine_id,
                        a.product_id,
                        b.product_id,
                    )
                )

                setup_count += 1

            idle_internal = (
                self.solver.value(
                    mv.machine_idle
                )
                if mv.machine_idle is not None
                else 0
            )

            machine_rows = self.data.machine_calendars.get(machine_id, [])
            available = sum(
                max(0.0, float(r.planned_available_hours)) * 60.0
                for r in machine_rows
                if r.is_workday
            ) + self.overtime_minutes * sum(
                1 for r in machine_rows if r.is_workday
            )
            if not machine_rows:
                available = self.calendar.total_working_minutes

            result.append(
                {
                    "machine_id": machine_id,
                    "available_working_min": available,
                    "busy_processing_min": busy,
                    "setup_min": setup_minutes,
                    "setup_count": setup_count,
                    "idle_internal_min": idle_internal,
                    "utilization_pct": (
                        100.0 * busy / available
                        if available
                        else 0.0
                    ),
                    "occupancy_pct": (
                        100.0
                        * (
                            busy
                            + setup_minutes
                        )
                        / available
                        if available
                        else 0.0
                    ),
                }
            )

        return result

    # =========================================================================
    # MATERIAL KPIs
    # =========================================================================

    def _material_kpis(
        self,
    ) -> List[dict]:

        result: List[dict] = []

        for material_id, material in (
            self.data.materials.items()
        ):

            inventory_values = [
                self.solver.value(
                    self.inventory_end[
                        (
                            material_id,
                            d,
                        )
                    ]
                )
                for d in self.calendar.work_days
            ]

            average_scaled = (
                sum(inventory_values)
                / len(inventory_values)
                if inventory_values
                else 0
            )

            result.append(
                {
                    "material_id": material_id,
                    "avg_inventory_qty": (
                        average_scaled
                        / self.material_scale
                    ),
                    "ending_inventory_qty": (
                        inventory_values[-1]
                        / self.material_scale
                        if inventory_values
                        else 0.0
                    ),
                    "min_inventory_qty": (
                        min(inventory_values)
                        / self.material_scale
                        if inventory_values
                        else 0.0
                    ),
                    "safety_stock_qty": (
                        material.safety_stock_qty
                    ),
                    "planned_replenishment_qty": (
                        sum(
                            self.solver.value(qty)
                            for (mid, _sid, _d), qty in self.purchase_qty.items()
                            if mid == material_id
                        )
                        / self.material_scale
                    ),
                }
            )

        return result

    # =========================================================================
    # ORDER KPIs
    # =========================================================================

    def _order_kpis(
        self,
    ) -> List[dict]:

        result: List[dict] = []

        for order in self.data.orders:

            last_key = self.last_operation_key(
                order.order_id
            )

            completion = self.solver.value(
                self.end[
                    self.task_id(last_key)
                ]
            )

            due = (
                self.calendar.to_working_minute(
                    order.requested_due_date,
                    prefer_end_of_day=True,
                )
            )

            tardy = max(
                0,
                completion - due,
            )

            result.append(
                {
                    "order_id": order.order_id,
                    "customer": order.customer,
                    "product_id": order.product_id,
                    "priority_class": (
                        order.priority_class
                    ),
                    "priority_weight": (
                        self.priority_weight(
                            order
                        )
                    ),
                    "urgent": (
                        order.is_urgent
                    ),
                    "due_datetime": (
                        order.requested_due_date
                        .isoformat(
                            sep=" "
                        )
                    ),
                    "completion_datetime": (
                        self.calendar
                        .from_working_minute(
                            completion
                        )
                        .isoformat(
                            sep=" "
                        )
                    ),
                    "tardiness_min": tardy,
                    "tardiness_hours": (
                        tardy / 60.0
                    ),
                    "on_time": (
                        tardy == 0
                    ),
                }
            )

        return result

    # =========================================================================
    # SUMMARY KPIs
    # =========================================================================

    def _summary_kpis(
        self,
        orders: List[dict],
        machines: List[dict],
        materials: List[dict],
    ) -> dict:

        n_orders = len(
            orders
        )

        on_time = sum(
            1
            for order in orders
            if order["on_time"]
        )

        tardiness_values = [
            order["tardiness_min"]
            for order in orders
        ]

        total_setup = sum(
            machine["setup_min"]
            for machine in machines
        )

        total_setup_count = sum(
            machine["setup_count"]
            for machine in machines
        )

        total_idle = sum(
            machine["idle_internal_min"]
            for machine in machines
        )

        return {
            "service_rate_pct": (
                100.0 * on_time / n_orders
                if n_orders
                else 0.0
            ),
            "avg_tardiness_hours": (
                sum(tardiness_values)
                / n_orders
                / 60.0
                if n_orders
                else 0.0
            ),
            "max_tardiness_hours": (
                max(tardiness_values)
                / 60.0
                if tardiness_values
                else 0.0
            ),
            "late_orders": (
                n_orders - on_time
            ),
            "total_setup_min": (
                total_setup
            ),
            "setup_count": (
                total_setup_count
            ),
            "avg_inventory_qty": (
                sum(
                    material[
                        "avg_inventory_qty"
                    ]
                    for material in materials
                )
            ),
            "total_idle_internal_min": (
                total_idle
            ),
            "procurement_orders": len(self._procurement_kpis()),
            "procurement_qty": sum(r["order_qty"] for r in self._procurement_kpis()),
            "procurement_cost_eur": sum(r["purchase_cost_eur"] for r in self._procurement_kpis()),
            "material_shortage_qty": sum(self.solver.value(v) for v in self.shortage_end.values()) / self.material_scale,
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def task_id(
        key: Tuple[str, int],
    ) -> str:
        return (
            f"{key[0]}__OP{key[1]}"
        )

    def first_operation_key(
        self,
        order_id: str,
    ) -> Tuple[str, int]:

        order = self.order_by_id[
            order_id
        ]

        first_seq = min(
            route.operation_seq
            for route in self.data.routing[
                order.product_id
            ]
        )

        return (
            order_id,
            first_seq,
        )

    def last_operation_key(
        self,
        order_id: str,
    ) -> Tuple[str, int]:

        order = self.order_by_id[
            order_id
        ]

        last_seq = max(
            route.operation_seq
            for route in self.data.routing[
                order.product_id
            ]
        )

        return (
            order_id,
            last_seq,
        )

    @staticmethod
    def priority_weight(
        order: OrderData,
    ) -> int:
        """
        Business rule:

            A > B > C

        Raw priority_weight is intentionally ignored.
        """

        return PRIORITY_WEIGHT.get(
            str(
                order.priority_class
            ).upper(),
            1,
        )

    def get_setup_minutes(
        self,
        machine_id: str,
        from_product: Optional[str],
        to_product: str,
    ) -> int:
        """
        Sequence-dependent setup time.

        Same product:
            0 min

        Missing setup matrix:
            30 min default
        """

        if (
            from_product is None
            or from_product == to_product
        ):
            return 0

        return max(
            0,
            int(
                self.data.setup_minutes.get(
                    (
                        machine_id,
                        from_product,
                        to_product,
                    ),
                    30,
                )
            ),
        )


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    "AvailabilityEvent",
    "BomData",
    "CalendarDay",
    "MachineCalendarData",
    "MachineData",
    "MaterialData",
    "ObjectiveWeights",
    "OptimizationResult",
    "SupplierLeadTimeScenario",
    "OrderData",
    "PlanningData",
    "ProductData",
    "ProductionCPSATOptimizer",
    "RoutingData",
]