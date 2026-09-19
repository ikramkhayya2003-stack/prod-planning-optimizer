from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from optimizer_cp_sat import PRIORITY_WEIGHT

from app.models import (
    BOM,
    Machine,
    Material,
    Order,
    ScenarioOrder,
    OrderKPI,
    PlanningResult,
)


# ============================================================
# RISK PRIORITY
# ============================================================

RISK_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
}


# ============================================================
# DATETIME HELPER
# ============================================================

def safe_datetime(value):

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(
            str(value)
        )
    except (ValueError, TypeError):
        return None


# ============================================================
# BUILD ORDER RISK MAP
# ============================================================

def build_order_risk_map(
    db: Session,
    run_id: str | None = None,
):
    """
    Build a risk analysis for each order.

    Risk sources:
        - delivery delay
        - material shortage / low coverage
        - machine availability pressure
    """

    # ========================================================
    # ORDERS
    # ========================================================

    base_orders = db.query(Order).all()
    scenario_orders = db.query(ScenarioOrder).all()

    # Scenario orders are also optimization orders. Keep one common
    # representation so risk analysis works for what-if scenarios too.
    orders = sorted(
        [*base_orders, *scenario_orders],
        key=lambda row: row.requested_due_date,
    )

    # ========================================================
    # PLANNING
    # ========================================================

    planning_rows = []

    if run_id:

        planning_rows = (
            db.query(PlanningResult)
            .filter(
                PlanningResult.run_id
                == run_id
            )
            .all()
        )

    planning_by_order = defaultdict(
        list
    )

    for row in planning_rows:

        planning_by_order[
            row.order_id
        ].append(row)

    # ========================================================
    # ORDER KPIS
    # ========================================================

    kpis_by_order = {}

    if run_id:

        kpi_rows = (
            db.query(OrderKPI)
            .filter(
                OrderKPI.run_id
                == run_id
            )
            .all()
        )

        kpis_by_order = {
            row.order_id: row
            for row in kpi_rows
        }

    # ========================================================
    # MACHINES
    # ========================================================

    machine_map = {
        row.machine_id: row
        for row in db.query(
            Machine
        ).all()
    }

    # ========================================================
    # MATERIALS
    # ========================================================

    material_map = {
        row.material_id: row
        for row in db.query(
            Material
        ).all()
    }

    # ========================================================
    # BOM
    # ========================================================

    bom_rows = (
        db.query(BOM)
        .all()
    )

    bom_by_product = defaultdict(
        list
    )

    for row in bom_rows:

        bom_by_product[
            row.product_id
        ].append(row)

    # ========================================================
    # FINAL RESULT
    # ========================================================

    risk_map = {}

    for order in orders:

        risk_level = "LOW"

        reasons = []

        expected_completion = None

        due_datetime = (
            order.requested_due_date
        )

        delay_hours = 0.0

        delay_days = 0.0

        material_risks = []

        machine_risks = []

        # ====================================================
        # PLANNING
        # ====================================================

        order_rows = (
            planning_by_order.get(
                order.order_id,
                []
            )
        )

        if order_rows:

            last_row = max(
                order_rows,
                key=lambda row:
                    row.end_min
            )

            expected_completion = (
                safe_datetime(
                    last_row.end_datetime
                )
            )

        # ====================================================
        # ORDER KPI
        # ====================================================

        kpi = kpis_by_order.get(
            order.order_id
        )

        if kpi:

            if (
                kpi.completion_datetime
                is not None
            ):

                expected_completion = (
                    safe_datetime(
                        kpi.completion_datetime
                    )
                )

            delay_hours = float(
                kpi.tardiness_hours
                or 0
            )

        elif (
            expected_completion
            is not None
            and due_datetime
            is not None
        ):

            difference = (
                expected_completion
                - due_datetime
            )

            delay_hours = max(
                0.0,
                difference.total_seconds()
                / 3600.0,
            )

        delay_days = (
            delay_hours / 24.0
        )

        # ====================================================
        # DELAY RISK
        # ====================================================

        if delay_hours > 0:

            risk_level = "HIGH"

            reasons.append(
                "Customer due date at risk"
            )

        # ====================================================
        # MATERIAL RISK
        # ====================================================

        for bom in bom_by_product.get(
            order.product_id,
            []
        ):

            material = material_map.get(
                bom.material_id
            )

            if material is None:
                continue

            coverage = float(
                material.coverage_days
                or 0
            )

            lead_time = float(
                material.lead_time_days
                or 0
            )

            on_hand = float(
                material.on_hand_qty
                or 0
            )

            safety_stock = float(
                material.safety_stock_qty
                or 0
            )

            high_risk_material = (
                coverage <= lead_time
                or on_hand <= safety_stock
            )

            medium_risk_material = (
                coverage < 14
            )

            if (
                high_risk_material
                or medium_risk_material
            ):

                material_risks.append(
                    {
                        "material_id":
                            material.material_id,

                        "coverage_days":
                            round(
                                coverage,
                                2
                            ),

                        "lead_time_days":
                            round(
                                lead_time,
                                2
                            ),

                        "on_hand_qty":
                            round(
                                on_hand,
                                2
                            ),

                        "safety_stock_qty":
                            round(
                                safety_stock,
                                2
                            ),

                        "severity":
                            (
                                "HIGH"
                                if high_risk_material
                                else "MEDIUM"
                            ),
                    }
                )

        if material_risks:

            has_high_material_risk = any(
                item["severity"] == "HIGH"
                for item in material_risks
            )

            if has_high_material_risk:

                risk_level = "HIGH"

                reasons.append(
                    "Material shortage risk"
                )

            elif risk_level == "LOW":

                risk_level = "MEDIUM"

                reasons.append(
                    "Low material coverage"
                )

        # ====================================================
        # MACHINE RISK
        # ====================================================

        for row in order_rows:

            machine = machine_map.get(
                row.machine_id
            )

            if machine is None:
                continue

            availability = float(
                machine.availability_pct
                or 0
            )

            if availability < 90:

                machine_risks.append(
                    {
                        "machine_id":
                            machine.machine_id,

                        "availability_pct":
                            availability,
                    }
                )

        if machine_risks:

            if risk_level == "LOW":

                risk_level = "MEDIUM"

                reasons.append(
                    "Machine availability pressure"
                )

            elif risk_level == "HIGH":

                reasons.append(
                    "Machine capacity pressure"
                )

        # ====================================================
        # NO RISK
        # ====================================================

        if not reasons:

            reasons.append(
                "No critical risk detected"
            )

        # Remove duplicates while keeping order.

        reasons = list(
            dict.fromkeys(
                reasons
            )
        )

        # ====================================================
        # RESULT
        # ====================================================

        risk_map[
            order.order_id
        ] = {

            "order_id":
                order.order_id,

            "customer":
                order.customer,

            "product_id":
                order.product_id,

            "priority_class":
                order.priority_class,

            "priority_weight":
                getattr(
                    order,
                    "priority_weight",
                    PRIORITY_WEIGHT.get(
                        order.priority_class,
                        1,
                    ),
                ),

            "urgent":
                bool(
                    order.is_urgent
                ),

            "risk":
                risk_level,

            "reasons":
                reasons,

            "expected_completion":
                expected_completion,

            "due_datetime":
                due_datetime,

            "delay_hours":
                round(
                    delay_hours,
                    2
                ),

            "delay_days":
                round(
                    delay_days,
                    2
                ),

            "material_risks":
                material_risks,

            "machine_risks":
                machine_risks,

            "material_ids":
                [
                    item[
                        "material_id"
                    ]
                    for item
                    in material_risks
                ],
        }

    return risk_map