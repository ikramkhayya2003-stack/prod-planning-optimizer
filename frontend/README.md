# Production Optimizer Frontend V3

This version fixes the main issue in the previous frontend:

- data pages now read PostgreSQL through FastAPI GET endpoints;
- Orders no longer depend on a completed optimization to display data;
- Machines, Materials and Products load independently;
- Products loads BOM + routing on demand;
- Data Management uses real file inputs, so Choose file opens the Windows file picker;
- Dashboard loads master data immediately and run KPIs after an optimization;
- run polling stops after COMPLETED or FAILED;
- Orders can export the currently filtered data to CSV;
- urgent orders and breakdown simulation remain connected to the existing backend.

## Run

```powershell
npm install
npm run dev
```

Backend:
`http://127.0.0.1:8000`

Frontend:
`http://127.0.0.1:5173`
