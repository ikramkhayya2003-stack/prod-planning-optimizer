import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Filter,
  RefreshCw,
  Search,
  ShoppingCart,
  X,
} from "lucide-react";

import PageHeader from "../components/PageHeader";
import { getLatestRun, getPlanning, getProcurement } from "../api";

const RISK_CONFIG = {
  HIGH: { label: "HIGH", icon: "🔴", className: "risk-high" },
  MEDIUM: { label: "MEDIUM", icon: "🟠", className: "risk-medium" },
  LOW: { label: "LOW", icon: "🟢", className: "risk-low" },
};

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString("fr-FR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString("fr-FR");
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("fr-FR") : "0";
}

function RiskBadge({ risk }) {
  const value = String(risk || "LOW").toUpperCase();
  const config = RISK_CONFIG[value] || RISK_CONFIG.LOW;
  return (
    <span className={`risk-badge ${config.className}`}>
      {config.icon} {config.label}
    </span>
  );
}

function PriorityBadge({ priority }) {
  if (!priority) return <span>—</span>;
  const value = String(priority).toUpperCase();
  return (
    <span className={`priority-badge priority-${value}`}>{value}</span>
  );
}

function DelayBadge({ hours }) {
  const value = Number(hours || 0);
  if (value <= 0) return <span className="delay-ok">On time</span>;
  return <span className="delay-danger">+{value.toFixed(1)} h</span>;
}

