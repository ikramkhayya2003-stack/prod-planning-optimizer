from sqlalchemy.orm import Session

from app.models import (
    BreakdownEvent,
    OptimizationRun,
    ScenarioOrder,
)


def save_run(
    db: Session,
    run: OptimizationRun,
):
    db.add(run)
    db.commit()
    db.refresh(run)

    return run


def get_run(
    db: Session,
    run_id: str,
):
    return (
        db.query(OptimizationRun)
        .filter(
            OptimizationRun.run_id == run_id
        )
        .first()
    )


def save_breakdown(
    db: Session,
    event: BreakdownEvent,
):
    db.add(event)
    db.commit()
    db.refresh(event)

    return event


def save_order(
    db: Session,
    order: ScenarioOrder,
):
    db.add(order)
    db.commit()
    db.refresh(order)

    return order