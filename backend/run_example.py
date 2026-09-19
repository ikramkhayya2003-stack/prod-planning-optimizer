from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_loader import load_excel
from optimizer_cp_sat import ObjectiveWeights, ProductionCPSATOptimizer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the automotive production CP-SAT optimizer."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "production_optimizer_dataset_v2.xlsx",
        help="Path to the generated Excel dataset.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=60.0,
        help="CP-SAT time limit in seconds.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of CP-SAT workers.",
    )
    args = parser.parse_args()

    dataset = args.dataset.expanduser().resolve()
    if not dataset.exists():
        raise FileNotFoundError(
            f"Excel dataset not found: {dataset}\n"
            "Example:\n"
            "  python run_example.py --dataset "
            "C:\\Users\\hp\\Desktop\\production_optimizer_dataset_v2.xlsx"
        )

    data = load_excel(str(dataset))

    # For the first demonstration we use explicit reference values.
    # After implementing EDD, replace these values by the real EDD KPIs.
    objective = ObjectiveWeights(
        tardiness=0.50,
        setup=0.20,
        inventory=0.15,
        idle=0.15,
        reference_tardiness_min=max(1, len(data.orders) * 8 * 60),
        reference_setup_min=10_000,
        reference_inventory_scaled=max(
            1,
            int(
                sum(m.on_hand_qty for m in data.materials.values())
                * 100
                * len(data.calendar_days)
            ),
        ),
        reference_idle_min=max(
            1,
            len(data.machines) * 16 * 60 * len(data.calendar_days),
        ),
    )

    optimizer = ProductionCPSATOptimizer(
        data,
        objective,
    )

    result = optimizer.solve(
        max_time_seconds=args.seconds,
        num_workers=args.workers,
        random_seed=42,
        log_search_progress=False,
    )

    print("\n=== CP-SAT RESULT ===")
    print("Status:", result.status)
    print("Objective:", result.objective_value)
    print("\n=== SUMMARY KPIs ===")
    print(json.dumps(result.summary_kpis, indent=2, default=str))

    print("\n=== FIRST 10 PLANNING ROWS ===")
    for row in result.planning_rows[:10]:
        print(row)


if __name__ == "__main__":
    main()
