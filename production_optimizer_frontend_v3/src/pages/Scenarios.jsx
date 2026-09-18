import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarPlus,
  CheckCircle2,
  Clock3,
  Gauge,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Truck,
} from "lucide-react";

import PageHeader from "../components/PageHeader";
import {
  getKpis,
  getLatestCompletedRun,
  getMachines,
  getMaterials,
  getRun,
  startOptimization,
} from "../api";

const DEFAULT_START = "2026-09-07";
const DEFAULT_END = "2026-10-16";

const WEIGHTS = {
  tardiness: 0.5,
  setup: 0.2,
  inventory: 0.15,
  idle: 0.15,
};

function getErrorMessage(error) {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join(", ");
  }

  if (detail && typeof detail === "object") {
    return detail.msg || detail.message || JSON.stringify(detail);
  }

  return error?.message || "Une erreur est survenue.";
}

function toDateInput(value) {
  return value || DEFAULT_START;
}

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00`);
  d.setDate(d.getDate() + Number(days));
  return d.toISOString().slice(0, 10);
}

function formatPct(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}%` : "—";
}

function formatNumber(value) {
  return Number.isFinite(Number(value))
    ? Number(value).toLocaleString("fr-FR", { maximumFractionDigits: 1 })
    : "—";
}

function normalizeKpis(kpis) {
  const summary = kpis?.summary || {};
  const machines = Array.isArray(kpis?.machines) ? kpis.machines : [];

  const utilizationValues = machines
    .map((m) => Number(m.utilization_pct))
    .filter(Number.isFinite);

  const avgUtilization = utilizationValues.length
    ? utilizationValues.reduce((a, b) => a + b, 0) / utilizationValues.length
    : null;

  return {
    serviceRate: Number(summary.service_rate_pct),
    lateOrders: Number(summary.late_orders),
    avgTardiness: Number(summary.avg_tardiness_hours),
    utilization: avgUtilization,
    setup: Number(summary.total_setup_min),
    inventory: Number(summary.avg_inventory_qty),
  };
}

