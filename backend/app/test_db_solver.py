from app.database import SessionLocal

from app.db_planning_loader import (
    load_planning_data_from_db,
)

from optimizer_cp_sat import (
    ObjectiveWeights,
    ProductionCPSATOptimizer,
)


def main():

    db = SessionLocal()

    try:

        print("=" * 80)
        print("DATABASE -> CP-SAT DIAGNOSTIC")
        print("=" * 80)

        # ----------------------------------------------------
        # LOAD DATA
        # ----------------------------------------------------

        print()
        print("[1] Loading PostgreSQL data...")

        data = load_planning_data_from_db(db)

        print(
            f"Machines  : {len(data.machines)}"
        )

        print(
            f"Products  : {len(data.products)}"
        )

        print(
            f"Orders    : {len(data.orders)}"
        )

        print(
            f"Materials : {len(data.materials)}"
        )

        print(
            "Routing   : "
            f"{sum(len(v) for v in data.routing.values())}"
        )

        print(
            "BOM       : "
            f"{sum(len(v) for v in data.bom.values())}"
        )

        print(
            f"Setups    : {len(data.setup_minutes)}"
        )

        print(
            f"Calendar  : {len(data.calendar_days)}"
        )

        print(
            f"Events    : {len(data.availability_events)}"
        )

        # ----------------------------------------------------
        # OBJECTIVE
        # ----------------------------------------------------

        print()
        print("[2] Creating objective...")

        objective = ObjectiveWeights(
            tardiness=0.50,
            setup=0.20,
            inventory=0.15,
            idle=0.15,

            reference_tardiness_min=50000,
            reference_setup_min=10000,
            reference_inventory_scaled=100000000,
            reference_idle_min=500000,
        )

        # ----------------------------------------------------
        # MODEL
        # ----------------------------------------------------

        print()
        print("[3] Building CP-SAT model...")

        optimizer = ProductionCPSATOptimizer(
            data,
            objective,
        )

        print(
            "[3] Model created."
        )

        # ----------------------------------------------------
        # SOLVE
        # ----------------------------------------------------

        print()
        print("[4] Starting CP-SAT...")
        print(
            "Time limit: 30 seconds"
        )

        result = optimizer.solve(
            max_time_seconds=30,
            num_workers=4,
            random_seed=42,
            log_search_progress=True,
        )

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        print()
        print("=" * 80)
        print("CP-SAT RESULT")
        print("=" * 80)

        print(
            f"Status       : {result.status}"
        )

        print(
            f"Objective    : {result.objective_value}"
        )

        print(
            f"Planning rows: "
            f"{len(result.planning_rows)}"
        )

        print(
            f"Order KPIs   : "
            f"{len(result.order_kpis)}"
        )

        print(
            f"Machine KPIs : "
            f"{len(result.machine_kpis)}"
        )

        print(
            f"Material KPIs: "
            f"{len(result.material_kpis)}"
        )

    except Exception as exc:

        import traceback

        print()
        print("=" * 80)
        print("ERROR")
        print("=" * 80)

        traceback.print_exc()

    finally:

        db.close()


if __name__ == "__main__":
    main()