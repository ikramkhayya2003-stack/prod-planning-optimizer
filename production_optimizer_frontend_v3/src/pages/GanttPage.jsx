
import { useMemo, useState } from "react";
import {
  CalendarDays,
  Edit3,
  Filter,
  Lock,
  RefreshCw,
  Search,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import Gantt from "../components/Gantt";
import PageHeader from "../components/PageHeader";
import StatusBadge from "../components/StatusBadge";
import ExplainPlanPanel from "../components/ExplainPlanPanel";

import {
  updatePlanningOperation,
  getPlanning,
} from "../api";

export default function GanttPage({
  planning = [],
  runId,
  onPlanningUpdated,
}) {
  const [editable, setEditable] = useState(false);
  const [message, setMessage] = useState("");
  const [machineFilter, setMachineFilter] = useState("ALL");
  const [riskFilter, setRiskFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [zoom, setZoom] = useState(1);
  const [explainOperation, setExplainOperation] = useState(null);

  // ============================================================
  // NORMALISER LE PLANNING
  // ============================================================


  const planningRows = useMemo(() => {
    if (Array.isArray(planning)) {
      return planning;
    }

    if (planning && Array.isArray(planning.planning)) {
      return planning.planning;
    }

    if (planning && Array.isArray(planning.data)) {
      return planning.data;
    }

    if (planning && Array.isArray(planning.results)) {
      return planning.results;
    }

    console.warn(
      "GanttPage: unexpected planning format:",
      planning,
    );

    return [];
  }, [planning]);

  // ============================================================
  // MACHINES
  // ============================================================

  const machines = useMemo(
    () => [
      "ALL",
      ...new Set(
        planningRows
          .map((row) => row.machine_id)
          .filter(Boolean)
          .map((value) => String(value)),
      ),
    ],
    [planningRows],
  );

  // ============================================================
  // STATISTIQUES
  // ============================================================

  const stats = useMemo(() => {
    const rows = planningRows.filter((row) => {
      const q = search.trim().toLowerCase();

      return (
        (machineFilter === "ALL" ||
          String(row.machine_id) === machineFilter) &&

        (
          riskFilter === "ALL" ||
          String(row.risk || "LOW").toUpperCase() === riskFilter
        ) &&

        (
          !q ||
          [
            row.order_id,
            row.product_id,
            row.operation_code,
            row.machine_id,
          ]
            .map((v) => String(v || "").toLowerCase())
            .some((v) => v.includes(q))
        )
      );
    });

    return {
      operations: rows.length,

      machines: new Set(
        rows
          .map((row) => row.machine_id)
          .filter(Boolean),
      ).size,

      high: rows.filter(
        (row) =>
          String(row.risk || "LOW").toUpperCase() === "HIGH",
      ).length,

      late: rows.filter(
        (row) => Number(row.delay_hours || 0) > 0,
      ).length,
    };
  }, [
    planningRows,
    machineFilter,
    riskFilter,
    search,
  ]);

  // ============================================================
  // MANUAL MOVE
  // ============================================================

  async function onMove(task, machine) {
    console.log("======================================");
    console.log("GANTT MANUAL MOVE");
    console.log("task:", task);
    console.log("target machine:", machine);
    console.log("runId:", runId);
    console.log("======================================");

    if (!runId) {
      setMessage(
        "No optimization run selected. Please run an optimization first.",
      );
      return;
    }

    if (!task?.id) {
      console.error(
        "Gantt move rejected: operation has no ID.",
        task,
      );

      setMessage(
        "This operation has no database ID. Refresh the planning.",
      );
      return;
    }

    const startMin = Number(task.start_min);
    const endMin = Number(task.end_min);

    if (
      !Number.isFinite(startMin) ||
      !Number.isFinite(endMin)
    ) {
      setMessage(
        "Invalid operation time.",
      );
      return;
    }

    if (endMin <= startMin) {
      setMessage(
        "Invalid operation duration.",
      );
      return;
    }

    try {
      setMessage(
        `Validating move of ${
          task.order_id || "operation"
        } → ${machine}...`,
      );

      // ========================================================
      // ENVOI AU BACKEND
      // ========================================================

      const result = await updatePlanningOperation(
        runId,
        task.id,
        {
          machine_id: String(machine),
          start_min: startMin,
          end_min: endMin,
        },
      );

      console.log(
        "Backend move response:",
        result,
      );

      // ========================================================
      // MOVE VALID
      // ========================================================

      if (result?.valid === true) {
        setMessage(
          `✓ ${
            task.order_id || "Operation"
          } successfully moved to ${machine}.`,
        );

        // ======================================================
        // RECHARGER LE PLANNING DEPUIS POSTGRESQL
        // ======================================================

        const refreshedPlanning =
          await getPlanning(runId);

        console.log(
          "Refreshed planning:",
          refreshedPlanning,
        );

        // Normalisation du nouveau planning
        let rows = [];

        if (Array.isArray(refreshedPlanning)) {
          rows = refreshedPlanning;
        } else if (
          refreshedPlanning &&
          Array.isArray(refreshedPlanning.planning)
        ) {
          rows = refreshedPlanning.planning;
        } else if (
          refreshedPlanning &&
          Array.isArray(refreshedPlanning.data)
        ) {
          rows = refreshedPlanning.data;
        } else if (
          refreshedPlanning &&
          Array.isArray(refreshedPlanning.results)
        ) {
          rows = refreshedPlanning.results;
        }

        if (onPlanningUpdated) {
          onPlanningUpdated(rows);
        }

        return;
      }

      // ========================================================
      // MOVE REJECTED
      // ========================================================

      const reasons =
        Array.isArray(result?.validation_errors) &&
        result.validation_errors.length > 0
          ? result.validation_errors.join(" | ")
          : "The operation cannot be moved.";

      setMessage(
        `✕ Move rejected: ${reasons}`,
      );

    } catch (error) {
      console.error(
        "Gantt operation update failed:",
        error,
      );

      const detail =
        error?.response?.data?.detail ||
        error?.response?.data?.message ||
        error?.message ||
        "Unknown error.";

      setMessage(
        `✕ Backend error: ${detail}`,
      );
    }
  }

  // ============================================================
  // RESET FILTERS
  // ============================================================

  function resetFilters() {
    setMachineFilter("ALL");
    setRiskFilter("ALL");
    setSearch("");
  }

  // ============================================================
  // RENDER
  // ============================================================

  return (
    <>
      <PageHeader
        title="Production Gantt"
        description="Visual production schedule by machine, with readable time scale, operation duration, priority and risk context."
        action={() =>
          setEditable((value) => !value)
        }
        actionLabel={
          editable
            ? "Lock schedule"
            : "Manual adjustment"
        }
        actionIcon={
          editable
            ? <Lock size={17} />
            : <Edit3 size={17} />
        }
      />

      {/* ====================================================== */}
      {/* COMMAND BAR                                            */}
      {/* ====================================================== */}

      <div className="gantt-command-bar panel">

        <div className="gantt-command-title">

          <div className="gantt-command-icon">
            <CalendarDays size={18} />
          </div>

          <div>
            <strong>
              Production timeline
            </strong>

            <span>
              Scroll horizontally to move through the schedule
            </span>
          </div>

        </div>

        <div className="gantt-stats">

          <span>
            <b>{stats.operations}</b> operations
          </span>

          <span>
            <b>{stats.machines}</b> machines
          </span>

          <span className="stat-danger">
            <b>{stats.high}</b> high risk
          </span>

          <span className="stat-warning">
            <b>{stats.late}</b> late
          </span>

        </div>

        <StatusBadge
          status={
            editable
              ? "EDIT MODE"
              : "LOCKED"
          }
        >
          {editable
            ? "EDIT MODE"
            : "LOCKED"}
        </StatusBadge>

      </div>

      {/* ====================================================== */}
      {/* FILTER BAR                                             */}
      {/* ====================================================== */}

      <div className="gantt-filter-bar panel">

        <div className="gantt-search">

          <Search size={15} />

          <input
            value={search}
            onChange={(event) =>
              setSearch(event.target.value)
            }
            placeholder="Search order, product, operation..."
          />

        </div>

        <select
          value={machineFilter}
          onChange={(event) =>
            setMachineFilter(event.target.value)
          }
        >
          {machines.map((machine) => (
            <option
              key={machine}
              value={machine}
            >
              {machine === "ALL"
                ? "All machines"
                : machine}
            </option>
          ))}
        </select>

        <select
          value={riskFilter}
          onChange={(event) =>
            setRiskFilter(event.target.value)
          }
        >
          <option value="ALL">
            All risks
          </option>

          <option value="HIGH">
            🔴 High risk
          </option>

          <option value="MEDIUM">
            🟠 Medium risk
          </option>

          <option value="LOW">
            🔵 Low risk
          </option>
        </select>

        <button
          type="button"
          className="button button-secondary"
          onClick={resetFilters}
        >
          <Filter size={15} />
          Reset
        </button>

        {/* ==================================================== */}
        {/* ZOOM                                                 */}
        {/* ==================================================== */}

        <div className="gantt-zoom-controls">

          <span>
            Zoom
          </span>

          <button
            type="button"
            className="gantt-icon-button"
            onClick={() =>
              setZoom((value) =>
                Math.max(
                  0.65,
                  Number(
                    (value - 0.15).toFixed(2),
                  ),
                ),
              )
            }
            title="Zoom out"
          >
            <ZoomOut size={15} />
          </button>

          <div className="gantt-zoom-value">
            {Math.round(zoom * 100)}%
          </div>

          <button
            type="button"
            className="gantt-icon-button"
            onClick={() =>
              setZoom((value) =>
                Math.min(
                  2,
                  Number(
                    (value + 0.15).toFixed(2),
                  ),
                ),
              )
            }
            title="Zoom in"
          >
            <ZoomIn size={15} />
          </button>

          <button
            type="button"
            className="gantt-icon-button"
            onClick={() =>
              setZoom(1)
            }
            title="Reset zoom"
          >
            <RefreshCw size={14} />
          </button>

        </div>

      </div>

      {/* ====================================================== */}
      {/* MESSAGE                                                */}
      {/* ====================================================== */}

      {message && (
        <div className="info-box gantt-message">
          <MoveIcon />
          <span>
            {message}
          </span>
        </div>
      )}

      {/* ====================================================== */}
      {/* GANTT                                                  */}
      {/* ====================================================== */}

      <div className="panel gantt-panel">

        <Gantt
          planning={planningRows}
          editable={editable}
          onMove={onMove}
          zoom={zoom}
          selectedMachine={machineFilter}
          riskFilter={riskFilter}
          search={search}
          onExplain={(operation) => setExplainOperation(operation)}
        />

      </div>

      {explainOperation && (
        <ExplainPlanPanel
          runId={runId}
          operation={explainOperation}
          onClose={() => setExplainOperation(null)}
        />
      )}
    </>
  );
}

function MoveIcon() {
  return <Edit3 size={15} />;
}

