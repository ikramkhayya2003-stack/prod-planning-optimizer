# V2 — Integrated Production & Procurement

## What changed
- Added `Material_Suppliers` Excel sheet for multi-sourcing.
- Added MOQ, lot size, unit cost, lead time, daily supplier capacity, order cost and reliability.
- Added `consumption_operation_seq` to BOM so material consumption is tied to CUT/CRP/ASM operation start.
- CP-SAT now decides purchase quantity, purchase date and supplier. Receipt date is derived from supplier lead time.
- Supplier daily capacity, MOQ and lot size are enforced.
- Inventory balance uses operation-level material consumption.

## Important modeling note
Supplier capacity is interpreted within a supplier/material UOM family. Exact physical supplier capacity across mixed UOMs would require a common capacity unit.

## Reset/import
Run `python reset_and_import.py` after replacing the dataset with `production_optimizer_dataset_v2.xlsx`.
