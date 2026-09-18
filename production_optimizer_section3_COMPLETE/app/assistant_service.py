
"""
Planning Assistant Service
==========================

Data-grounded conversational assistant for the production planning system.

Design goals:
- No modification of the optimizer.
- No modification of database models.
- Uses the active/latest optimization run.
- Uses real planning, order-risk, machine and material data.
- Supports English, French and mixed questions.
- Returns auditable facts instead of inventing explanations.
- Keeps the API compatible with the existing frontend:
      {
          "answer": "...",
          "facts": [...]
      }

Additional response fields are included for future frontend improvements:
- intent
- run_id
- suggested_questions
- data
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    BOM,
    Machine,
    Material,
    Order,
    OptimizationRun,
    PlanningResult,
    ProcurementPlan,
    ScenarioOrder,
)
from app.risk_service import build_order_risk_map
from app.shortage_prediction import predict_material_shortage


# ============================================================================
# CONSTANTS
# ============================================================================

RISK_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

STOP_WORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "what",
    "which",
    "who",
    "why",
    "how",
    "can",
    "could",
    "should",
    "please",
    "me",
    "show",
    "give",
    "tell",
    "the",
    "la",
    "le",
    "les",
    "un",
    "une",
    "des",
    "du",
    "de",
    "est",
    "sont",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "pourquoi",
    "comment",
    "peux",
    "peut",
    "montre",
    "donne",
    "donner",
    "moi",
}


# ============================================================================
# TEXT HELPERS
# ============================================================================

def _normalize_text(value: Any) -> str:
    """
    Lowercase + remove accents + normalize separators.
    """
    text = str(value or "").strip().lower()

    text = unicodedata.normalize("NFD", text)
    text = "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )

    text = text.replace("_", "-")
    text = re.sub(r"\s+", " ", text)

    return text


def _contains_any(text: str, words: tuple[str, ...] | list[str]) -> bool:
    """
    Safe keyword detection.

    Uses normalized text and word boundaries where possible.
    """
    normalized = _normalize_text(text)

    for word in words:
        candidate = _normalize_text(word)

        if not candidate:
            continue

        if " " in candidate or "-" in candidate:
            if candidate in normalized:
                return True
        else:
            if re.search(rf"\b{re.escape(candidate)}\b", normalized):
                return True

    return False


def _is_french(text: str) -> bool:
    normalized = _normalize_text(text)

    french_words = (
        "pourquoi",
        "comment",
        "quelle",
        "quelles",
        "quel",
        "quels",
        "retard",
        "retards",
        "commande",
        "commandes",
        "matiere",
        "matières",
        "rupture",
        "stock",
        "machine",
        "charge",
        "plan",
        "production",
        "fournisseur",
        "risque",
        "urgent",
        "aujourd",
        "priorite",
    )

    score = sum(
        1
        for word in french_words
        if word in normalized
    )

    return score >= 1


def _format_number(value: Any, decimals: int = 0) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0

    if decimals == 0:
        return f"{number:,.0f}".replace(",", " ")

    return f"{number:,.{decimals}f}".replace(",", " ")


def _format_hours(minutes: Any) -> str:
    try:
        hours = float(minutes or 0) / 60.0
    except (TypeError, ValueError):
        hours = 0.0

    return f"{hours:.1f} h"


def _safe_datetime(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")

    return str(value)


# ============================================================================
# ENTITY EXTRACTION
# ============================================================================

def _extract_order_id(question: str, orders: dict[str, Any]) -> str | None:
    """
    Detect order IDs such as:
      ORD104
      ORD-104
      ORDER104
      SO-001
      SO001
    """

    q = question.upper().replace("_", "-")

    patterns = [
        r"\bORDER[- ]?([A-Z]{0,5})[- ]?(\d{2,})\b",
        r"\bORD[- ]?([A-Z]{0,5})[- ]?(\d{2,})\b",
        r"\bSO[- ]?(\d{2,})\b",
    ]

    candidates: list[str] = []

    for pattern in patterns:
        for match in re.finditer(pattern, q, re.I):
            groups = [g for g in match.groups() if g]

            if not groups:
                continue

            if len(groups) == 1:
                token = groups[0]
            else:
                token = "".join(groups)

            candidates.append(token.upper())

    # Direct exact match first.
    normalized_orders = {
        str(order_id).upper(): str(order_id)
        for order_id in orders
    }

    for token in candidates:
        if token in normalized_orders:
            return normalized_orders[token]

    # Existing system IDs can have prefixes.
    for token in candidates:
        for order_id in orders:
            oid = str(order_id).upper()

            if oid.endswith(token):
                return order_id

    # Generic alphanumeric order token fallback.
    generic = re.findall(
        r"\b(?:ORD|ORDER|SO)[-_]?[A-Z0-9]{2,}\b",
        q,
        re.I,
    )

    for token in generic:
        token = token.upper().replace("_", "-")

        if token in normalized_orders:
            return normalized_orders[token]

        for order_id in orders:
            if str(order_id).upper().endswith(token):
                return order_id

    return None


def _extract_machine_id(question: str, machines: dict[str, Any]) -> str | None:
    q = question.upper().replace("_", "-")

    # Prefer exact known machine IDs.
    for machine_id in machines:
        normalized = str(machine_id).upper().replace("_", "-")

        if normalized in q:
            return machine_id

    # Generic machine IDs such as CUT-01, ASM-02, TEST-01.
    match = re.search(
        r"\b(?:CUT|CRIMP|ASM|TEST|ASSY|MACHINE|MC)[-_]?\d{1,3}\b",
        q,
        re.I,
    )

    if match:
        token = match.group(0).upper().replace("_", "-")

        for machine_id in machines:
            if str(machine_id).upper().replace("_", "-") == token:
                return machine_id

    return None


def _extract_material_id(question: str, materials: dict[str, Any]) -> str | None:
    q = question.upper().replace("_", "-")

    # Exact known material ID.
    for material_id in materials:
        normalized = str(material_id).upper().replace("_", "-")

        if normalized in q:
            return material_id

    # Generic material pattern: MAT-001, MAT023, etc.
    match = re.search(
        r"\bMAT[-_]?\d{1,5}\b",
        q,
        re.I,
    )

    if match:
        token = match.group(0).upper().replace("_", "-")

        for material_id in materials:
            if str(material_id).upper().replace("_", "-") == token:
                return material_id

    return None


# ============================================================================
# RUN SELECTION
# ============================================================================

def _select_run(
    db: Session,
    requested_run_id: str | None,
) -> OptimizationRun | None:
    """
    Select:
    1. explicitly requested run;
    2. latest completed/usable run;
    3. latest run as fallback.
    """

    if requested_run_id:
        run = (
            db.query(OptimizationRun)
            .filter(OptimizationRun.run_id == requested_run_id)
            .first()
        )

        if run is not None:
            return run

    # Prefer completed / feasible-like runs.
    runs = (
        db.query(OptimizationRun)
        .order_by(
            OptimizationRun.created_at.desc(),
            OptimizationRun.id.desc(),
        )
        .limit(20)
        .all()
    )

    if not runs:
        return None

    preferred = []

    for run in runs:
        status = str(
            getattr(run, "solver_status", None)
            or getattr(run, "status", None)
            or ""
        ).upper()

        if any(
            marker in status
            for marker in (
                "COMPLETED",
                "FEASIBLE",
                "OPTIMAL",
            )
        ):
            preferred.append(run)

    if preferred:
        return preferred[0]

    return runs[0]


# ============================================================================
# DATA LOADING
# ============================================================================

def _load_orders(db: Session) -> dict[str, Any]:
    """
    Merge standard orders and scenario orders.

    Scenario orders override standard orders with the same ID,
    preserving the behavior of the previous assistant implementation.
    """

    orders: dict[str, Any] = {}

    for order in db.query(Order).all():
        orders[str(order.order_id)] = order

    for order in db.query(ScenarioOrder).all():
        orders[str(order.order_id)] = order

    return orders


def _load_planning(
    db: Session,
    run_id: str,
) -> list[PlanningResult]:
    return (
        db.query(PlanningResult)
        .filter(PlanningResult.run_id == run_id)
        .all()
    )


# ============================================================================
# INTENT DETECTION
# ============================================================================

def _detect_intent(
    question: str,
    order_id: str | None,
    machine_id: str | None,
    material_id: str | None,
) -> str:

    q = _normalize_text(question)

    # ------------------------------------------------------------
    # Specific order
    # ------------------------------------------------------------

    if order_id:
        if _contains_any(
            q,
            (
                "pourquoi",
                "why",
                "retard",
                "late",
                "delay",
                "reason",
                "raison",
                "risque",
                "risk",
                "urgent",
                "critical",
                "critique",
            ),
        ):
            return "order_risk"

        if _contains_any(
            q,
            (
                "machine",
                "scheduled",
                "schedule",
                "planifie",
                "planifiee",
                "planification",
                "where",
                "ou",
            ),
        ):
            return "order_detail"

        return "order_detail"

    # ------------------------------------------------------------
    # Specific machine
    # ------------------------------------------------------------

    if machine_id:
        return "machine_detail"

    # ------------------------------------------------------------
    # Specific material
    # ------------------------------------------------------------

    if material_id:
        return "material_detail"

    # ------------------------------------------------------------
    # Supplier
    # ------------------------------------------------------------

    if _contains_any(
        q,
        (
            "supplier",
            "suppliers",
            "fournisseur",
            "fournisseurs",
            "procurement",
            "approvisionnement",
            "lead time",
            "delai fournisseur",
        ),
    ):
        return "supplier_risk"

    # ------------------------------------------------------------
    # Machine / capacity
    # ------------------------------------------------------------

    if _contains_any(
        q,
        (
            "machine",
            "machines",
            "capacity",
            "capacite",
            "capacity",
            "loaded",
            "charge",
            "utilization",
            "utilisation",
            "bottleneck",
            "goulot",
            "overloaded",
            "surcharge",
        ),
    ):
        return "machine_load"

    # ------------------------------------------------------------
    # Material / shortage
    # ------------------------------------------------------------

    if _contains_any(
        q,
        (
            "material",
            "materials",
            "matiere",
            "matieres",
            "stock",
            "shortage",
            "rupture",
            "inventory",
            "inventaire",
            "coverage",
            "couverture",
            "replenishment",
            "reapprovisionnement",
        ),
    ):
        return "material_risk"

    # ------------------------------------------------------------
    # Risk / late orders
    # ------------------------------------------------------------

    if _contains_any(
        q,
        (
            "risk",
            "risque",
            "late",
            "retard",
            "retards",
            "delay",
            "delai",
            "urgent",
            "critical",
            "critique",
            "priorite",
            "priority",
        ),
    ):
        return "order_risk_list"

    # ------------------------------------------------------------
    # KPI
    # ------------------------------------------------------------

    if _contains_any(
        q,
        (
            "kpi",
            "kpis",
            "performance",
            "performance",
            "service rate",
            "tardiness",
            "retard moyen",
            "objective",
            "objectif",
        ),
    ):
        return "kpi"

    # ------------------------------------------------------------
    # Recommendation / action
    # ------------------------------------------------------------

    if _contains_any(
        q,
        (
            "what should i do",
            "what should we do",
            "que dois je faire",
            "que devons nous faire",
            "action",
            "actions",
            "recommend",
            "recommendation",
            "recommandation",
            "recommandations",
            "next step",
            "prochaine action",
        ),
    ):
        return "recommendation"

    # ------------------------------------------------------------
    # Plan explanation
    # ------------------------------------------------------------

    if _contains_any(
        q,
        (
            "plan",
            "planning",
            "schedule",
            "production plan",
            "plan de production",
            "planification",
            "explain the plan",
            "explique le plan",
            "current plan",
            "plan actuel",
        ),
    ):
        return "plan_summary"

    # ------------------------------------------------------------
    # Greeting
    # ------------------------------------------------------------

    if _contains_any(
        q,
        (
            "hello",
            "hi",
            "bonjour",
            "salut",
            "hey",
        ),
    ):
        return "greeting"

    return "help"


# ============================================================================
# RISK HELPERS
# ============================================================================

def _rank_risk_orders(
    risk_map: dict[str, dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:

    unique: dict[str, dict[str, Any]] = {}

    for order_id, data in risk_map.items():
        unique[str(order_id)] = data

    return sorted(
        unique.items(),
        key=lambda item: (
            RISK_RANK.get(
                str(item[1].get("risk", "LOW")).upper(),
                0,
            ),
            float(item[1].get("delay_hours") or 0),
        ),
        reverse=True,
    )


def _risk_reason_list(
    risk: dict[str, Any],
) -> list[str]:
    reasons = list(risk.get("reasons") or [])

    if not reasons:
        reasons = []

    machine = list(risk.get("machine_risks") or [])
    material = list(risk.get("material_risks") or [])

    for value in machine[:3]:
        text = f"Machine constraint: {value}"
        if text not in reasons:
            reasons.append(text)

    for value in material[:3]:
        text = f"Material constraint: {value}"
        if text not in reasons:
            reasons.append(text)

    if not reasons:
        reasons.append(
            "No major risk reason was recorded for this order."
        )

    return reasons


# ============================================================================
# ORDER ANALYSIS
# ============================================================================

def _answer_order(
    question: str,
    order_id: str,
    orders: dict[str, Any],
    planning: list[PlanningResult],
    risk_map: dict[str, dict[str, Any]],
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    risk = risk_map.get(order_id, {}) or {}
    order = orders.get(order_id)

    rows = [
        row
        for row in planning
        if str(row.order_id) == str(order_id)
    ]

    reasons = _risk_reason_list(risk)

    risk_name = str(
        risk.get("risk")
        or "LOW"
    ).upper()

    delay = float(
        risk.get("delay_hours")
        or 0
    )

    due = risk.get("due_datetime")
    completion = risk.get("expected_completion")

    machines = []
    operation_names = []

    for row in sorted(
        rows,
        key=lambda item: (
            int(item.operation_seq or 0),
            item.start_min or 0,
        ),
    ):
        if row.machine_id and row.machine_id not in machines:
            machines.append(row.machine_id)

        if row.operation_code:
            operation_names.append(str(row.operation_code))

    if french:
        answer = (
            f"**{order_id}** est classée en risque **{risk_name}**.\n\n"
            f"**Pourquoi :** {'; '.join(str(x) for x in reasons[:4])}.\n"
        )

        if order is not None:
            priority = getattr(
                order,
                "priority_class",
                None,
            )

            customer = getattr(
                order,
                "customer",
                None,
            )

            if customer:
                answer += f"Client : {customer}. "

            if priority:
                answer += f"Priorité : {priority}. "

            answer += "\n"

        if machines:
            answer += (
                f"Machines utilisées : {', '.join(machines)}.\n"
            )

        if operation_names:
            answer += (
                f"Opérations planifiées : {', '.join(operation_names)}.\n"
            )

        if due:
            answer += f"Due date : {_safe_datetime(due)}.\n"

        if completion:
            answer += (
                f"Fin prévue : {_safe_datetime(completion)}.\n"
            )

        if delay > 0:
            answer += (
                f"Retard estimé : **{delay:.1f} h**."
            )
        else:
            answer += (
                "Aucun retard positif n'est actuellement enregistré."
            )

    else:
        answer = (
            f"**{order_id}** is classified as **{risk_name}** risk.\n\n"
            f"**Why:** {'; '.join(str(x) for x in reasons[:4])}.\n"
        )

        if order is not None:
            priority = getattr(
                order,
                "priority_class",
                None,
            )

            customer = getattr(
                order,
                "customer",
                None,
            )

            if customer:
                answer += f"Customer: {customer}. "

            if priority:
                answer += f"Priority: {priority}. "

            answer += "\n"

        if machines:
            answer += (
                f"Scheduled machines: {', '.join(machines)}.\n"
            )

        if operation_names:
            answer += (
                f"Scheduled operations: {', '.join(operation_names)}.\n"
            )

        if due:
            answer += f"Due date: {_safe_datetime(due)}.\n"

        if completion:
            answer += (
                f"Expected completion: {_safe_datetime(completion)}.\n"
            )

        if delay > 0:
            answer += (
                f"Estimated delay: **{delay:.1f} h**."
            )
        else:
            answer += (
                "No positive delay is currently recorded."
            )

    facts = [
        f"Risk: {risk_name}",
        f"Operations: {len(rows)}",
        f"Machines: {len(machines)}",
        f"Run: {run_id}",
    ]

    suggestions = (
        [
            f"What is causing {order_id} to be late?",
            f"Which materials affect {order_id}?",
            f"Which machine is used by {order_id}?",
        ]
        if not french
        else
        [
            f"Pourquoi {order_id} est en retard ?",
            f"Quelles matières affectent {order_id} ?",
            f"Quelle machine est utilisée par {order_id} ?",
        ]
    )

    return {
        "answer": answer,
        "facts": facts,
        "intent": "order_risk",
        "run_id": run_id,
        "suggested_questions": suggestions,
        "data": {
            "order_id": order_id,
            "risk": risk_name,
            "delay_hours": delay,
            "machines": machines,
            "operations": operation_names,
        },
    }


# ============================================================================
# MACHINE ANALYSIS
# ============================================================================

def _machine_loads(
    planning: list[PlanningResult],
) -> dict[str, float]:

    machine_load: dict[str, float] = defaultdict(float)

    for row in planning:
        machine_id = str(
            row.machine_id
            or "UNASSIGNED"
        )

        machine_load[machine_id] += (
            float(row.processing_minutes or 0)
            + float(row.setup_minutes or 0)
        )

    return dict(machine_load)


def _answer_machine(
    question: str,
    machine_id: str | None,
    machines: dict[str, Any],
    planning: list[PlanningResult],
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    loads = _machine_loads(planning)

    if machine_id:
        load_minutes = float(
            loads.get(machine_id, 0)
        )

        machine = machines.get(machine_id)

        rows = [
            row
            for row in planning
            if str(row.machine_id) == str(machine_id)
        ]

        order_ids = sorted(
            {
                str(row.order_id)
                for row in rows
                if row.order_id
            }
        )

        if french:
            answer = (
                f"**{machine_id}** a actuellement "
                f"**{_format_hours(load_minutes)}** de charge planifiée "
                f"(production + setups).\n"
            )

            if machine is not None:
                capacity = getattr(
                    machine,
                    "capacity_units_hour",
                    None,
                )

                availability = getattr(
                    machine,
                    "availability_pct",
                    None,
                )

                stage = getattr(
                    machine,
                    "stage",
                    None,
                )

                if stage:
                    answer += f"Étape : {stage}. "

                if capacity is not None:
                    answer += (
                        f"Capacité nominale : "
                        f"{_format_number(capacity, 1)} unités/h. "
                    )

                if availability is not None:
                    answer += (
                        f"Disponibilité : "
                        f"{_format_number(availability, 1)} %. "
                    )

                answer += "\n"

            answer += (
                f"Nombre d'opérations : {len(rows)}.\n"
                f"Ordres concernés : {len(order_ids)}."
            )

        else:
            answer = (
                f"**{machine_id}** currently has "
                f"**{_format_hours(load_minutes)}** of scheduled load "
                f"(processing + setup).\n"
            )

            if machine is not None:
                capacity = getattr(
                    machine,
                    "capacity_units_hour",
                    None,
                )

                availability = getattr(
                    machine,
                    "availability_pct",
                    None,
                )

                stage = getattr(
                    machine,
                    "stage",
                    None,
                )

                if stage:
                    answer += f"Stage: {stage}. "

                if capacity is not None:
                    answer += (
                        f"Nominal capacity: "
                        f"{_format_number(capacity, 1)} units/h. "
                    )

                if availability is not None:
                    answer += (
                        f"Availability: "
                        f"{_format_number(availability, 1)}%. "
                    )

                answer += "\n"

            answer += (
                f"Operations: {len(rows)}.\n"
                f"Orders affected: {len(order_ids)}."
            )

        return {
            "answer": answer,
            "facts": [
                f"Machine: {machine_id}",
                f"Scheduled load: {load_minutes / 60:.1f} h",
                f"Operations: {len(rows)}",
                f"Run: {run_id}",
            ],
            "intent": "machine_detail",
            "run_id": run_id,
            "suggested_questions": (
                [
                    f"Is {machine_id} the bottleneck?",
                    "Which machines are most loaded?",
                    "Which orders use this machine?",
                ]
                if not french
                else
                [
                    f"Est-ce que {machine_id} est le goulot ?",
                    "Quelles sont les machines les plus chargées ?",
                    "Quels ordres utilisent cette machine ?",
                ]
            ),
            "data": {
                "machine_id": machine_id,
                "load_minutes": load_minutes,
                "operation_count": len(rows),
                "order_count": len(order_ids),
            },
        }

    ranked = sorted(
        loads.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    top = ranked[:8]

    if french:
        if not top:
            answer = (
                "Aucune charge machine n'est actuellement disponible "
                "dans le run sélectionné."
            )
        else:
            lines = [
                f"{machine}: {_format_hours(minutes)}"
                for machine, minutes in top
            ]

            answer = (
                "Les machines les plus chargées du plan actuel sont :\n\n"
                + "\n".join(
                    f"{index}. {line}"
                    for index, line in enumerate(lines, 1)
                )
                + "\n\n"
                "Le classement utilise le temps de production planifié "
                "plus le temps de setup."
            )
    else:
        if not top:
            answer = (
                "No machine load is currently available "
                "in the selected run."
            )
        else:
            lines = [
                f"{machine}: {_format_hours(minutes)}"
                for machine, minutes in top
            ]

            answer = (
                "The most loaded machines in the current plan are:\n\n"
                + "\n".join(
                    f"{index}. {line}"
                    for index, line in enumerate(lines, 1)
                )
                + "\n\n"
                "The ranking uses scheduled processing time "
                "plus setup time."
            )

    return {
        "answer": answer,
        "facts": [
            f"Machines scheduled: {len(loads)}",
            f"Run: {run_id}",
        ],
        "intent": "machine_load",
        "run_id": run_id,
        "suggested_questions": (
            [
                "Which machine is the bottleneck?",
                "Show the machine load ranking.",
                "Which orders are affected by the most loaded machine?",
            ]
            if not french
            else
            [
                "Quelle machine est le goulot ?",
                "Montre le classement des charges machines.",
                "Quels ordres sont affectés par la machine la plus chargée ?",
            ]
        ),
        "data": {
            "machine_loads": [
                {
                    "machine_id": machine,
                    "load_minutes": minutes,
                }
                for machine, minutes in ranked
            ],
        },
    }


# ============================================================================
# MATERIAL ANALYSIS
# ============================================================================

def _critical_materials(
    materials: list[Material],
) -> list[Material]:

    critical = [
        material
        for material in materials
        if float(material.on_hand_qty or 0)
        < float(material.safety_stock_qty or 0)
    ]

    critical.sort(
        key=lambda material: (
            float(material.on_hand_qty or 0)
            - float(material.safety_stock_qty or 0)
        )
    )

    return critical


def _answer_material(
    question: str,
    material_id: str | None,
    materials: dict[str, Any],
    planning: list[PlanningResult],
    db: Session,
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    # ------------------------------------------------------------
    # Specific material
    # ------------------------------------------------------------

    if material_id:
        material = materials.get(material_id)

        if material is None:
            return {
                "answer": (
                    f"I could not find material {material_id}."
                    if not french
                    else
                    f"Je n'ai pas trouvé la matière {material_id}."
                ),
                "facts": [
                    f"Material requested: {material_id}",
                ],
                "intent": "material_detail",
                "run_id": run_id,
                "suggested_questions": [],
                "data": {},
            }

        shortage = None

        # The prediction service is intentionally called only for
        # the requested material.
        try:
            shortage = predict_material_shortage(
                db=db,
                material_id=material_id,
            )
        except TypeError:
            # Compatibility fallback if the project version exposes
            # a slightly different signature.
            try:
                shortage = predict_material_shortage(
                    db,
                    material_id,
                )
            except Exception:
                shortage = None
        except Exception:
            shortage = None

        on_hand = float(
            material.on_hand_qty or 0
        )

        safety = float(
            material.safety_stock_qty or 0
        )

        coverage = getattr(
            material,
            "coverage_days",
            None,
        )

        lead_time = getattr(
            material,
            "lead_time_days",
            None,
        )

        if french:
            answer = (
                f"**{material_id}** : stock actuel "
                f"**{_format_number(on_hand)}**."
            )

            answer += (
                f" Stock de sécurité : "
                f"**{_format_number(safety)}**."
            )

            if coverage is not None:
                answer += (
                    f" Couverture : "
                    f"**{float(coverage):.1f} jours**."
                )

            if lead_time is not None:
                answer += (
                    f" Lead time fournisseur : "
                    f"**{float(lead_time):.1f} jours**."
                )

            answer += "\n"

            if on_hand < safety:
                answer += (
                    "\n⚠️ La matière est actuellement "
                    "sous le stock de sécurité."
                )
            else:
                answer += (
                    "\nLe stock actuel est au-dessus "
                    "du stock de sécurité."
                )

            if shortage:
                answer += (
                    "\n\n**Prévision de rupture :**\n"
                    f"{_format_shortage_result(shortage, french=True)}"
                )

        else:
            answer = (
                f"**{material_id}**: current stock "
                f"**{_format_number(on_hand)}**."
            )

            answer += (
                f" Safety stock: "
                f"**{_format_number(safety)}**."
            )

            if coverage is not None:
                answer += (
                    f" Coverage: "
                    f"**{float(coverage):.1f} days**."
                )

            if lead_time is not None:
                answer += (
                    f" Supplier lead time: "
                    f"**{float(lead_time):.1f} days**."
                )

            answer += "\n"

            if on_hand < safety:
                answer += (
                    "\n⚠️ The material is currently "
                    "below safety stock."
                )
            else:
                answer += (
                    "\nCurrent stock is above safety stock."
                )

            if shortage:
                answer += (
                    "\n\n**Shortage prediction:**\n"
                    f"{_format_shortage_result(shortage, french=False)}"
                )

        return {
            "answer": answer,
            "facts": [
                f"Material: {material_id}",
                f"Stock: {on_hand:g}",
                f"Safety stock: {safety:g}",
                f"Run: {run_id}",
            ],
            "intent": "material_detail",
            "run_id": run_id,
            "suggested_questions": (
                [
                    f"When will {material_id} run out?",
                    f"Which orders are affected by {material_id}?",
                    "Which materials are currently critical?",
                ]
                if not french
                else
                [
                    f"Quand {material_id} sera-t-elle en rupture ?",
                    f"Quels ordres sont affectés par {material_id} ?",
                    "Quelles matières sont actuellement critiques ?",
                ]
            ),
            "data": {
                "material_id": material_id,
                "on_hand_qty": on_hand,
                "safety_stock_qty": safety,
                "coverage_days": coverage,
                "lead_time_days": lead_time,
                "shortage_prediction": shortage,
            },
        }

    # ------------------------------------------------------------
    # General material risk
    # ------------------------------------------------------------

    material_rows = list(materials.values())
    critical = _critical_materials(material_rows)

    if french:
        if not critical:
            answer = (
                "Aucune matière n'est actuellement sous le stock "
                "de sécurité."
            )
        else:
            lines = []

            for material in critical[:10]:
                coverage = getattr(
                    material,
                    "coverage_days",
                    None,
                )

                coverage_text = (
                    f"{float(coverage):.1f} j"
                    if coverage is not None
                    else "N/A"
                )

                lines.append(
                    f"- {material.material_id}: "
                    f"stock {_format_number(material.on_hand_qty)} "
                    f"< sécurité {_format_number(material.safety_stock_qty)} "
                    f"(couverture {coverage_text})"
                )

            answer = (
                "Les matières actuellement sous leur stock de sécurité "
                "sont :\n\n"
                + "\n".join(lines)
            )

            answer += (
                "\n\n⚠️ Ceci est un indicateur de risque actuel. "
                "Une date exacte de rupture doit intégrer la consommation "
                "future et les réapprovisionnements."
            )
    else:
        if not critical:
            answer = (
                "No material is currently below its safety-stock threshold."
            )
        else:
            lines = []

            for material in critical[:10]:
                coverage = getattr(
                    material,
                    "coverage_days",
                    None,
                )

                coverage_text = (
                    f"{float(coverage):.1f} d"
                    if coverage is not None
                    else "N/A"
                )

                lines.append(
                    f"- {material.material_id}: "
                    f"stock {_format_number(material.on_hand_qty)} "
                    f"< safety {_format_number(material.safety_stock_qty)} "
                    f"(coverage {coverage_text})"
                )

            answer = (
                "The materials currently below safety stock are:\n\n"
                + "\n".join(lines)
            )

            answer += (
                "\n\n⚠️ This is a current risk indicator. "
                "An exact shortage date requires future consumption "
                "and replenishment information."
            )

    return {
        "answer": answer,
        "facts": [
            f"Critical materials: {len(critical)}",
            f"Materials checked: {len(material_rows)}",
            f"Run: {run_id}",
        ],
        "intent": "material_risk",
        "run_id": run_id,
        "suggested_questions": (
            [
                "Which material will run out first?",
                "Which materials have the shortest coverage?",
                "Which orders are affected by material shortages?",
            ]
            if not french
            else
            [
                "Quelle matière sera en rupture en premier ?",
                "Quelles matières ont la couverture la plus faible ?",
                "Quels ordres sont affectés par les ruptures matière ?",
            ]
        ),
        "data": {
            "critical_materials": [
                {
                    "material_id": material.material_id,
                    "on_hand_qty": float(
                        material.on_hand_qty or 0
                    ),
                    "safety_stock_qty": float(
                        material.safety_stock_qty or 0
                    ),
                    "coverage_days": getattr(
                        material,
                        "coverage_days",
                        None,
                    ),
                }
                for material in critical
            ],
        },
    }


def _format_shortage_result(
    result: Any,
    french: bool,
) -> str:

    if result is None:
        return (
            "No shortage prediction is available."
            if not french
            else
            "Aucune prévision de rupture n'est disponible."
        )

    if isinstance(result, dict):
        # Try the most common names without assuming
        # one exact implementation.
        shortage_date = (
            result.get("shortage_date")
            or result.get("expected_shortage_date")
            or result.get("predicted_shortage_date")
        )

        lead_time = (
            result.get("lead_time_days")
            or result.get("supplier_lead_time_days")
        )

        affected = (
            result.get("affected_orders")
            or result.get("affected_order_ids")
            or []
        )

        daily = (
            result.get("daily_consumption")
            or result.get("avg_daily_consumption")
        )

        parts = []

        if shortage_date:
            parts.append(
                (
                    f"Date de rupture estimée : {shortage_date}"
                    if french
                    else
                    f"Estimated shortage date: {shortage_date}"
                )
            )

        if daily is not None:
            parts.append(
                (
                    f"Consommation quotidienne : {daily}"
                    if french
                    else
                    f"Daily consumption: {daily}"
                )
            )

        if lead_time is not None:
            parts.append(
                (
                    f"Lead time : {lead_time} jours"
                    if french
                    else
                    f"Lead time: {lead_time} days"
                )
            )

        if affected:
            parts.append(
                (
                    "Ordres affectés : "
                    + ", ".join(
                        str(item)
                        for item in affected[:10]
                    )
                    if french
                    else
                    "Affected orders: "
                    + ", ".join(
                        str(item)
                        for item in affected[:10]
                    )
                )
            )

        if parts:
            return "\n".join(parts)

    return str(result)


# ============================================================================
# ORDER RISK LIST
# ============================================================================

def _answer_risk_list(
    risk_map: dict[str, dict[str, Any]],
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    ranked = _rank_risk_orders(risk_map)
    top = ranked[:10]

    if not top:
        answer = (
            "No order-risk data is currently available."
            if not french
            else
            "Aucune donnée de risque commande n'est actuellement disponible."
        )
    else:
        lines = []

        for order_id, data in top:
            risk = str(
                data.get("risk")
                or "LOW"
            ).upper()

            delay = float(
                data.get("delay_hours")
                or 0
            )

            lines.append(
                f"{order_id}: {risk} — {delay:.1f} h"
            )

        if french:
            answer = (
                "Les commandes présentant les risques les plus élevés "
                "dans le run actuel sont :\n\n"
                + "\n".join(
                    f"{index}. {line}"
                    for index, line in enumerate(lines, 1)
                )
            )
        else:
            answer = (
                "The highest-risk orders in the active run are:\n\n"
                + "\n".join(
                    f"{index}. {line}"
                    for index, line in enumerate(lines, 1)
                )
            )

    return {
        "answer": answer,
        "facts": [
            f"Orders analyzed: {len(risk_map)}",
            f"Run: {run_id}",
        ],
        "intent": "order_risk_list",
        "run_id": run_id,
        "suggested_questions": (
            [
                "Why is the highest-risk order late?",
                "Which materials are causing the risks?",
                "Which orders are urgent?",
            ]
            if not french
            else
            [
                "Pourquoi la commande la plus risquée est en retard ?",
                "Quelles matières causent les risques ?",
                "Quelles commandes sont urgentes ?",
            ]
        ),
        "data": {
            "orders": [
                {
                    "order_id": order_id,
                    "risk": str(
                        data.get("risk")
                        or "LOW"
                    ).upper(),
                    "delay_hours": float(
                        data.get("delay_hours")
                        or 0
                    ),
                }
                for order_id, data in ranked
            ],
        },
    }


# ============================================================================
# KPI ANALYSIS
# ============================================================================

def _answer_kpi(
    run: OptimizationRun,
    planning: list[PlanningResult],
    risk_map: dict[str, dict[str, Any]],
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    processing = sum(
        float(row.processing_minutes or 0)
        for row in planning
    )

    setup = sum(
        float(row.setup_minutes or 0)
        for row in planning
    )

    late_orders = {
        order_id
        for order_id, data in risk_map.items()
        if float(data.get("delay_hours") or 0) > 0
    }

    objective = getattr(
        run,
        "objective_value",
        None,
    )

    status = (
        getattr(run, "solver_status", None)
        or getattr(run, "status", None)
        or "UNKNOWN"
    )

    if french:
        answer = (
            "### KPIs du plan actuel\n\n"
            f"- Opérations planifiées : **{len(planning)}**\n"
            f"- Temps de production : **{processing / 60:.1f} h**\n"
            f"- Temps de setup : **{setup / 60:.1f} h**\n"
            f"- Commandes avec retard positif : **{len(late_orders)}**\n"
            f"- Statut solver : **{status}**"
        )

        if objective is not None:
            answer += (
                f"\n- Objective CP-SAT : **{objective}**"
            )
    else:
        answer = (
            "### Current plan KPIs\n\n"
            f"- Scheduled operations: **{len(planning)}**\n"
            f"- Processing time: **{processing / 60:.1f} h**\n"
            f"- Setup time: **{setup / 60:.1f} h**\n"
            f"- Orders with positive delay: **{len(late_orders)}**\n"
            f"- Solver status: **{status}**"
        )

        if objective is not None:
            answer += (
                f"\n- CP-SAT objective: **{objective}**"
            )

    return {
        "answer": answer,
        "facts": [
            f"Run: {run_id}",
            f"Operations: {len(planning)}",
            f"Late orders: {len(late_orders)}",
        ],
        "intent": "kpi",
        "run_id": run_id,
        "suggested_questions": (
            [
                "Explain the current production plan.",
                "Which machines are most loaded?",
                "Which orders are at highest risk?",
            ]
            if not french
            else
            [
                "Explique le plan de production actuel.",
                "Quelles machines sont les plus chargées ?",
                "Quelles commandes présentent le plus de risques ?",
            ]
        ),
        "data": {
            "processing_hours": processing / 60,
            "setup_hours": setup / 60,
            "late_orders": len(late_orders),
            "operation_count": len(planning),
            "solver_status": str(status),
            "objective_value": objective,
        },
    }


# ============================================================================
# PLAN SUMMARY
# ============================================================================

def _answer_plan_summary(
    run: OptimizationRun,
    planning: list[PlanningResult],
    risk_map: dict[str, dict[str, Any]],
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    machines = {
        str(row.machine_id)
        for row in planning
        if row.machine_id
    }

    orders = {
        str(row.order_id)
        for row in planning
        if row.order_id
    }

    processing = sum(
        float(row.processing_minutes or 0)
        for row in planning
    )

    setup = sum(
        float(row.setup_minutes or 0)
        for row in planning
    )

    late = {
        order_id
        for order_id, data in risk_map.items()
        if float(data.get("delay_hours") or 0) > 0
    }

    status = (
        getattr(run, "solver_status", None)
        or getattr(run, "status", None)
        or "UNKNOWN"
    )

    if french:
        answer = (
            "### Vue du plan actuel\n\n"
            f"Le plan contient **{len(planning)} opérations** "
            f"réparties sur **{len(machines)} machines** "
            f"pour **{len(orders)} commandes**.\n\n"
            f"- Temps de production : **{processing / 60:.1f} h**\n"
            f"- Temps de setup : **{setup / 60:.1f} h**\n"
            f"- Commandes avec retard positif : **{len(late)}**\n"
            f"- Statut solver : **{status}**\n\n"
            "Le plan est issu du moteur CP-SAT et respecte les "
            "contraintes représentées dans le modèle, notamment "
            "le routage, l'affectation machine, les setups, les "
            "priorités et les contraintes matière intégrées."
        )
    else:
        answer = (
            "### Current production plan\n\n"
            f"The plan contains **{len(planning)} operations** "
            f"across **{len(machines)} machines** "
            f"for **{len(orders)} orders**.\n\n"
            f"- Processing time: **{processing / 60:.1f} h**\n"
            f"- Setup time: **{setup / 60:.1f} h**\n"
            f"- Orders with positive delay: **{len(late)}**\n"
            f"- Solver status: **{status}**\n\n"
            "The plan is generated by the CP-SAT engine and reflects "
            "the constraints represented in the model, including "
            "routing, machine assignment, setups, priorities and "
            "integrated material constraints."
        )

    return {
        "answer": answer,
        "facts": [
            f"Solver: {status}",
            f"Operations: {len(planning)}",
            f"Machines: {len(machines)}",
            f"Orders: {len(orders)}",
            f"Run: {run_id}",
        ],
        "intent": "plan_summary",
        "run_id": run_id,
        "suggested_questions": (
            [
                "Which orders are most at risk?",
                "Which machine is the bottleneck?",
                "Which materials are critical?",
            ]
            if not french
            else
            [
                "Quelles commandes sont les plus à risque ?",
                "Quelle machine est le goulot ?",
                "Quelles matières sont critiques ?",
            ]
        ),
        "data": {
            "operation_count": len(planning),
            "machine_count": len(machines),
            "order_count": len(orders),
            "processing_hours": processing / 60,
            "setup_hours": setup / 60,
            "late_orders": len(late),
            "solver_status": str(status),
        },
    }


# ============================================================================
# RECOMMENDATIONS
# ============================================================================

def _answer_recommendation(
    planning: list[PlanningResult],
    risk_map: dict[str, dict[str, Any]],
    materials: dict[str, Any],
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    ranked_risks = _rank_risk_orders(risk_map)

    critical_materials = _critical_materials(
        list(materials.values())
    )

    machine_loads = _machine_loads(planning)

    ranked_machines = sorted(
        machine_loads.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    recommendations = []

    if ranked_risks:
        top_order, top_data = ranked_risks[0]

        risk = str(
            top_data.get("risk")
            or "LOW"
        ).upper()

        delay = float(
            top_data.get("delay_hours")
            or 0
        )

        if delay > 0 or risk in ("HIGH", "CRITICAL"):
            if french:
                recommendations.append(
                    f"Prioriser l'analyse de {top_order} "
                    f"({risk}, retard {delay:.1f} h)."
                )
            else:
                recommendations.append(
                    f"Prioritize the analysis of {top_order} "
                    f"({risk}, {delay:.1f} h delay)."
                )

    if critical_materials:
        material = critical_materials[0]

        if french:
            recommendations.append(
                f"Vérifier immédiatement le réapprovisionnement de "
                f"{material.material_id}, actuellement sous le stock "
                f"de sécurité."
            )
        else:
            recommendations.append(
                f"Check replenishment for {material.material_id}, "
                f"currently below safety stock."
            )

    if ranked_machines:
        machine, minutes = ranked_machines[0]

        if french:
            recommendations.append(
                f"Surveiller {machine}, qui présente la plus forte "
                f"charge planifiée ({minutes / 60:.1f} h)."
            )
        else:
            recommendations.append(
                f"Monitor {machine}, which has the highest scheduled "
                f"load ({minutes / 60:.1f} h)."
            )

    if not recommendations:
        if french:
            recommendations.append(
                "Aucune action prioritaire évidente n'est identifiée "
                "à partir des indicateurs disponibles."
            )
        else:
            recommendations.append(
                "No obvious priority action is identified from "
                "the available indicators."
            )

    if french:
        answer = (
            "### Actions recommandées\n\n"
            + "\n".join(
                f"{index}. {item}"
                for index, item in enumerate(
                    recommendations,
                    1,
                )
            )
        )
    else:
        answer = (
            "### Recommended actions\n\n"
            + "\n".join(
                f"{index}. {item}"
                for index, item in enumerate(
                    recommendations,
                    1,
                )
            )
        )

    return {
        "answer": answer,
        "facts": [
            f"Risk orders analyzed: {len(risk_map)}",
            f"Critical materials: {len(critical_materials)}",
            f"Machines scheduled: {len(machine_loads)}",
            f"Run: {run_id}",
        ],
        "intent": "recommendation",
        "run_id": run_id,
        "suggested_questions": (
            [
                "Why is the highest-risk order late?",
                "Which material should I replenish first?",
                "Which machine is the bottleneck?",
            ]
            if not french
            else
            [
                "Pourquoi la commande la plus risquée est en retard ?",
                "Quelle matière dois-je réapprovisionner en premier ?",
                "Quelle machine est le goulot ?",
            ]
        ),
        "data": {
            "recommendations": recommendations,
        },
    }


# ============================================================================
# SUPPLIER / PROCUREMENT ANALYSIS
# ============================================================================

def _answer_supplier_risk(
    db: Session,
    materials: dict[str, Any],
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    # ProcurementPlan is already part of the current system.
    # We use only fields known to exist from the current application.
    try:
        procurement_rows = (
            db.query(ProcurementPlan)
            .filter(ProcurementPlan.run_id == run_id)
            .all()
        )
    except Exception:
        procurement_rows = []

    if procurement_rows:
        # Group by supplier where possible.
        supplier_data: dict[str, dict[str, float]] = defaultdict(
            lambda: {
                "lines": 0,
                "qty": 0.0,
                "late": 0.0,
            }
        )

        for row in procurement_rows:
            supplier_id = getattr(
                row,
                "supplier_id",
                None,
            )

            if supplier_id is None:
                supplier_id = "UNKNOWN"

            key = str(supplier_id)

            supplier_data[key]["lines"] += 1

            qty = getattr(
                row,
                "order_qty",
                None,
            )

            if qty is None:
                qty = getattr(
                    row,
                    "planned_qty",
                    0,
                )

            try:
                supplier_data[key]["qty"] += float(
                    qty or 0
                )
            except (TypeError, ValueError):
                pass

            late_flag = getattr(
                row,
                "is_late",
                None,
            )

            if late_flag:
                supplier_data[key]["late"] += 1

        ranked = sorted(
            supplier_data.items(),
            key=lambda item: (
                item[1]["late"],
                item[1]["qty"],
            ),
            reverse=True,
        )

        lines = []

        for supplier_id, data in ranked[:10]:
            lines.append(
                f"{supplier_id}: "
                f"{int(data['lines'])} lines, "
                f"{int(data['late'])} late"
            )

        if french:
            answer = (
                "Les données d'approvisionnement disponibles "
                "par fournisseur sont :\n\n"
                + "\n".join(lines)
            )
        else:
            answer = (
                "Available procurement data by supplier:\n\n"
                + "\n".join(lines)
            )

        return {
            "answer": answer,
            "facts": [
                f"Procurement lines: {len(procurement_rows)}",
                f"Suppliers analyzed: {len(supplier_data)}",
                f"Run: {run_id}",
            ],
            "intent": "supplier_risk",
            "run_id": run_id,
            "suggested_questions": (
                [
                    "Which materials have the longest lead time?",
                    "Which supplier affects the most critical materials?",
                    "Which orders are affected by procurement risks?",
                ]
                if not french
                else
                [
                    "Quelles matières ont le plus long lead time ?",
                    "Quel fournisseur affecte le plus de matières critiques ?",
                    "Quels ordres sont affectés par les risques d'approvisionnement ?",
                ]
            ),
            "data": {
                "suppliers": supplier_data,
            },
        }

    # Fallback based on material lead times.
    supplier_materials: dict[str, list[Any]] = defaultdict(list)

    for material in materials.values():
        supplier_id = getattr(
            material,
            "supplier_id",
            None,
        )

        if supplier_id is not None:
            supplier_materials[str(supplier_id)].append(
                material
            )

    ranked_supplier = sorted(
        supplier_materials.items(),
        key=lambda item: max(
            float(
                getattr(
                    material,
                    "lead_time_days",
                    0,
                )
                or 0
            )
            for material in item[1]
        ),
        reverse=True,
    )

    if not ranked_supplier:
        if french:
            answer = (
                "Aucune donnée fournisseur exploitable n'est "
                "actuellement disponible."
            )
        else:
            answer = (
                "No usable supplier information is currently available."
            )
    else:
        lines = []

        for supplier_id, supplier_material_list in ranked_supplier[:8]:
            max_lead = max(
                float(
                    getattr(
                        material,
                        "lead_time_days",
                        0,
                    )
                    or 0
                )
                for material in supplier_material_list
            )

            lines.append(
                f"{supplier_id}: "
                f"{len(supplier_material_list)} materials, "
                f"max lead time {max_lead:.1f} days"
            )

        if french:
            answer = (
                "Les fournisseurs associés aux plus longs lead times "
                "matière sont :\n\n"
                + "\n".join(lines)
            )
        else:
            answer = (
                "Suppliers associated with the longest material "
                "lead times are:\n\n"
                + "\n".join(lines)
            )

    return {
        "answer": answer,
        "facts": [
            f"Materials checked: {len(materials)}",
            f"Run: {run_id}",
        ],
        "intent": "supplier_risk",
        "run_id": run_id,
        "suggested_questions": (
            [
                "Which materials have the longest lead time?",
                "Which materials are currently critical?",
                "Which orders are affected by supply risk?",
            ]
            if not french
            else
            [
                "Quelles matières ont le plus long lead time ?",
                "Quelles matières sont actuellement critiques ?",
                "Quels ordres sont affectés par le risque d'approvisionnement ?",
            ]
        ),
        "data": {},
    }


# ============================================================================
# HELP
# ============================================================================

def _answer_help(
    run_id: str,
    french: bool,
) -> dict[str, Any]:

    if french:
        answer = (
            "Je peux analyser directement les données de planification "
            "actuelles.\n\n"
            "Vous pouvez me demander :\n\n"
            "- Pourquoi SO-001 est en retard ?\n"
            "- Quelles commandes présentent le plus de risques ?\n"
            "- Quelle machine est la plus chargée ?\n"
            "- Quelle matière risque la rupture ?\n"
            "- Quand MAT-023 sera en rupture ?\n"
            "- Quels fournisseurs présentent un risque ?\n"
            "- Explique le plan de production actuel.\n"
            "- Quels sont les KPI du plan ?\n"
            "- Que dois-je faire en priorité ?"
        )
    else:
        answer = (
            "I can directly analyze the current planning data.\n\n"
            "You can ask me:\n\n"
            "- Why is SO-001 late?\n"
            "- Which orders have the highest risk?\n"
            "- Which machine is most loaded?\n"
            "- Which material may run out?\n"
            "- When will MAT-023 run out?\n"
            "- Which suppliers present a risk?\n"
            "- Explain the current production plan.\n"
            "- What are the plan KPIs?\n"
            "- What should I do first?"
        )

    return {
        "answer": answer,
        "facts": [
            "Data-grounded planning assistant",
            f"Run: {run_id}",
        ],
        "intent": "help",
        "run_id": run_id,
        "suggested_questions": (
            [
                "Why is the highest-risk order late?",
                "Which machine is the bottleneck?",
                "Which material is most critical?",
            ]
            if not french
            else
            [
                "Pourquoi la commande la plus risquée est en retard ?",
                "Quelle machine est le goulot ?",
                "Quelle matière est la plus critique ?",
            ]
        ),
        "data": {},
    }


# ============================================================================
# MAIN SERVICE
# ============================================================================

def ask_planning_assistant(
    db: Session,
    question: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Main service entry point.

    Compatible with:
        POST /assistant/ask

    Parameters
    ----------
    db:
        SQLAlchemy database session.

    question:
        User's natural-language question.

    run_id:
        Optional optimization run ID.
        If omitted, latest usable run is selected.
    """

    question = str(question or "").strip()

    if not question:
        return {
            "answer": "Please enter a question.",
            "facts": [],
            "intent": "empty",
            "run_id": run_id,
            "suggested_questions": [
                "Which orders have the highest risk?",
                "Which machines are most loaded?",
                "Which materials are critical?",
            ],
            "data": {},
        }

    french = _is_french(question)

    # ------------------------------------------------------------
    # Select run
    # ------------------------------------------------------------

    run = _select_run(
        db=db,
        requested_run_id=run_id,
    )

    if run is None:
        if french:
            answer = (
                "Je peux analyser les données de planification "
                "dès qu'un run d'optimisation est disponible. "
                "Lancez d'abord l'optimiseur."
            )
        else:
            answer = (
                "I can analyze the planning data once an optimization "
                "run is available. Please run the optimizer first."
            )

        return {
            "answer": answer,
            "facts": [],
            "intent": "no_run",
            "run_id": None,
            "suggested_questions": [],
            "data": {},
        }

    active_run_id = str(run.run_id)

    # ------------------------------------------------------------
    # Load real system data
    # ------------------------------------------------------------

    planning = _load_planning(
        db=db,
        run_id=active_run_id,
    )

    risk_map = build_order_risk_map(
        db,
        active_run_id,
    )

    orders = _load_orders(db)

    machine_rows = db.query(Machine).all()

    machines = {
        str(machine.machine_id): machine
        for machine in machine_rows
    }

    material_rows = db.query(Material).all()

    materials = {
        str(material.material_id): material
        for material in material_rows
    }

    # ------------------------------------------------------------
    # Detect entities
    # ------------------------------------------------------------

    order_id = _extract_order_id(
        question,
        orders,
    )

    machine_id = _extract_machine_id(
        question,
        machines,
    )

    material_id = _extract_material_id(
        question,
        materials,
    )

    # ------------------------------------------------------------
    # Detect intent
    # ------------------------------------------------------------

    intent = _detect_intent(
        question=question,
        order_id=order_id,
        machine_id=machine_id,
        material_id=material_id,
    )

    # ------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------

    if intent == "greeting":
        if french:
            answer = (
                "Bonjour 👋 Je suis votre assistant de planification. "
                "Je peux analyser les commandes, les machines, les "
                "matières, les risques et le plan CP-SAT actuel."
            )
        else:
            answer = (
                "Hello 👋 I am your planning assistant. "
                "I can analyze orders, machines, materials, risks "
                "and the current CP-SAT production plan."
            )

        return {
            "answer": answer,
            "facts": [
                f"Run: {active_run_id}",
            ],
            "intent": "greeting",
            "run_id": active_run_id,
            "suggested_questions": (
                [
                    "Which orders have the highest risk?",
                    "Which machines are most loaded?",
                    "Which materials are critical?",
                ]
                if not french
                else
                [
                    "Quelles commandes sont les plus à risque ?",
                    "Quelles machines sont les plus chargées ?",
                    "Quelles matières sont critiques ?",
                ]
            ),
            "data": {},
        }

    if intent in ("order_risk", "order_detail") and order_id:
        return _answer_order(
            question=question,
            order_id=order_id,
            orders=orders,
            planning=planning,
            risk_map=risk_map,
            run_id=active_run_id,
            french=french,
        )

    if intent in ("machine_detail", "machine_load"):
        return _answer_machine(
            question=question,
            machine_id=machine_id,
            machines=machines,
            planning=planning,
            run_id=active_run_id,
            french=french,
        )

    if intent in ("material_detail", "material_risk"):
        return _answer_material(
            question=question,
            material_id=material_id,
            materials=materials,
            planning=planning,
            db=db,
            run_id=active_run_id,
            french=french,
        )

    if intent == "order_risk_list":
        return _answer_risk_list(
            risk_map=risk_map,
            run_id=active_run_id,
            french=french,
        )

    if intent == "kpi":
        return _answer_kpi(
            run=run,
            planning=planning,
            risk_map=risk_map,
            run_id=active_run_id,
            french=french,
        )

    if intent == "plan_summary":
        return _answer_plan_summary(
            run=run,
            planning=planning,
            risk_map=risk_map,
            run_id=active_run_id,
            french=french,
        )

    if intent == "recommendation":
        return _answer_recommendation(
            planning=planning,
            risk_map=risk_map,
            materials=materials,
            run_id=active_run_id,
            french=french,
        )

    if intent == "supplier_risk":
        return _answer_supplier_risk(
            db=db,
            materials=materials,
            run_id=active_run_id,
            french=french,
        )

    if intent == "help":
        return _answer_help(
            run_id=active_run_id,
            french=french,
        )

    # ------------------------------------------------------------
    # Generic fallback
    # ------------------------------------------------------------

    if french:
        answer = (
            "Je n'ai pas identifié précisément la demande. "
            "Je peux néanmoins analyser les commandes, les risques, "
            "les machines, les matières, les fournisseurs et le plan actuel."
        )
    else:
        answer = (
            "I could not identify the request precisely. "
            "I can analyze orders, risks, machines, materials, "
            "suppliers and the current production plan."
        )

    return {
        "answer": answer,
        "facts": [
            "Data-grounded planning assistant",
            f"Run: {active_run_id}",
        ],
        "intent": "fallback",
        "run_id": active_run_id,
        "suggested_questions": (
            [
                "Which orders have the highest risk?",
                "Which machines are most loaded?",
                "Which materials are critical?",
                "Explain the current production plan.",
            ]
            if not french
            else
            [
                "Quelles commandes sont les plus à risque ?",
                "Quelles machines sont les plus chargées ?",
                "Quelles matières sont critiques ?",
                "Explique le plan de production actuel.",
            ]
        ),
        "data": {},
    }

