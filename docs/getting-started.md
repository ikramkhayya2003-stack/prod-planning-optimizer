# Production Optimizer — clean startup

## 1. PostgreSQL
Create a database named `production_optimizer` and make sure the credentials in `backend/.env` are correct.

## 2. Python
Use a clean Python environment. From the `backend` folder:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Do not reuse the old `.venv` shipped in previous archives; virtual environments are OS/Python-version specific.

## 3. First clean import
Run `backend/RESET_AND_IMPORT.bat`. This clears old optimization runs, planning results, scenarios, simulated breakdowns and master data, then imports the bundled Excel dataset.

## 4. Start backend
Run `START_BACKEND.bat`. API: `http://127.0.0.1:8000`, docs: `http://127.0.0.1:8000/docs`.

## 5. Start frontend
Run `START_FRONTEND.bat`. Vite normally opens on `http://localhost:5173`.

## 6. Verify
Open `http://127.0.0.1:8000/health`. The response should contain `status: ok` and non-zero machine/material/order counts after import.

## Important
The frontend error `ERR_CONNECTION_REFUSED` on `/health`, `/machines`, `/materials` and `/optimize` means the API process is not listening on port 8000. Start the backend first.
