import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";

import Layout from "./components/Layout";
import {
  getKpis,
  getPlanning,
  getRun,
  getLatestRun,
  healthCheck,
  startOptimization,
} from "./api";

import Dashboard from "./pages/Dashboard";
import Orders from "./pages/Orders";
import Planning from "./pages/Planning";
import GanttPage from "./pages/GanttPage";
import Machines from "./pages/Machines";
import Materials from "./pages/Materials";
import Products from "./pages/Products";
import Optimization from "./pages/Optimization";
import Scenarios from "./pages/Scenarios";
import Performance from "./pages/Performance";
import DataManagement from "./pages/DataManagement";
import Settings from "./pages/Settings";
import Assistant from "./pages/Assistant";

// One key for the whole application. The previous code used
// "production_optimizer_run_id" here while several pages used
// "latest_run_id", which caused the pages to lose the active run.
export const RUN_KEY = "latest_run_id";
export const RUN_STATUS_KEY = "latest_run_status";

export default function App() {
  const [health, setHealth] = useState(null);
  const [runId, setRunId] = useState(
    () => localStorage.getItem(RUN_KEY) || null,
  );
  const [runStatus, setRunStatus] = useState(
    () => localStorage.getItem(RUN_STATUS_KEY) || null,
  );
  const [kpis, setKpis] = useState(null);
  const [planning, setPlanning] = useState([]);
  const navigate = useNavigate();

  const refreshHealth = useCallback(async () => {
    try {
      const data = await healthCheck();
      setHealth(data);
    } catch (error) {
      console.error("Health check failed:", error);
      setHealth({ status: "offline", database: "offline" });
    }
  }, []);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth]);

  // Restore the latest run from PostgreSQL when localStorage is empty.
  useEffect(() => {
    if (runId) return;

    let cancelled = false;

    getLatestRun()
      .then((latest) => {
        if (cancelled || !latest?.run_id) return;
        setRunId(latest.run_id);
        setRunStatus(latest.status || null);
        localStorage.setItem(RUN_KEY, latest.run_id);
        localStorage.setItem(
          RUN_STATUS_KEY,
          latest.status || "",
        );
      })
      .catch((error) => {
        // 404 simply means that no optimization has been run yet.
        if (error?.response?.status !== 404) {
          console.error("Latest run loading failed:", error);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Poll the active run until it reaches a terminal state.
  useEffect(() => {
    if (!runId) return undefined;

    let cancelled = false;
    let timer = null;

    const poll = async () => {
      try {
        const run = await getRun(runId);
        if (cancelled) return;

        const status = String(run?.status || "READY").toUpperCase();
        setRunStatus(status);
        localStorage.setItem(RUN_STATUS_KEY, status);

        if (status === "COMPLETED") {
          const [k, p] = await Promise.all([
            getKpis(runId),
            getPlanning(runId),
          ]);

          if (!cancelled) {
            setKpis(k);
            setPlanning(p?.planning || []);
          }
          return;
        }

        if (status === "FAILED") return;

        timer = window.setTimeout(poll, 2000);
      } catch (error) {
        if (cancelled) return;

        // A temporary network/DB error must not be converted into a
        // false FAILED solver state. Retry instead.
        console.error("Run polling failed:", error);
        timer = window.setTimeout(poll, 3000);
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [runId]);

  const registerRun = useCallback((created) => {
    if (!created?.run_id) return;

    const id = created.run_id;
    const status = created.status || "QUEUED";

    setRunId(id);
    setRunStatus(status);
    setKpis(null);
    setPlanning([]);

    localStorage.setItem(RUN_KEY, id);
    localStorage.setItem(RUN_STATUS_KEY, status);
  }, []);

  const handleRunCreated = useCallback(
    (created) => {
      registerRun(created);
      navigate("/optimization");
    },
    [navigate, registerRun],
  );

  const quickOptimize = useCallback(async () => {
    try {
      const created = await startOptimization({
        max_time_seconds: 60,
        num_workers: 8,
        random_seed: 42,
        weights: {
          tardiness: 0.5,
          setup: 0.2,
          inventory: 0.15,
          idle: 0.15,
        },
      });

      registerRun(created);
    } catch (error) {
      console.error("Quick optimization failed:", error);
      // Keep the dashboard usable when the API is temporarily offline.
      setHealth((previous) => ({
        ...(previous || {}),
        status: "offline",
        database: "offline",
        error: error?.response?.data?.detail || error?.message || "API unavailable",
      }));
    }
  }, [registerRun]);

  return (
    <Layout apiOnline={health?.status === "ok"}>
      <Routes>
        <Route
          path="/"
          element={
            <Dashboard
              runId={runId}
              runStatus={runStatus}
              health={health}
              onOptimize={quickOptimize}
            />
          }
        />

        <Route path="/assistant" element={<Assistant runId={runId} />} />

        <Route path="/orders" element={<Orders />} />

        <Route
          path="/planning"
          element={
            <Planning
              planning={planning}
              runId={runId}
              runStatus={runStatus}
              onRefresh={() => runId && getPlanning(runId)}
            />
          }
        />

        <Route
  path="/gantt"
  element={
    <GanttPage
      planning={planning}
      runId={runId}
      onPlanningUpdated={setPlanning}
    />
  }
/>

        <Route
          path="/machines"
          element={<Machines runId={runId} kpis={kpis} />}
        />

        <Route
          path="/materials"
          element={<Materials runId={runId} kpis={kpis} />}
        />

        <Route path="/products" element={<Products />} />

        <Route
          path="/optimization"
          element={
            <Optimization
              runId={runId}
              runStatus={runStatus}
              kpis={kpis}
              onRunCreated={handleRunCreated}
            />
          }
        />

        <Route
          path="/scenarios"
          element={<Scenarios onRunCreated={handleRunCreated} />}
        />

        <Route
          path="/performance"
          element={<Performance runId={runId} kpis={kpis} />}
        />

        <Route path="/data" element={<DataManagement />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