export default function Scenarios({ onRunCreated }) {
  const [demand, setDemand] = useState(20);

  const [machine, setMachine] = useState("");
  const [machines, setMachines] = useState([]);
  const [breakdownDate, setBreakdownDate] = useState(DEFAULT_START);
  const [breakdownStart, setBreakdownStart] = useState("10:00");
  const [breakdownDuration, setBreakdownDuration] = useState(4);

  const [lead, setLead] = useState(5);
  const [supplier, setSupplier] = useState("");
  const [materials, setMaterials] = useState([]);

  const [planningStart, setPlanningStart] = useState(DEFAULT_START);
  const [planningEnd, setPlanningEnd] = useState(DEFAULT_END);
  const [includeWeekends, setIncludeWeekends] = useState(false);
  const [includeOvertime, setIncludeOvertime] = useState(false);

  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [baseline, setBaseline] = useState(null);
  const [scenarioResult, setScenarioResult] = useState(null);
  const [activeScenario, setActiveScenario] = useState(null);
  const [scenarioRunId, setScenarioRunId] = useState(null);
  const [runStatus, setRunStatus] = useState(null);

  const supplierIds = useMemo(
    () =>
      [...new Set(materials.map((m) => m?.supplier_id).filter(Boolean))].sort(),
    [materials],
  );

  const horizonValid =
    Boolean(planningStart) &&
    Boolean(planningEnd) &&
    planningEnd >= planningStart;

  useEffect(() => {
    let cancelled = false;

    async function loadReferenceData() {
      try {
        const [materialResponse, machineResponse, latest] = await Promise.all([
          getMaterials({ limit: 500 }),
          getMachines({ limit: 500 }),
          getLatestCompletedRun().catch(() => null),
        ]);

        if (cancelled) return;

        const materialRows =
          materialResponse?.materials ||
          materialResponse?.data ||
          (Array.isArray(materialResponse) ? materialResponse : []);

        const machineRows =
          machineResponse?.machines ||
          machineResponse?.data ||
          (Array.isArray(machineResponse) ? machineResponse : []);

        setMaterials(Array.isArray(materialRows) ? materialRows : []);
        setMachines(Array.isArray(machineRows) ? machineRows : []);

        if (machineRows?.length && !machine) {
          setMachine(machineRows[0].machine_id);
        }

        const supplierList = [
          ...new Set(
            (Array.isArray(materialRows) ? materialRows : [])
              .map((m) => m?.supplier_id)
              .filter(Boolean),
          ),
        ];

        if (supplierList.length && !supplier) {
          setSupplier(supplierList[0]);
        }

        if (latest?.run_id) {
          try {
            const latestKpis = await getKpis(latest.run_id);
            if (!cancelled) {
              setBaseline(normalizeKpis(latestKpis));
            }
          } catch {
            // No completed baseline yet.
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(getErrorMessage(err));
          setMaterials([]);
          setMachines([]);
        }
      }
    }

    loadReferenceData();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!scenarioRunId) return undefined;

    let cancelled = false;
    let timer;

    async function pollScenario() {
      try {
        const run = await getRun(scenarioRunId);
        if (cancelled) return;

        const status = String(run?.status || "").toUpperCase();
        setRunStatus(status);

        if (status === "COMPLETED") {
          const kpis = await getKpis(scenarioRunId);
          if (!cancelled) {
            setScenarioResult(normalizeKpis(kpis));
            setMessage("Scenario terminé. Les KPI ci-dessous proviennent du calcul CP-SAT.");
            setBusy(false);
          }
          return;
        }

        if (status === "FAILED") {
          if (!cancelled) {
            setError(
              run?.solver_status ||
                "Le solveur n'a pas trouvé de solution exploitable.",
            );
            setBusy(false);
          }
          return;
        }

        timer = window.setTimeout(pollScenario, 2000);
      } catch (err) {
        if (!cancelled) {
          setError(getErrorMessage(err));
          setBusy(false);
        }
      }
    }

    pollScenario();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [scenarioRunId]);

  function optimizationOptions(scenario) {
    return {
      max_time_seconds: 60,
      num_workers: 8,
      random_seed: 42,
      weights: WEIGHTS,
      planning_start_date: planningStart,
      planning_end_date: planningEnd,
      include_weekends: includeWeekends,
      include_overtime: includeOvertime,
      scenario,
    };
  }

  async function submitScenario(type, scenario) {
    if (!horizonValid) {
      setError("La date de fin doit être postérieure ou égale à la date de début.");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    setScenarioResult(null);
    setActiveScenario(type);
    setRunStatus("QUEUED");

    try {
      const run = await startOptimization(optimizationOptions(scenario));

      setScenarioRunId(run.run_id);
      setRunStatus(run.status || "QUEUED");
      onRunCreated?.(run);

      setMessage(
        "Scénario envoyé au moteur CP-SAT. Les résultats seront actualisés automatiquement.",
      );
    } catch (err) {
      setBusy(false);
      setRunStatus(null);
      setError(getErrorMessage(err));
      console.error("Scenario optimization failed:", err);
    }
  }

  async function runDemand() {
    await submitScenario("Demand Increase", {
      type: "demand_increase",
      demand_increase_pct: Number(demand),
    });
  }

  async function runBreakdown() {
    if (!machine) {
      setError("Aucune machine disponible.");
      return;
    }

    const start = `${breakdownDate}T${breakdownStart}:00`;
    const endDateTime = new Date(`${start}`);
    endDateTime.setHours(
      endDateTime.getHours() + Number(breakdownDuration),
    );

    const end = [
      endDateTime.getFullYear(),
      String(endDateTime.getMonth() + 1).padStart(2, "0"),
      String(endDateTime.getDate()).padStart(2, "0"),
    ].join("-") +
      "T" +
      [
        String(endDateTime.getHours()).padStart(2, "0"),
        String(endDateTime.getMinutes()).padStart(2, "0"),
      ].join(":") +
      ":00";

    await submitScenario("Machine Unavailable", {
      type: "machine_unavailable",
      machine_id: machine,
      machine_start: start,
      machine_end: end,
    });
  }

  async function runSupplierLeadTime() {
    if (!supplier) {
      setError("Sélectionnez un fournisseur.");
      return;
    }

    await submitScenario("Supplier Lead Time", {
      type: "supplier_lead_time",
      supplier_id: supplier,
      lead_time_delta_days: Number(lead),
    });
  }

  function resetComparison() {
    setScenarioResult(null);
    setActiveScenario(null);
    setScenarioRunId(null);
    setRunStatus(null);
    setMessage("");
    setError("");
  }

  return (
    <>
      <PageHeader
        title="What-if Scenario Analysis"
        description="Testez l'impact d'une variation de demande, d'une indisponibilité machine ou d'un retard fournisseur avant de valider le plan."
      />

      <section className="panel" style={{ marginBottom: 20 }}>
        <div className="panel-header">
          <div>
            <h2>Planning Horizon</h2>
            <p>Le moteur CP-SAT optimise uniquement la période sélectionnée.</p>
          </div>
          <Clock3 size={20} />
        </div>

        <div className="form-grid">
          <label>
            From
            <input
              type="date"
              value={planningStart}
              onChange={(e) => {
                const value = e.target.value;
                setPlanningStart(value);
                if (planningEnd < value) setPlanningEnd(value);
              }}
            />
          </label>

          <label>
            To
            <input
              type="date"
              value={planningEnd}
              min={planningStart}
              onChange={(e) => setPlanningEnd(e.target.value)}
            />
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={includeWeekends}
              onChange={(e) => setIncludeWeekends(e.target.checked)}
            />
            Include weekends
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={includeOvertime}
              onChange={(e) => setIncludeOvertime(e.target.checked)}
            />
            Include overtime
          </label>
        </div>

        {!horizonValid && (
          <div className="info-box">
            La période sélectionnée est invalide.
          </div>
        )}
      </section>

      <div className="scenario-grid">
        <ScenarioCard
          title="Demand Increase"
          subtitle="Augmente temporairement toutes les commandes du scénario."
          icon={<Plus size={18} />}
        >
          <div className="scenario-control">
            <label>
              Demand uplift <strong>+{demand}%</strong>
            </label>
            <input
              type="range"
              min="5"
              max="50"
              step="5"
              value={demand}
              onChange={(e) => setDemand(Number(e.target.value))}
              disabled={busy}
            />
          </div>

          <div className="info-box">
            <strong>Simulation non destructive</strong>
            <p>
              La base de données n'est pas modifiée. Le volume est ajusté
              uniquement dans la copie utilisée par CP-SAT.
            </p>
          </div>

          <button
            className="button button-primary"
            disabled={busy || !horizonValid}
            onClick={runDemand}
          >
            <Play size={16} />
            Run +{demand}% demand
          </button>
        </ScenarioCard>

        <ScenarioCard
          title="Machine Unavailable"
          subtitle="Bloque une machine sur une période donnée et recalcule le plan."
          icon={<AlertTriangle size={18} />}
        >
          <div className="form-grid">
            <label>
              Machine
              <select
                value={machine}
                onChange={(e) => setMachine(e.target.value)}
                disabled={busy}
              >
                {machines.length === 0 && (
                  <option value="">Loading machines...</option>
                )}
                {machines.map((m) => (
                  <option key={m.machine_id} value={m.machine_id}>
                    {m.machine_id}
                    {m.machine_name ? ` — ${m.machine_name}` : ""}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Date
              <input
                type="date"
                value={breakdownDate}
                min={planningStart}
                max={planningEnd}
                onChange={(e) => setBreakdownDate(e.target.value)}
                disabled={busy}
              />
            </label>

            <label>
              Start
              <input
                type="time"
                value={breakdownStart}
                onChange={(e) => setBreakdownStart(e.target.value)}
                disabled={busy}
              />
            </label>

            <label>
              Duration
              <select
                value={breakdownDuration}
                onChange={(e) => setBreakdownDuration(Number(e.target.value))}
                disabled={busy}
              >
                {[2, 4, 6, 8].map((h) => (
                  <option key={h} value={h}>
                    {h} hours
                  </option>
                ))}
              </select>
            </label>
          </div>

          <button
            className="button button-danger"
            disabled={busy || !machine || !horizonValid}
            onClick={runBreakdown}
          >
            <AlertTriangle size={16} />
            Run breakdown scenario
          </button>
        </ScenarioCard>

        <ScenarioCard
          title="Supplier Lead Time"
          subtitle="Décale temporairement les réceptions des matériaux du fournisseur."
          icon={<Truck size={18} />}
        >
          <div className="form-grid">
            <label>
              Supplier
              <select
                value={supplier}
                onChange={(e) => setSupplier(e.target.value)}
                disabled={busy}
              >
                {supplierIds.length === 0 && (
                  <option value="">No supplier available</option>
                )}
                {supplierIds.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="scenario-control">
            <label>
              Additional lead time <strong>+{lead} days</strong>
            </label>
            <input
              type="range"
              min="1"
              max="15"
              step="1"
              value={lead}
              onChange={(e) => setLead(Number(e.target.value))}
              disabled={busy}
            />
          </div>

          <div className="info-box">
            <strong>Flow modeled by the engine</strong>
            <p>
              Supplier → Material → Lead Time → Replenishment → Material
              availability → Production
            </p>
          </div>

          <button
            className="button button-primary"
            disabled={busy || !supplier || !horizonValid}
            onClick={runSupplierLeadTime}
          >
            <Play size={16} />
            Run supplier scenario
          </button>
        </ScenarioCard>
      </div>

      {(busy || message || error) && (
        <section className="panel" style={{ marginTop: 20 }}>
          {busy && (
            <div className="info-box">
              <RefreshCw size={16} style={{ verticalAlign: "middle" }} />{" "}
              CP-SAT status: <strong>{runStatus || "RUNNING"}</strong>
              {activeScenario ? ` — ${activeScenario}` : ""}
            </div>
          )}

          {message && !error && (
            <div className="info-box">
              <CheckCircle2 size={16} style={{ verticalAlign: "middle" }} />{" "}
              {message}
            </div>
          )}

          {error && (
            <div className="info-box">
              <AlertTriangle size={16} style={{ verticalAlign: "middle" }} />{" "}
              {String(error)}
            </div>
          )}
        </section>
      )}

      <section className="dashboard-grid" style={{ marginTop: 20 }}>
        <div className="panel span-5">
          <div className="panel-header">
            <div>
              <h2>Scenario comparison</h2>
              <p>
                Valeurs calculées à partir des KPI du run baseline et du run
                scénario.
              </p>
            </div>
            <Gauge size={20} />
          </div>

          {!baseline && !scenarioResult && (
            <div className="empty-state">
              Aucun run terminé disponible pour établir un baseline.
            </div>
          )}

          <ComparisonRow
            label="On-time delivery"
            baseline={baseline ? formatPct(baseline.serviceRate) : "—"}
            scenario={scenarioResult ? formatPct(scenarioResult.serviceRate) : "—"}
          />

          <ComparisonRow
            label="Average machine utilization"
            baseline={baseline ? formatPct(baseline.utilization) : "—"}
            scenario={
              scenarioResult ? formatPct(scenarioResult.utilization) : "—"
            }
          />

          <ComparisonRow
            label="Late orders"
            baseline={baseline ? formatNumber(baseline.lateOrders) : "—"}
            scenario={scenarioResult ? formatNumber(scenarioResult.lateOrders) : "—"}
          />

          <ComparisonRow
            label="Average tardiness"
            baseline={
              baseline ? `${formatNumber(baseline.avgTardiness)} h` : "—"
            }
            scenario={
              scenarioResult
                ? `${formatNumber(scenarioResult.avgTardiness)} h`
                : "—"
            }
          />

          {scenarioResult && (
            <button
              className="button button-secondary"
              onClick={resetComparison}
              style={{ marginTop: 16 }}
            >
              <RefreshCw size={15} />
              Reset comparison
            </button>
          )}
        </div>

        <div className="panel span-7">
          <div className="panel-header">
            <div>
              <h2>Decision interpretation</h2>
              <p>Une lecture opérationnelle basée sur les résultats réels du solveur.</p>
            </div>
            <Sparkles size={20} />
          </div>

          <DecisionInterpretation
            baseline={baseline}
            scenario={scenarioResult}
            scenarioName={activeScenario}
            supplier={supplier}
            lead={lead}
          />
        </div>
      </section>
    </>
  );
}

function DecisionInterpretation({
  baseline,
  scenario,
  scenarioName,
  supplier,
  lead,
}) {
  if (!baseline || !scenario) {
    return (
      <div className="decision-card">
        <Sparkles size={20} />
        <div>
          <strong>Decision support</strong>
          <p>
            Lancez un scénario. Après résolution CP-SAT, cette zone expliquera
            automatiquement l'évolution du service, des retards et de
            l'utilisation des ressources.
          </p>
        </div>
      </div>
    );
  }

  const serviceDelta = scenario.serviceRate - baseline.serviceRate;
  const lateDelta = scenario.lateOrders - baseline.lateOrders;
  const utilizationDelta = scenario.utilization - baseline.utilization;

  let consequence =
    "L'impact global est limité. Le plan reste relativement robuste sur l'horizon sélectionné.";

  if (serviceDelta < -2 || lateDelta > 5) {
    consequence =
      "Le scénario dégrade sensiblement le niveau de service. Les commandes prioritaires doivent être protégées et le planner doit revoir les capacités ou les approvisionnements.";
  } else if (serviceDelta > 1 && lateDelta < 0) {
    consequence =
      "Le scénario produit un plan plus performant sur l'indicateur de service. Il peut être considéré comme favorable sous réserve de la capacité réelle des ressources.";
  }

  return (
    <div className="decision-card">
      <Sparkles size={20} />
      <div>
        <strong>{scenarioName || "Scenario"} — résultat CP-SAT</strong>
        <p>{consequence}</p>
        <ul>
          <li>
            Service: <strong>{serviceDelta >= 0 ? "+" : ""}
            {serviceDelta.toFixed(1)} pts</strong>
          </li>
          <li>
            Late orders: <strong>{lateDelta >= 0 ? "+" : ""}
            {lateDelta}</strong>
          </li>
          <li>
            Utilization: <strong>{utilizationDelta >= 0 ? "+" : ""}
            {utilizationDelta.toFixed(1)} pts</strong>
          </li>
          {scenarioName === "Supplier Lead Time" && (
            <li>
              Supplier impact: <strong>{supplier} +{lead} days</strong>
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

function ScenarioCard({ title, subtitle, icon, children }) {
  return (
    <div className="panel scenario-card">
      <div className="scenario-icon">{icon}</div>
      <h2>{title}</h2>
      <p>{subtitle}</p>
      <div className="scenario-content">{children}</div>
    </div>
  );
}

function ComparisonRow({ label, baseline, scenario }) {
  return (
    <div className="comparison-row">
      <span>{label}</span>
      <strong>{baseline}</strong>
      <ArrowRight size={15} />
      <em>{scenario}</em>
    </div>
  );
}
