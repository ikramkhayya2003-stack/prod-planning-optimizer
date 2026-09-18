# Installation Windows — corrected version

## Backend

Open PowerShell in the backend folder:

```powershell
cd C:\path\to\production_optimizer_section3_COMPLETE
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check:

http://127.0.0.1:8000/health

Swagger:

http://127.0.0.1:8000/docs

## Frontend

Open a second PowerShell:

```powershell
cd C:\path\to\production_optimizer_frontend_v3
npm install
npm run dev
```

Open:

http://127.0.0.1:5173

The frontend and backend both use the same localStorage keys for the active optimization run.
