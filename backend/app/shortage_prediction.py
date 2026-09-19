
from __future__ import annotations

from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Material, Supplier


# ============================================================
# SHORTAGE PREDICTION RESULT
# ============================================================

@dataclass
class ShortagePrediction:

    material_id: str

    current_stock: float

    daily_consumption: float

    lead_time_days: float

    shortage_date: Optional[date]

    days_to_shortage: Optional[int]

    shortage_qty: float

    supplier_arrival_date: Optional[date]

    affected_orders: list[str]

    risk_level: str

    supplier_can_arrive_before_shortage: bool


# ============================================================
# GET MATERIAL
# ============================================================

def get_material(
    db: Session,
    material_id: str,
) -> Optional[Material]:

    return (
        db.query(Material)
        .filter(
            Material.material_id == material_id
        )
        .first()
    )


# ============================================================
# DAILY CONSUMPTION
# ============================================================

def get_daily_consumption(
    material: Material,
) -> float:
    """
    Utilise la consommation journalière déjà calculée
    dans le référentiel Material.
    """

    value = (
        material.avg_daily_requirement
        or 0
    )

    return max(
        float(value),
        0.0,
    )


# ============================================================
# CURRENT STOCK
# ============================================================

def get_current_stock(
    material: Material,
) -> float:
    """
    Stock actuel de la matière.

    Dans ton modèle :
        Material.on_hand_qty
    """

    value = (
        material.on_hand_qty
        or 0
    )

    return max(
        float(value),
        0.0,
    )


# ============================================================
# LEAD TIME
# ============================================================

def get_lead_time(
    material: Material,
) -> float:
    """
    Lead time fournisseur en jours.

    Dans ton modèle :
        Material.lead_time_days
    """

    value = (
        material.lead_time_days
        or 0
    )

    return max(
        float(value),
        0.0,
    )


# ============================================================
# FUTURE DEMAND
# ============================================================

def get_future_daily_demand(
    material: Material,
    day: int,
) -> float:
    """
    Estimation de la demande future.

    Ton modèle possède :
        horizon_requirement_qty

    et :
        avg_daily_requirement

    On utilise la consommation journalière comme
    projection de base.
    """

    daily = get_daily_consumption(
        material
    )

    return daily


# ============================================================
# SHORTAGE DATE
# ============================================================

def calculate_shortage_date(
    material: Material,
    calculation_date: date,
    horizon_days: int,
):
    """
    Projection jour par jour du stock.

    Stock(t+1) =
        Stock(t)
        - demande future
    """

    stock = get_current_stock(
        material
    )

    daily_consumption = get_daily_consumption(
        material
    )

    # Aucun besoin de projection
    if daily_consumption <= 0:

        return (
            None,
            None,
            0.0,
        )

    for day_number in range(
        0,
        horizon_days + 1,
    ):

        current_date = (
            calculation_date
            + timedelta(
                days=day_number
            )
        )

        demand = get_future_daily_demand(
            material,
            day_number,
        )

        stock -= demand

        if stock < 0:

            shortage_qty = abs(
                stock
            )

            return (
                current_date,
                day_number,
                shortage_qty,
            )

    return (
        None,
        None,
        0.0,
    )


# ============================================================
# RISK LEVEL
# ============================================================

def calculate_risk_level(
    days_to_shortage: Optional[int],
) -> str:

    if days_to_shortage is None:

        return "LOW"

    if days_to_shortage <= 3:

        return "CRITICAL"

    if days_to_shortage <= 7:

        return "HIGH"

    if days_to_shortage <= 15:

        return "MEDIUM"

    return "LOW"


# ============================================================
# MAIN PREDICTION
# ============================================================

def predict_material_shortage(
    db: Session,
    material_id: str,
    calculation_date: Optional[date] = None,
    horizon_days: int = 120,
) -> ShortagePrediction:

    # --------------------------------------------------------
    # Date de calcul
    # --------------------------------------------------------

    if calculation_date is None:

        calculation_date = date.today()

    # --------------------------------------------------------
    # Material
    # --------------------------------------------------------

    material = get_material(
        db,
        material_id,
    )

    if material is None:

        raise ValueError(
            f"Material '{material_id}' not found."
        )

    # --------------------------------------------------------
    # Current stock
    # --------------------------------------------------------

    current_stock = get_current_stock(
        material
    )

    # --------------------------------------------------------
    # Daily consumption
    # --------------------------------------------------------

    daily_consumption = get_daily_consumption(
        material
    )

    # --------------------------------------------------------
    # Lead time
    # --------------------------------------------------------

    lead_time_days = get_lead_time(
        material
    )

    # --------------------------------------------------------
    # Shortage projection
    # --------------------------------------------------------

    (
        shortage_date,
        days_to_shortage,
        shortage_qty,
    ) = calculate_shortage_date(
        material,
        calculation_date,
        horizon_days,
    )

    # --------------------------------------------------------
    # Supplier arrival
    # --------------------------------------------------------

    supplier_arrival_date = (
        calculation_date
        + timedelta(
            days=lead_time_days
        )
    )

    # --------------------------------------------------------
    # Supplier vs shortage
    # --------------------------------------------------------

    if shortage_date is None:

        supplier_can_arrive = True

    else:

        supplier_can_arrive = (
            supplier_arrival_date
            <= shortage_date
        )

    # --------------------------------------------------------
    # Risk
    # --------------------------------------------------------

    risk_level = calculate_risk_level(
        days_to_shortage
    )

    # --------------------------------------------------------
    # Affected orders
    # --------------------------------------------------------
    #
    # Ton modèle actuel ne contient pas encore
    # une relation Material -> Orders.
    #
    # Donc on ne fabrique PAS de faux order IDs.
    #
    # La liste reste vide jusqu'à l'intégration
    # de BOM + Orders + besoins matière.
    # --------------------------------------------------------

    affected_orders = []

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return ShortagePrediction(

        material_id=material_id,

        current_stock=current_stock,

        daily_consumption=daily_consumption,

        lead_time_days=lead_time_days,

        shortage_date=shortage_date,

        days_to_shortage=days_to_shortage,

        shortage_qty=shortage_qty,

        supplier_arrival_date=supplier_arrival_date,

        affected_orders=affected_orders,

        risk_level=risk_level,

        supplier_can_arrive_before_shortage=
            supplier_can_arrive,
    )


# ============================================================
# PREDICT ALL MATERIALS
# ============================================================

def predict_all_material_shortages(
    db: Session,
    calculation_date: Optional[date] = None,
    horizon_days: int = 120,
) -> list[ShortagePrediction]:
    """
    Calcule la prévision de rupture pour toutes
    les matières.
    """

    materials = (
        db.query(Material)
        .all()
    )

    results = []

    for material in materials:

        try:

            prediction = (
                predict_material_shortage(
                    db=db,
                    material_id=material.material_id,
                    calculation_date=calculation_date,
                    horizon_days=horizon_days,
                )
            )

            results.append(
                prediction
            )

        except Exception as error:

            print(
                f"[SHORTAGE PREDICTION] "
                f"Error for {material.material_id}: "
                f"{error}"
            )

    return results

