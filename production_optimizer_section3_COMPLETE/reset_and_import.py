"""Reset project operational data and import the canonical Excel dataset."""
from app.database import SessionLocal, Base, engine
from app.models import (
    PlanningResult, OrderKPI, MachineKPI, MaterialKPI, ProcurementPlan, OptimizationRun,
    ScenarioOrder, BreakdownEvent, SetupMatrix, BOM, Routing, Order,
    MachineCalendar, MachineEvent, MaterialSupplier, Material, Product, Machine, Supplier,
    MachineCapacity, StageCapacity, SetupExample,
)
from app.import_data import import_all_data
from app.config import DATASET_PATH

DEPENDENTS = (
    PlanningResult, OrderKPI, MachineKPI, MaterialKPI, ProcurementPlan, ScenarioOrder,
    BreakdownEvent, OptimizationRun,
)
MASTER = (
    SetupMatrix, BOM, Routing, Order, MachineCalendar, MachineEvent,
    MaterialSupplier, Material, Product, Machine, Supplier,
)

def reset_database():
    """Recreate the project schema so V2 columns/tables are guaranteed present."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    print("Resetting production optimizer database...")
    reset_database()
    print("Database cleared. Importing Excel dataset...")
    summary = import_all_data(DATASET_PATH)
    print("\nIMPORT SUMMARY")
    for k, v in summary.items():
        print(f"{k}: {v}")