export default function Planning({
  planning: planningProp = [],
  runId: runIdProp = "",
  runStatus: runStatusProp = "READY",
}) {
  const [localPlanning, setLocalPlanning] = useState([]);
  const [summary, setSummary] = useState({});
  const [procurementRows, setProcurementRows] = useState([]);
  const [procurementLoading, setProcurementLoading] = useState(false);
  const [procurementError, setProcurementError] = useState("");
  const [localRunId, setLocalRunId] = useState(
    () => localStorage.getItem("latest_run_id") || "",
  );
  const [localRunStatus, setLocalRunStatus] = useState("READY");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [machineFilter, setMachineFilter] = useState("ALL");
  const [riskFilter, setRiskFilter] = useState("ALL");
  const [priorityFilter, setPriorityFilter] = useState("ALL");
  const [selectedRow, setSelectedRow] = useState(null);

  const runId = runIdProp || localRunId;
  const runStatus = runStatusProp || localRunStatus;
  const planning = Array.isArray(planningProp) && planningProp.length
    ? planningProp
    : localPlanning;

  const loadProcurement = useCallback(async (targetId = runId) => {
    const id = targetId || localStorage.getItem("latest_run_id") || "";
    if (!id) {
      setProcurementRows([]);
      setProcurementError("");
      return;
    }

    setProcurementLoading(true);
    setProcurementError("");

    try {
      const result = await getProcurement(id);
      setProcurementRows(
        Array.isArray(result?.rows) ? result.rows : [],
      );
    } catch (err) {
      console.error("Procurement loading error:", err);
      setProcurementRows([]);
      setProcurementError(
        err?.response?.data?.detail ||
          err?.message ||
          "Unable to load the procurement plan.",
      );
    } finally {
      setProcurementLoading(false);
    }
  }, [runId]);

  const loadPlanning = useCallback(async (targetId = runId) => {
    setLoading(true);
    setError("");

    try {
      let id = targetId || localStorage.getItem("latest_run_id") || "";

      if (!id) {
        const latest = await getLatestRun();
        id = latest?.run_id || "";
      }

      if (!id) {
        setLocalPlanning([]);
        setSummary({});
        setProcurementRows([]);
        setProcurementError("");
        setError("No optimization run found. Please run CP-SAT first.");
        return;
      }

      const result = await getPlanning(id);
      const rows = Array.isArray(result?.planning) ? result.planning : [];

      setLocalPlanning(rows);
      setSummary(result?.summary || {});
      setLocalRunId(result?.run_id || id);
      setLocalRunStatus(result?.status || "READY");

      await loadProcurement(result?.run_id || id);

      localStorage.setItem("latest_run_id", result?.run_id || id);
      localStorage.setItem("latest_run_status", result?.status || "READY");
    } catch (err) {
      console.error("Planning loading error:", err);
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Unable to load the production plan.",
      );
      setLocalPlanning([]);
    } finally {
      setLoading(false);
    }
  }, [runId, loadProcurement]);

  // If App has not loaded planning yet, fetch it directly from the API.
  useEffect(() => {
    if (!planningProp?.length && runId) {
      loadPlanning(runId);
    }
  }, [planningProp?.length, runId, loadPlanning]);

  // The App loads production operations after a completed run, so the
  // procurement plan must be loaded independently as well.
  useEffect(() => {
    if (runId) {
      loadProcurement(runId);
    }
  }, [runId, loadProcurement]);

  const machines = useMemo(() => {
    const values = planning.map((row) => row.machine_id).filter(Boolean);
    return ["ALL", ...Array.from(new Set(values))];
  }, [planning]);

  const filteredPlanning = useMemo(() => {
    const query = search.trim().toLowerCase();

    return planning.filter((row) => {
      const matchesSearch =
        !query ||
        [row.order_id, row.product_id, row.operation_code, row.machine_id]
          .map((value) => String(value || "").toLowerCase())
          .some((value) => value.includes(query));

      const matchesMachine =
        machineFilter === "ALL" ||
        String(row.machine_id || "") === String(machineFilter);

      const matchesRisk =
        riskFilter === "ALL" ||
        String(row.risk || "LOW").toUpperCase() === riskFilter;

      const matchesPriority =
        priorityFilter === "ALL" ||
        String(row.priority_class || "").toUpperCase() === priorityFilter;

      return matchesSearch && matchesMachine && matchesRisk && matchesPriority;
    });
  }, [planning, search, machineFilter, riskFilter, priorityFilter]);

  function resetFilters() {
    setSearch("");
    setMachineFilter("ALL");
    setRiskFilter("ALL");
    setPriorityFilter("ALL");
  }

  return (
    <div className="planning-page">
      <PageHeader
        title="Production Plan"
        description="Optimized production sequence with machine, priority, due-date and risk context."
      />

      <div className="panel">
        <div className="panel-header">
          <div>
            <span className="eyebrow">OPTIMIZATION RUN</span>
            <h2>Active production schedule</h2>
            <p>
              Run ID: <strong>{runId || "No run selected"}</strong>
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <RiskStatus status={runStatus} />
            <button
              type="button"
              className="button button-secondary"
              onClick={async () => { await loadPlanning(runId); await loadProcurement(runId); }}
              disabled={loading || !runId}
            >
              <RefreshCw size={15} className={loading ? "spin" : ""} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="error-box">
          <AlertCircle size={17} />
          <span>{error}</span>
        </div>
      )}

      <div className="kpi-grid">
        <MiniKpi
          label="Operations"
          value={formatNumber(summary.operations ?? planning.length)}
          icon={<CalendarDays size={18} />}
        />
        <MiniKpi
          label="Total setup"
          value={`${(Number(summary.total_setup_minutes ?? summary.total_setup_min ?? 0) / 60).toFixed(1)} h`}
          icon={<Clock3 size={18} />}
        />
        <MiniKpi
          label="Late orders"
          value={formatNumber(summary.late_orders || 0)}
          icon={<AlertCircle size={18} />}
        />
        <MiniKpi
          label="High risk"
          value={formatNumber(summary.high_risk_operations || 0)}
          icon={<span>🔴</span>}
        />
      </div>

      <div className="panel">
        <div className="filter-toolbar">
          <div className="search-box">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search order, product, operation or machine..."
            />
          </div>

          <select value={machineFilter} onChange={(e) => setMachineFilter(e.target.value)}>
            {machines.map((machine) => (
              <option key={machine} value={machine}>
                {machine === "ALL" ? "All machines" : machine}
              </option>
            ))}
          </select>

          <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
            <option value="ALL">All priorities</option>
            <option value="A">Priority A</option>
            <option value="B">Priority B</option>
            <option value="C">Priority C</option>
          </select>

          <select value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
            <option value="ALL">All risks</option>
            <option value="HIGH">🔴 HIGH</option>
            <option value="MEDIUM">🟠 MEDIUM</option>
            <option value="LOW">🟢 LOW</option>
          </select>

          <button type="button" className="button button-secondary" onClick={resetFilters}>
            <Filter size={15} /> Reset
          </button>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div>
            <h2>Production operations</h2>
            <p>{filteredPlanning.length} operations displayed.</p>
          </div>
        </div>

        {loading ? (
          <div className="loading-state">
            <RefreshCw size={24} className="spin" />
            <span>Loading production plan...</span>
          </div>
        ) : filteredPlanning.length === 0 ? (
          <div className="empty-state">
            <CalendarDays size={32} />
            <strong>No planning data available</strong>
            <span>Run a successful optimization, then refresh this page.</span>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table planning-table">
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Product</th>
                  <th>Operation</th>
                  <th>Machine</th>
                  <th>Start</th>
                  <th>End</th>
                  <th>Setup</th>
                  <th>Priority</th>
                  <th>Due date</th>
                  <th>Delay</th>
                  <th>Risk</th>
                  <th>Explain</th>
                </tr>
              </thead>
              <tbody>
                {filteredPlanning.map((row, index) => (
                  <tr key={`${row.order_id || "order"}-${row.operation_seq ?? index}-${index}`}>
                    <td>
                      <strong>{row.order_id || "—"}</strong>
                      {row.urgent && <span className="urgent-tag">URGENT</span>}
                    </td>
                    <td>{row.product_id || "—"}</td>
                    <td>
                      <strong>{row.operation_code || "—"}</strong>
                      <small style={{ display: "block", color: "#94a3b8" }}>
                        Seq. {row.operation_seq ?? "—"}
                      </small>
                    </td>
                    <td><span className="machine-pill">{row.machine_id || "—"}</span></td>
                    <td>{formatDateTime(row.start_datetime)}</td>
                    <td>{formatDateTime(row.end_datetime)}</td>
                    <td>{Number(row.setup_minutes || 0) > 0 ? `${row.setup_minutes} min` : "—"}</td>
                    <td><PriorityBadge priority={row.priority_class} /></td>
                    <td>{formatDate(row.due_date)}</td>
                    <td><DelayBadge hours={row.delay_hours} /></td>
                    <td><RiskBadge risk={row.risk} /></td>
                    <td>
                      <button type="button" className="button button-small" onClick={() => setSelectedRow(row)}>
                        Why?
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel procurement-panel">
        <div className="panel-header">
          <div>
            <span className="eyebrow">SUPPLY DECISION</span>
            <h2>Procurement Plan</h2>
            <p>Supplier, order quantity and receipt decisions generated for this optimization run.</p>
          </div>
          <div className="status-badge">
            {procurementRows.length} order{procurementRows.length === 1 ? "" : "s"}
          </div>
        </div>

        {procurementError && (
          <div className="error-box">
            <AlertCircle size={17} />
            <span>{procurementError}</span>
          </div>
        )}

        {procurementLoading ? (
          <div className="loading-state">
            <RefreshCw size={24} className="spin" />
            <span>Loading procurement decisions...</span>
          </div>
        ) : procurementRows.length === 0 ? (
          <div className="empty-state">
            <ShoppingCart size={32} />
            <strong>No procurement decision stored for this run</strong>
            <span>Run a new CP-SAT optimization after importing the V2 dataset.</span>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table planning-table">
              <thead>
                <tr>
                  <th>Material</th>
                  <th>Supplier</th>
                  <th>Order Date</th>
                  <th>Receipt Date</th>
                  <th>Qty</th>
                  <th>Unit Cost</th>
                  <th>Total Cost</th>
                  <th>Lead Time</th>
                  <th>MOQ</th>
                  <th>Lot Size</th>
                  <th>Reliability</th>
                </tr>
              </thead>
              <tbody>
                {procurementRows.map((row, index) => (
                  <tr key={`${row.material_id || "material"}-${row.supplier_id || "supplier"}-${row.order_date || index}-${index}`}>
                    <td><strong>{row.material_id || "—"}</strong></td>
                    <td><span className="machine-pill">{row.supplier_id || "—"}</span></td>
                    <td>{formatDate(row.order_date)}</td>
                    <td>{formatDate(row.receipt_date)}</td>
                    <td><strong>{formatNumber(row.order_qty)}</strong></td>
                    <td>{Number(row.unit_cost_eur || 0).toFixed(4)} €</td>
                    <td><strong>{Number(row.purchase_cost_eur || 0).toFixed(2)} €</strong></td>
                    <td>{row.lead_time_days ?? "—"} d</td>
                    <td>{formatNumber(row.min_order_qty)}</td>
                    <td>{formatNumber(row.lot_size)}</td>
                    <td>{Number(row.reliability_pct || 0).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedRow && (
        <PlanningDetail row={selectedRow} onClose={() => setSelectedRow(null)} />
      )}
    </div>
  );
}

function MiniKpi({ label, value, icon }) {
  return (
    <div className="kpi-card">
      <div className="kpi-icon">{icon}</div>
      <div>
        <span className="kpi-label">{label}</span>
        <strong className="kpi-value">{value}</strong>
      </div>
    </div>
  );
}

function RiskStatus({ status }) {
  const value = String(status || "READY").toUpperCase();
  if (value === "COMPLETED" || value === "SUCCESS") {
    return <span className="status-badge status-success"><CheckCircle2 size={14} /> COMPLETED</span>;
  }
  if (value === "RUNNING" || value === "QUEUED") {
    return <span className="status-badge status-warning"><Clock3 size={14} /> {value}</span>;
  }
  if (value === "FAILED") {
    return <span className="status-badge status-error"><AlertCircle size={14} /> FAILED</span>;
  }
  return <span className="status-badge">{value}</span>;
}

function PlanningDetail({ row, onClose }) {
  const reasons = Array.isArray(row.risk_reasons) ? row.risk_reasons : [];
  const materialRisks = Array.isArray(row.material_risks) ? row.material_risks : [];

  return (
    <div className="drawer-overlay">
      <aside className="risk-drawer">
        <div className="drawer-header">
          <div>
            <span>Schedule explanation</span>
            <h2>{row.order_id || "Operation"}</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="drawer-risk"><RiskBadge risk={row.risk} /></div>

        <div className="risk-summary">
          <InfoRow label="Product" value={row.product_id} />
          <InfoRow label="Operation" value={`${row.operation_code || "—"} / Seq. ${row.operation_seq ?? "—"}`} />
          <InfoRow label="Machine" value={row.machine_id} />
          <InfoRow label="Priority" value={row.priority_class} />
          <InfoRow label="Setup" value={Number(row.setup_minutes || 0) > 0 ? `${row.setup_minutes} min` : "No setup"} />
          <InfoRow label="Start" value={formatDateTime(row.start_datetime)} />
          <InfoRow label="End" value={formatDateTime(row.end_datetime)} />
          <InfoRow label="Due date" value={formatDate(row.due_date)} />
          <InfoRow label="Delay" value={Number(row.delay_hours || 0) > 0 ? `+${Number(row.delay_hours).toFixed(1)} h` : "On time"} />
        </div>

        <div className="drawer-section">
          <h3>Why is this operation here?</h3>
          {reasons.length ? (
            <div className="reason-list">
              {reasons.map((reason, index) => (
                <div className="reason-item" key={index}>
                  <AlertCircle size={16} />
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="reason-item">
              <CheckCircle2 size={16} />
              <span>No critical risk detected.</span>
            </div>
          )}
        </div>

        {materialRisks.length > 0 && (
          <div className="drawer-section">
            <h3>Material constraints</h3>
            <div className="mini-table">
              {materialRisks.map((material, index) => (
                <div className="mini-row" key={material.material_id || index}>
                  <strong>{material.material_id || "—"}</strong>
                  <span>Coverage: {material.coverage_days ?? "—"} d</span>
                  <span>Lead time: {material.lead_time_days ?? "—"} d</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <strong>{value || "—"}</strong>
    </div>
  );
}
