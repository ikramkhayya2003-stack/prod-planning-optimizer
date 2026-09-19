# Installation Windows

Ouvre PowerShell dans ce dossier :

```powershell
cd C:\path\to\prod-planning-optimizer\backend
```

Crée l'environnement :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Installe les dépendances :

```powershell
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

Vérifie OR-Tools :

```powershell
python -c "import ortools; from ortools.sat.python import cp_model; print('OR-Tools OK:', ortools.__version__)"
```

Lance le modèle :

```powershell
python .\run_example.py --dataset .\production_optimizer_dataset_v2.xlsx --seconds 60 --workers 8
```

La version OR-Tools utilisée est 9.15.6755. PyPI publie cette version pour CPython 3.9 à 3.14, notamment Windows x86-64. Si l'installation échoue, vérifie d'abord :

```powershell
python --version
```

Puis utilise Python 3.11, 3.12 ou 3.13 64-bit.
