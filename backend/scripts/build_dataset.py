"""Build the canonical import workbook from the bundled source workbooks."""

from pathlib import Path

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = BACKEND_DIR / "excel"
OUTPUT_PATH = BACKEND_DIR / "production_optimizer_dataset_v2.xlsx"

SHEETS = {
    "Suppliers": "supplier.xlsx",
    "Material_Suppliers": "matirialsuppl.xlsx",
    "Machines": "machines.xlsx",
    "Products": "product.xlsx",
    "Materials": "materiel.xlsx",
    "Routing": "routing.xlsx",
    "BOM": "bom.xlsx",
    "Orders": "orders.xlsx",
    "Machine_Events": "machine event.xlsx",
    "Machine_Calendar": "machine calendier.xlsx",
    "Setup_Matrix": "matrice.xlsx",
}


def main() -> None:
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        for sheet_name, source_name in SHEETS.items():
            source_path = SOURCE_DIR / source_name
            if not source_path.exists():
                raise FileNotFoundError(f"Missing source workbook: {source_path}")

            pd.read_excel(source_path).to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
            )

    print(f"Created {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
