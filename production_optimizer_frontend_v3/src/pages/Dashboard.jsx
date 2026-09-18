
import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Boxes,
  Factory,
  Gauge,
  RefreshCw,
  Settings2,
  Timer,
  X,
  CheckCircle2,
  Package,
  CalendarClock,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getKpis,
  getMaterials,
  getPlanning,
  getMachines,
} from "../api";

import KpiCard from "../components/KpiCard";
import PageHeader from "../components/PageHeader";
import StatusBadge from "../components/StatusBadge";
import Gantt from "../components/Gantt";
import EmptyState from "../components/EmptyState";

export default function Dashboard({
  runId,
  runStatus,
  health,
  onOptimize,
}) {
  const [kpis, setKpis] = useState(null);
  const [planning, setPlanning] = useState([]);
  const [machines, setMachines] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Alert selected by the user
  const [selectedAlert, setSelectedAlert] = useState(null);

  // ============================================================
  // LOAD MASTER DATA
  // ============================================================

  useEffect(() => {
    let alive = true;

    Promise.all([
      getMachines(),
      getMaterials({ limit: 500 }),
    ])
      .then(([machineData, materialData]) => {
        if (!alive) return;

        setMachines(machineData.machines || []);
        setMaterials(materialData.materials || []);
      })
      .catch(() => {});

    return () => {
      alive = false;
    };
  }, []);

  // ============================================================
  // LOAD COMPLETED RUN
  // ============================================================

  useEffect(() => {
    if (!runId || runStatus !== "COMPLETED") {
      return undefined;
    }

    let alive = true;

    setLoading(true);
    setError("");

    Promise.all([
      getKpis(runId),
      getPlanning(runId),
    ])
      .then(([k, p]) => {
        if (!alive) return;

        setKpis(k);
        setPlanning(p.planning || []);
      })
      .catch((err) => {
        if (!alive) return;

        setError(
          err.response?.data?.detail ||
            "Unable to load the completed run."
        );
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, [runId, runStatus]);

  // ============================================================
  // KPI DATA
  // ============================================================

  const summary = kpis?.summary || {};

  const chart = useMemo(
    () =>
      (kpis?.machines || []).map((m) => ({
        machine: m.machine_id,
        utilization: Number(m.utilization_pct || 0),
        occupancy: Number(m.occupancy_pct || 0),
      })),
    [kpis]
  );

  const avgUtil = chart.length
    ? chart.reduce((s, x) => s + x.utilization, 0) / chart.length
    : 0;

  const materialRisk = useMemo(
    () =>
      materials.filter(
        (m) =>
          Number(m.on_hand_qty || 0) <
          Number(m.safety_stock_qty || 0)
      ),
    [materials]
  );

  const materialRiskCount = materialRisk.length;

  const overloadedMachines = useMemo(
    () =>
      chart.filter(
        (x) => Number(x.utilization || 0) > 90
      ),
    [chart]
  );

  const overloadCount = overloadedMachines.length;

  // ============================================================
  // ALERTS
  // ============================================================

  const alerts = useMemo(() => {
    const result = [];

    // ----------------------------------------------------------
    // LATE ORDERS
    // ----------------------------------------------------------

    if (Number(summary.late_orders || 0) > 0) {
      result.push({
        id: "late-orders",
        type: "late_orders",
        tone: "red",
        severity: "Critical",
        title: `${summary.late_orders} orders may be late`,
        message:
          "Review due dates and bottleneck capacity before release.",
      });
    }

    // ----------------------------------------------------------
    // MACHINE OVERLOAD
    // ----------------------------------------------------------

    if (overloadCount > 0) {
      result.push({
        id: "machine-overload",
        type: "machine_overload",
        tone: "orange",
        severity: "Warning",
        title: `${overloadCount} machine(s) above 90%`,
        message:
          "Use Gantt and the optimization center to redistribute load.",
      });
    }

    // ----------------------------------------------------------
    // MATERIAL RISK
    // ----------------------------------------------------------

    if (materialRiskCount > 0) {
      result.push({
        id: "material-risk",
        type: "material-risk",
        tone: "red",
        severity: "Critical",
        title: `${materialRiskCount} material(s) below safety`,
        message:
          "Review coverage and supplier lead time before scheduling.",
      });
    }

    return result;
  }, [
    summary.late_orders,
    overloadCount,
    materialRiskCount,
  ]);

  // ============================================================
  // ALERT DETAILS
  // ============================================================

  const getAlertDetails = (alert) => {
    if (!alert) return null;

    // ----------------------------------------------------------
    // LATE ORDERS
    // ----------------------------------------------------------

    if (alert.type === "late_orders") {
      return {
        icon: <CalendarClock size={21} />,
        title: "Late Orders Risk",
        description:
          "The latest optimized production plan contains orders with expected tardiness.",
        metrics: [
          {
            label: "Orders affected",
            value: String(summary.late_orders || 0),
          },
          {
            label: "Average delay",
            value: `${Number(
              summary.avg_tardiness_hours || 0
            ).toFixed(1)} h`,
          },
          {
            label: "Maximum delay",
            value: `${Number(
              summary.max_tardiness_hours || 0
            ).toFixed(1)} h`,
          },
        ],
        actions: [
          "Review the affected orders and their requested due dates.",
          "Check bottleneck machines in the Gantt.",
          "Consider redistributing production load.",
          "Run a new optimization after changing priorities or capacity.",
        ],
      };
    }

    // ----------------------------------------------------------
    // MACHINE OVERLOAD
    // ----------------------------------------------------------

    if (alert.type === "machine_overload") {
      return {
        icon: <Factory size={21} />,
        title: "Machine Capacity Risk",
        description:
          "One or more machines are operating above the 90% utilization threshold.",
        metrics: [
          {
            label: "Machines affected",
            value: String(overloadCount),
          },
          {
            label: "Average utilization",
            value: `${avgUtil.toFixed(1)}%`,
          },
          {
            label: "Threshold",
            value: "90%",
          },
        ],
        machines: overloadedMachines,
        actions: [
          "Open the Gantt to identify overloaded periods.",
          "Check whether compatible machines can absorb some operations.",
          "Review setup sequences and machine availability.",
          "Run optimization again if capacity must be redistributed.",
        ],
      };
    }

    // ----------------------------------------------------------
    // MATERIAL RISK
    // ----------------------------------------------------------

    if (alert.type === "material-risk") {
      return {
        icon: <Package size={21} />,
        title: "Material Stock Risk",
        description:
          "Some materials are currently below their defined safety-stock level.",
        metrics: [
          {
            label: "Materials affected",
            value: String(materialRiskCount),
          },
          {
            label: "Stock threshold",
            value: "Safety stock",
          },
        ],
        materials: materialRisk,
        actions: [
          "Review current material coverage.",
          "Check supplier lead times.",
          "Verify open purchase orders.",
          "Consider procurement before releasing additional production.",
        ],
      };
    }

    return {
      icon: <AlertCircle size={21} />,
      title: alert.title,
      description: alert.message,
      metrics: [],
      actions: [],
    };
  };

  // ============================================================
  // RENDER
  // ============================================================

  return (
    <>
      <PageHeader
        title="Executive Dashboard"
        description="A decision cockpit for answering: Is production under control today?"
        action={onOptimize}
        actionLabel={
          runStatus === "RUNNING"
            ? "Optimizing…"
            : "Run Optimization"
        }
        actionIcon={
          <RefreshCw
            size={17}
            className={
              runStatus === "RUNNING" ? "spin" : ""
            }
          />
        }
      />

      {/* ======================================================
          CURRENT RUN
      ====================================================== */}

      <div className="hero-strip">
        <div>
          <span className="hero-label">CURRENT RUN</span>

          <strong>
            {runId || "No optimized run"}
          </strong>

          <small>
            {runStatus || "Waiting for first optimization"}
          </small>
        </div>

        <StatusBadge status={runStatus || "READY"}>
          {runStatus || "READY"}
        </StatusBadge>
      </div>

      {error && (
        <div className="error-box">
          {error}
        </div>
      )}

      {/* ======================================================
          KPI GRID
      ====================================================== */}

      <section className="kpi-grid">
        <KpiCard
          title="Orders"
          value={health?.orders ?? "—"}
          subtitle="Customer demand in PostgreSQL"
          icon={<Boxes size={19} />}
        />

        <KpiCard
          title="On-Time Delivery"
          value={`${Number(
            summary.service_rate_pct || 0
          ).toFixed(1)}%`}
          subtitle="Latest completed run"
          icon={<Gauge size={19} />}
          tone="green"
        />

        <KpiCard
          title="Late Orders"
          value={summary.late_orders ?? "—"}
          subtitle="Current run"
          icon={<AlertCircle size={19} />}
          tone="red"
        />

        <KpiCard
          title="Machine Utilization"
          value={`${avgUtil.toFixed(1)}%`}
          subtitle="Average across run machines"
          icon={<Factory size={19} />}
        />

        <KpiCard
          title="Setup Time"
          value={`${(
            Number(summary.total_setup_min || 0) / 60
          ).toFixed(1)}h`}
          subtitle="Sequence-dependent setup"
          icon={<Settings2 size={19} />}
          tone="amber"
        />

        <KpiCard
          title="Average Delay"
          value={`${Number(
            summary.avg_tardiness_hours || 0
          ).toFixed(1)}h`}
          subtitle={`Max ${Number(
            summary.max_tardiness_hours || 0
          ).toFixed(1)}h`}
          icon={<Timer size={19} />}
          tone="amber"
        />
      </section>

      {/* ======================================================
          ALERT CENTER
      ====================================================== */}

      <section className="dashboard-grid">
        <div className="panel span-7">
          <div className="panel-header">
            <div>
              <h2>Alert Center</h2>

              <p>
                Items requiring planner attention before plan release.
              </p>
            </div>

            <span className="section-counter">
              {alerts.length} alerts
            </span>
          </div>

          <div className="alert-list">
            {alerts.length ? (
              alerts.map((alert) => (
                <button
                  type="button"
                  className={`alert-item ${
                    selectedAlert?.id === alert.id
                      ? "selected"
                      : ""
                  }`}
                  key={alert.id}
                  onClick={() =>
                    setSelectedAlert(alert)
                  }
                >
                  <div
                    className={`alert-severity ${alert.tone}`}
                  />

                  <div className="alert-main">
                    <strong>{alert.title}</strong>

                    <span>
                      {alert.message}
                    </span>
                  </div>

                  <ArrowRight size={17} />
                </button>
              ))
            ) : (
              <EmptyState
                title="No critical alert"
                description="Current master data and completed run show no surfaced exception."
              />
            )}
          </div>

          {/* ==================================================
              ALERT DETAIL PANEL
          ================================================== */}

          {selectedAlert && (
            <AlertDetailPanel
              alert={selectedAlert}
              details={getAlertDetails(selectedAlert)}
              onClose={() =>
                setSelectedAlert(null)
              }
            />
          )}
        </div>

        {/* ======================================================
            OPTIMIZATION SNAPSHOT
        ====================================================== */}

        <div className="panel span-5">
          <div className="panel-header">
            <div>
              <h2>Optimization Snapshot</h2>

              <p>
                Latest run and planning volume.
              </p>
            </div>
          </div>

          <div className="snapshot-list">
            <Snapshot
              label="Solver status"
              value={runStatus || "—"}
            />

            <Snapshot
              label="Objective value"
              value={
                kpis?.objective_value ?? "—"
              }
            />

            <Snapshot
              label="Operations scheduled"
              value={
                planning.length || "—"
              }
            />

            <Snapshot
              label="Materials below safety"
              value={materialRiskCount}
            />
          </div>
        </div>
      </section>

      {/* ======================================================
          MACHINE UTILIZATION
      ====================================================== */}

      <section className="dashboard-grid">
        <div className="panel span-7">
          <div className="panel-header">
            <div>
              <h2>Machine Utilization</h2>

              <p>
                Utilization versus total occupancy.
              </p>
            </div>
          </div>

          {chart.length ? (
            <div className="chart-box">
              <ResponsiveContainer
                width="100%"
                height={340}
              >
                <BarChart data={chart}>
                  <CartesianGrid strokeDasharray="3 3" />

                  <XAxis dataKey="machine" />

                  <YAxis
                    domain={[0, 100]}
                    unit="%"
                  />

                  <Tooltip />

                  <Bar
                    dataKey="utilization"
                    name="Utilization"
                    fill="#315A7D"
                    radius={[5, 5, 0, 0]}
                  />

                  <Bar
                    dataKey="occupancy"
                    name="Occupancy"
                    fill="#6F8F9F"
                    radius={[5, 5, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              title="No completed run yet"
              description="Run CP-SAT to populate machine KPIs."
            />
          )}
        </div>

        {/* ====================================================
            PLANNING PREVIEW
        ==================================================== */}

        <div className="panel span-5">
          <div className="panel-header">
            <div>
              <h2>Planning Preview</h2>

              <p>
                First optimized operations.
              </p>
            </div>
          </div>

          {loading ? (
            <div className="loading-box">
              <RefreshCw className="spin" />

              Loading plan…
            </div>
          ) : (
            <Gantt
              planning={planning.slice(0, 40)}
            />
          )}
        </div>
      </section>
    </>
  );
}

// ============================================================
// SNAPSHOT
// ============================================================

function Snapshot({ label, value }) {
  return (
    <div className="snapshot-row">
      <span>{label}</span>

      <strong>
        {String(value)}
      </strong>
    </div>
  );
}

// ============================================================
// ALERT DETAIL PANEL
// ============================================================

function AlertDetailPanel({
  alert,
  details,
  onClose,
}) {
  if (!details) return null;

  return (
    <div className="alert-detail-panel">
      {/* Header */}

      <div className="alert-detail-header">
        <div className="alert-detail-title">
          <div
            className={`alert-detail-icon ${alert.tone}`}
          >
            {details.icon}
          </div>

          <div>
            <span className="alert-detail-label">
              {alert.severity} ALERT
            </span>

            <h3>{details.title}</h3>
          </div>
        </div>

        <button
          type="button"
          className="alert-close-button"
          onClick={onClose}
          aria-label="Close alert details"
        >
          <X size={18} />
        </button>
      </div>

      {/* Description */}

      <p className="alert-detail-description">
        {details.description}
      </p>

      {/* Metrics */}

      {details.metrics?.length > 0 && (
        <div className="alert-detail-metrics">
          {details.metrics.map(
            (metric) => (
              <div
                className="alert-detail-metric"
                key={metric.label}
              >
                <span>{metric.label}</span>

                <strong>
                  {metric.value}
                </strong>
              </div>
            )
          )}
        </div>
      )}

      {/* Machine list */}

      {details.machines?.length > 0 && (
        <div className="alert-detail-section">
          <h4>
            <Factory size={16} />
            Affected machines
          </h4>

          <div className="alert-detail-table">
            {details.machines.map(
              (machine) => (
                <div
                  className="alert-detail-row"
                  key={machine.machine}
                >
                  <span>
                    {machine.machine}
                  </span>

                  <strong>
                    {Number(
                      machine.utilization || 0
                    ).toFixed(1)}
                    %
                  </strong>
                </div>
              )
            )}
          </div>
        </div>
      )}

      {/* Material list */}

      {details.materials?.length > 0 && (
        <div className="alert-detail-section">
          <h4>
            <Package size={16} />
            Materials below safety stock
          </h4>

          <div className="alert-detail-table">
            {details.materials
              .slice(0, 10)
              .map((material) => {
                const stock = Number(
                  material.on_hand_qty || 0
                );

                const safety = Number(
                  material.safety_stock_qty || 0
                );

                return (
                  <div
                    className="alert-detail-row"
                    key={material.material_id}
                  >
                    <div>
                      <strong>
                        {material.material_id}
                      </strong>

                      {material.material_name && (
                        <small>
                          {material.material_name}
                        </small>
                      )}
                    </div>

                    <span>
                      {stock.toLocaleString()} /{" "}
                      {safety.toLocaleString()}
                    </span>
                  </div>
                );
              })}
          </div>

          {details.materials.length > 10 && (
            <small className="alert-detail-more">
              + {details.materials.length - 10} more
              materials
            </small>
          )}
        </div>
      )}

      {/* Recommended actions */}

      {details.actions?.length > 0 && (
        <div className="alert-detail-section">
          <h4>
            <CheckCircle2 size={16} />
            Recommended actions
          </h4>

          <ul className="alert-action-list">
            {details.actions.map(
              (action, index) => (
                <li key={index}>
                  {action}
                </li>
              )
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

