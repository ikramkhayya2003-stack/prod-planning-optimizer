from app.database import Base, engine

# Import all models so SQLAlchemy registers every table.
from app.models import (
    Supplier,
    Machine,
    Product,
    Material,
    Routing,
    BOM,
    Order,
    MachineEvent,
    MachineCalendar,
    SetupMatrix,
    OptimizationRun,
    ScenarioOrder,
    BreakdownEvent,
    MaterialSupplier,
    ProcurementPlan,
)


def create_tables():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_tables()
    print("All database tables created successfully.")