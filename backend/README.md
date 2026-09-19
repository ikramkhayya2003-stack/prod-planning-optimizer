# Production Optimizer - Section 3

Complete CP-SAT implementation for the automotive wiring production scheduling portfolio project.

## Files

- `optimizer_cp_sat.py` — complete CP-SAT engine
- `data_loader.py` — Excel loader for `production_optimizer_dataset_v2.xlsx`
- `run_example.py` — command-line launch
- `requirements.txt` — Python dependencies

## Windows

```powershell
cd C:\Users\hp\Desktop\production_optimizer_section3_complete
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

Run:

```powershell
python .\run_example.py --dataset C:\Users\hp\Desktop\production_optimizer_dataset_v2.xlsx --seconds 60 --workers 8
```

## Implemented

- BoolVar machine assignment
- Optional IntervalVar
- `add_exactly_one`
- `add_no_overlap`
- routing precedence
- sequence-dependent setup
- machine Circuit
- maintenance / breakdown intervals
- BOM and safety-stock constraints
- deterministic lead-time replenishment V1
- weighted normalized objective
- service / tardiness / setup / utilization / idle / inventory KPIs
