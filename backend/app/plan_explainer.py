from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import BOM, Machine, Material, Order, PlanningResult, Routing, SetupMatrix


class PlanExplainer:
    """Builds evidence-based explanations for an optimized operation.

    Important: this service explains observable evidence from the final plan.
    It does not claim that a human-readable reason was explicitly chosen by
    CP-SAT unless the underlying model actually contains that criterion.
    """

    def __init__(self, db: Session, run_id: str):
        self.db = db
        self.run_id = run_id

    @staticmethod
    def _parse_machines(value: str | None) -> list[str]:
        if not value:
            return []
        normalized = value.replace(";", ",").replace("|", ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]

    @staticmethod
    def _fmt_date(value: datetime | None) -> str:
        return value.strftime("%d/%m/%Y") if value else "—"

    @staticmethod
    def _status(ok: bool | None) -> str:
        if ok is True:
            return "positive"
        if ok is False:
            return "negative"
        return "neutral"

    def _candidate_loads(self, candidate_machines: list[str], operation_id: int) -> dict[str, float]:
        rows = (
            self.db.query(PlanningResult)
            .filter(PlanningResult.run_id == self.run_id)
            .all()
        )
        loads: dict[str, float] = defaultdict(float)
        for row in rows:
            if row.id == operation_id:
                continue
            if row.machine_id in candidate_machines:
                loads[row.machine_id] += float(row.processing_minutes or 0) + float(row.setup_minutes or 0)
        return dict(loads)

    def _setup_for_candidate(
        self,
        candidate_machine: str,
        product_id: str,
        operation_id: int,
    ) -> float:
        previous = (
            self.db.query(PlanningResult)
            .filter(
                PlanningResult.run_id == self.run_id,
                PlanningResult.machine_id == candidate_machine,
                PlanningResult.id != operation_id,
                PlanningResult.start_min < (
                    self.db.query(PlanningResult.start_min)
                    .filter(PlanningResult.id == operation_id)
                    .scalar_subquery()
                ),
            )
            .order_by(PlanningResult.start_min.desc())
            .first()
        )

        if previous is None:
            return 0.0

        setup = (
            self.db.query(SetupMatrix)
            .filter(
                SetupMatrix.machine_id == candidate_machine,
                SetupMatrix.from_product_id == previous.product_id,
                SetupMatrix.to_product_id == product_id,
            )
            .first()
        )
        return float(setup.setup_time_min) if setup else 0.0

    def _material_status(self, order: Order, operation_seq: int) -> dict[str, Any]:
        boms = (
            self.db.query(BOM)
            .filter(
                BOM.product_id == order.product_id,
                BOM.consumption_operation_seq <= operation_seq,
            )
            .all()
        )

        if not boms:
            return {
                "available": None,
                "required_qty": 0.0,
                "checked_materials": [],
                "message": "No BOM material is linked to this operation sequence.",
            }

        materials = {
            material.material_id: material
            for material in self.db.query(Material).filter(
                Material.material_id.in_([bom.material_id for bom in boms])
            ).all()
        }

        details = []
        all_available = True
        total_required = 0.0

        for bom in boms:
            required = float(order.order_qty) * float(bom.qty_per_unit) * (1.0 + float(bom.scrap_factor_pct or 0.0) / 100.0)
            material = materials.get(bom.material_id)
            on_hand = float(material.on_hand_qty) if material else 0.0
            available = material is not None and on_hand >= required
            all_available = all_available and available
            total_required += required
            details.append({
                "material_id": bom.material_id,
                "required_qty": round(required, 2),
                "on_hand_qty": round(on_hand, 2),
                "available": available,
            })

        return {
            "available": all_available,
            "required_qty": round(total_required, 2),
            "checked_materials": details,
            "message": "Required BOM materials are available." if all_available else "At least one required BOM material is below the calculated requirement.",
        }

    def explain_operation(self, operation_id: int) -> dict[str, Any]:
        operation = (
            self.db.query(PlanningResult)
            .filter(
                PlanningResult.id == operation_id,
                PlanningResult.run_id == self.run_id,
            )
            .first()
        )
        if operation is None:
            raise ValueError("Planning operation not found for this run.")

        order = self.db.query(Order).filter(Order.order_id == operation.order_id).first()
        if order is None:
            raise ValueError(f"Order '{operation.order_id}' was not found.")

        routing = (
            self.db.query(Routing)
            .filter(
                Routing.product_id == operation.product_id,
                Routing.operation_seq == operation.operation_seq,
            )
            .first()
        )

        candidate_machines = self._parse_machines(routing.compatible_machines if routing else None)
        if operation.machine_id not in candidate_machines:
            candidate_machines.append(operation.machine_id)

        machine = self.db.query(Machine).filter(Machine.machine_id == operation.machine_id).first()
        loads = self._candidate_loads(candidate_machines, operation.id)
        loads[operation.machine_id] = loads.get(operation.machine_id, 0.0) + float(operation.processing_minutes or 0) + float(operation.setup_minutes or 0)

        candidate_setup = {
            machine_id: self._setup_for_candidate(machine_id, operation.product_id, operation.id)
            for machine_id in candidate_machines
        }
        selected_load = loads.get(operation.machine_id, 0.0)
        selected_setup = candidate_setup.get(operation.machine_id, float(operation.setup_minutes or 0))
        alternative_loads = [v for k, v in loads.items() if k != operation.machine_id]
        alternative_setups = [v for k, v in candidate_setup.items() if k != operation.machine_id]

        load_advantage = bool(alternative_loads) and selected_load <= min(alternative_loads)
        setup_advantage = bool(alternative_setups) and selected_setup <= min(alternative_setups)

        due_ok = operation.end_datetime <= order.requested_due_date
        material = self._material_status(order, operation.operation_seq)

        reasons = []
        reasons.append({
            "type": "compatibility",
            "status": self._status(operation.machine_id in candidate_machines),
            "title": "Machine compatibility",
            "message": f"{operation.machine_id} is compatible with {operation.operation_code} for {operation.product_id}." if routing else "Routing compatibility data is not available.",
            "evidence": "routing",
        })

        reasons.append({
            "type": "load",
            "status": self._status(load_advantage if alternative_loads else None),
            "title": "Machine load",
            "message": (
                f"{operation.machine_id} has {selected_load:.0f} scheduled minutes versus "
                f"{min(alternative_loads):.0f} minutes on the least-loaded alternative."
                if alternative_loads else "No alternative compatible machine is available for comparison."
            ),
            "evidence": "final_plan",
        })

        reasons.append({
            "type": "priority",
            "status": "positive" if order.priority_class == "A" or order.is_urgent else "neutral",
            "title": "Customer priority",
            "message": f"Priority {order.priority_class}{' · urgent' if order.is_urgent else ''}.",
            "evidence": "order_master",
        })

        reasons.append({
            "type": "due_date",
            "status": self._status(due_ok),
            "title": "Due date",
            "message": (
                f"Operation finishes on {self._fmt_date(operation.end_datetime)} and the order is due on {self._fmt_date(order.requested_due_date)}."
            ),
            "evidence": "final_plan",
        })

        reasons.append({
            "type": "material",
            "status": self._status(material["available"]),
            "title": "Material availability",
            "message": material["message"],
            "evidence": "bom_and_inventory",
        })

        reasons.append({
            "type": "setup",
            "status": self._status(setup_advantage if alternative_setups else None),
            "title": "Setup time",
            "message": (
                f"Estimated setup on {operation.machine_id}: {selected_setup:.0f} min; "
                f"best alternative: {min(alternative_setups):.0f} min."
                if alternative_setups else f"Estimated setup on {operation.machine_id}: {selected_setup:.0f} min."
            ),
            "evidence": "setup_matrix",
        })

        availability_ok = machine is not None and float(machine.availability_pct) > 0
        reasons.append({
            "type": "availability",
            "status": self._status(availability_ok if machine else None),
            "title": "Machine availability",
            "message": (
                f"{operation.machine_id} has a configured availability of {float(machine.availability_pct):.1f}%."
                if machine else "Machine master data is not available."
            ),
            "evidence": "machine_master",
        })

        decision_factors = []
        if load_advantage:
            decision_factors.append("lower_machine_load")
        if setup_advantage:
            decision_factors.append("lower_setup")
        if due_ok:
            decision_factors.append("due_date_feasible")
        if material["available"] is True:
            decision_factors.append("material_available")

        if load_advantage and setup_advantage:
            summary = f"{operation.order_id} was scheduled on {operation.machine_id} because it was compatible and showed both a lower observed load and a lower setup time than the alternatives."
        elif load_advantage:
            summary = f"{operation.order_id} was scheduled on {operation.machine_id} because it was compatible and had the lowest observed load among the compatible machines."
        elif setup_advantage:
            summary = f"{operation.order_id} was scheduled on {operation.machine_id} because it was compatible and had the lowest observed setup time among the alternatives."
        else:
            summary = f"{operation.order_id} was scheduled on {operation.machine_id}. The machine is compatible; the remaining evidence does not identify one single dominant factor from the final plan."

        return {
            "run_id": self.run_id,
            "operation_id": operation.id,
            "order_id": operation.order_id,
            "product_id": operation.product_id,
            "operation_seq": operation.operation_seq,
            "operation_code": operation.operation_code,
            "machine_id": operation.machine_id,
            "machine_name": machine.machine_name if machine else operation.machine_id,
            "start_datetime": operation.start_datetime,
            "end_datetime": operation.end_datetime,
            "processing_minutes": operation.processing_minutes,
            "setup_minutes": operation.setup_minutes,
            "priority_class": order.priority_class,
            "customer": order.customer,
            "due_date": order.requested_due_date,
            "urgent": bool(order.is_urgent),
            "summary": summary,
            "reasons": reasons,
            "decision_factors": decision_factors,
            "candidate_machines": [
                {
                    "machine_id": machine_id,
                    "scheduled_minutes": round(loads.get(machine_id, 0.0), 1),
                    "setup_minutes": round(candidate_setup.get(machine_id, 0.0), 1),
                    "selected": machine_id == operation.machine_id,
                }
                for machine_id in candidate_machines
            ],
            "material_check": material,
            "explainability_note": "Reasons are evidence from routing, the final schedule, setup data, order master data and inventory. They are not claimed as direct causal CP-SAT decisions unless represented by the optimization model.",
        }
