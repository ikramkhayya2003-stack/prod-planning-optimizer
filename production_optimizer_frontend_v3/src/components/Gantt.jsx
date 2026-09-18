import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Clock3,
  GripVertical,
  Info,
  Lock,
  Move,
} from "lucide-react";
import EmptyState from "./EmptyState";

const HOUR = 60;
const DAY = 24 * HOUR;

function toMinutes(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function getTimeRange(planning) {
  const starts = planning
    .map((row) => toMinutes(row.start_min))
    .filter((v) => v !== null);
  const ends = planning
    .map((row) => toMinutes(row.end_min))
    .filter((v) => v !== null);

  if (starts.length && ends.length) {
    return {
      minStart: Math.min(...starts),
      maxEnd: Math.max(...ends),
    };
  }

  const dates = planning
    .flatMap((row) => [row.start_datetime, row.end_datetime])
    .map((value) => new Date(value))
    .filter((date) => !Number.isNaN(date.getTime()));

  if (!dates.length) return { minStart: 0, maxEnd: DAY };

  const first = Math.min(...dates.map((date) => date.getTime()));
  const last = Math.max(...dates.map((date) => date.getTime()));
  return {
    minStart: 0,
    maxEnd: Math.max(DAY, Math.ceil((last - first) / 60000)),
  };
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(start, end) {
  const s = toMinutes(start);
  const e = toMinutes(end);
  if (s === null || e === null) return "—";
  const minutes = Math.max(0, e - s);
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  if (hours === 0) return `${mins} min`;
  if (mins === 0) return `${hours} h`;
  return `${hours} h ${mins} min`;
}

function getRiskClass(risk) {
  const value = String(risk || "LOW").toUpperCase();
  if (value === "HIGH") return "gantt-task-high";
  if (value === "MEDIUM") return "gantt-task-medium";
  return "gantt-task-low";
}

function getRiskLabel(risk) {
  return String(risk || "LOW").toUpperCase();
}

function getBarText(row) {
  const order = row.order_id || "Order";
  const operation = row.operation_code || `OP ${row.operation_seq ?? ""}`;
  return `${order} · ${operation}`;
}

export default function Gantt({
  planning = [],
  onMove,
  editable = false,
  zoom = 1,
  selectedMachine = "ALL",
  riskFilter = "ALL",
  search = "",
  onExplain,
}) {
  const [dragged, setDragged] = useState(null);
  const [collapsed, setCollapsed] = useState({});

  const filteredPlanning = useMemo(() => {
    const query = search.trim().toLowerCase();
    return planning.filter((row) => {
      const machineMatch =
        selectedMachine === "ALL" ||
        String(row.machine_id) === String(selectedMachine);
      const riskMatch =
        riskFilter === "ALL" ||
        getRiskLabel(row.risk) === riskFilter;
      const searchMatch =
        !query ||
        [row.order_id, row.product_id, row.operation_code, row.machine_id]
          .map((v) => String(v || "").toLowerCase())
          .some((v) => v.includes(query));
      return machineMatch && riskMatch && searchMatch;
    });
  }, [planning, selectedMachine, riskFilter, search]);

  const machines = useMemo(() => {
    return [...new Set(filteredPlanning.map((row) => row.machine_id).filter(Boolean))];
  }, [filteredPlanning]);

  if (!planning.length) {
    return (
      <EmptyState
        title="No optimized schedule"
        description="Run CP-SAT to generate the production Gantt."
      />
    );
  }

  if (!filteredPlanning.length) {
    return (
      <div className="gantt-empty-filter">
        <Info size={18} />
        <strong>No operations match the selected filters.</strong>
        <span>Try another machine, risk level or search term.</span>
      </div>
    );
  }

  const { minStart, maxEnd } = getTimeRange(filteredPlanning);
  const span = Math.max(DAY, maxEnd - minStart);
  const start = Math.floor(minStart / DAY) * DAY;
  const end = Math.ceil(maxEnd / DAY) * DAY;
  const totalDays = Math.max(1, Math.ceil((end - start) / DAY));
  const hourWidth = Math.max(8, 13 * zoom);
  const timelineWidth = Math.max(900, ((end - start) / HOUR) * hourWidth);

  const dayTicks = Array.from({ length: totalDays }, (_, index) => {
    const minute = start + index * DAY;
    return { minute, label: formatTimelineDay(filteredPlanning, minute, minStart) };
  });

  const hourTicks = Array.from(
    { length: Math.ceil((end - start) / HOUR) },
    (_, index) => start + index * HOUR,
  );

  const dropOnMachine = (machineId) => {
    if (!editable || !dragged) return;
    onMove?.(dragged, machineId);
    setDragged(null);
  };

  const getPosition = (row) => {
    const rowStart = toMinutes(row.start_min);
    const rowEnd = toMinutes(row.end_min);
    if (rowStart === null || rowEnd === null) return null;

    const left = ((rowStart - start) / HOUR) * hourWidth;
    const width = Math.max(7, ((rowEnd - rowStart) / HOUR) * hourWidth);
    return { left, width };
  };

  return (
    <div className="gantt-v2">
      <div className="gantt-v2-legend">
        <span><i className="gantt-legend-dot production" /> Production</span>
        <span><i className="gantt-legend-dot high" /> High risk</span>
        <span><i className="gantt-legend-dot medium" /> Medium risk</span>
        <span><i className="gantt-legend-dot low" /> Low risk</span>
        <span className="gantt-legend-note"><Clock3 size={13} /> Width = operation duration</span>
      </div>

      <div className="gantt-v2-scroll">
        <div className="gantt-v2-canvas" style={{ minWidth: `${timelineWidth + 230}px` }}>
          <div className="gantt-v2-header">
            <div className="gantt-v2-machine-head">
              <span>MACHINE</span>
              <small>{machines.length} machines · {filteredPlanning.length} operations</small>
            </div>
            <div className="gantt-v2-time-head" style={{ width: `${timelineWidth}px` }}>
              <div className="gantt-day-row">
                {dayTicks.map((tick, index) => (
                  <div
                    className="gantt-day-cell"
                    key={tick.minute}
                    style={{ width: `${DAY / HOUR * hourWidth}px` }}
                  >
                    <strong>{tick.label}</strong>
                    <span>Day {index + 1}</span>
                  </div>
                ))}
              </div>
              <div className="gantt-hour-row">
                {hourTicks.map((minute) => (
                  <span
                    key={minute}
                    style={{ width: `${hourWidth}px` }}
                  >
                    {Math.round((minute - start) / HOUR) % 24}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {machines.map((machine) => {
            const rows = filteredPlanning
              .filter((row) => row.machine_id === machine)
              .sort((a, b) => Number(a.start_min) - Number(b.start_min));
            const isCollapsed = Boolean(collapsed[machine]);

            return (
              <div className={`gantt-machine-group ${isCollapsed ? "is-collapsed" : ""}`} key={machine}>
                <div className="gantt-machine-name">
                  <button
                    type="button"
                    className="gantt-collapse-button"
                    onClick={() =>
                      setCollapsed((current) => ({
                        ...current,
                        [machine]: !current[machine],
                      }))
                    }
                    aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${machine}`}
                  >
                    {isCollapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} />}
                  </button>
                  <div>
                    <strong>{machine}</strong>
                    <span>{rows.length} operations</span>
                  </div>
                </div>

                {!isCollapsed && (
                  <div
                    className="gantt-machine-track"
                    style={{ width: `${timelineWidth}px` }}
                    onDragOver={(event) => editable && event.preventDefault()}
                    onDrop={() => dropOnMachine(machine)}
                  >
                    <div className="gantt-hour-grid">
                      {hourTicks.map((minute) => (
                        <span key={minute} style={{ left: `${((minute - start) / HOUR) * hourWidth}px` }} />
                      ))}
                    </div>

                    {rows.map((row, index) => {
                      const position = getPosition(row);
                      if (!position) return null;

                      const label = getBarText(row);
                      const canShowLabel = position.width >= 90;
                      const setupMinutes = Number(row.setup_minutes || 0);

                      return (
                        <div
                          key={`${row.order_id}-${row.operation_seq}-${index}`}
                          className={`gantt-task ${getRiskClass(row.risk)}`}
                          style={{ left: `${position.left}px`, width: `${position.width}px` }}
                          draggable={editable}
                          onDragStart={() => setDragged(row)}
                          title={[
                            `${row.order_id || "Order"} · ${row.operation_code || "Operation"}`,
                            `Machine: ${row.machine_id || "—"}`,
                            `Product: ${row.product_id || "—"}`,
                            `Start: ${formatDateTime(row.start_datetime)}`,
                            `End: ${formatDateTime(row.end_datetime)}`,
                            `Duration: ${formatDuration(row.start_min, row.end_min)}`,
                            `Setup: ${setupMinutes} min`,
                            `Priority: ${row.priority_class || "—"}`,
                            `Risk: ${getRiskLabel(row.risk)}`,
                          ].join("\n")}
                        >
                          <span className="gantt-task-progress" />
                          {editable ? <GripVertical size={12} /> : <Lock size={11} />}
                          {canShowLabel ? (
                            <span className="gantt-task-label">
                              <strong>{row.order_id || "—"}</strong>
                              <small>{row.operation_code || `OP ${row.operation_seq ?? ""}`}</small>
                            </span>
                          ) : (
                            <span className="gantt-task-short">{String(row.order_id || "O").slice(-4)}</span>
                          )}
                          {setupMinutes > 0 && position.width >= 130 && (
                            <span className="gantt-task-setup">S {setupMinutes}m</span>
                          )}
                          <button
                            type="button"
                            className="gantt-explain-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              onExplain?.(row);
                            }}
                            onMouseDown={(event) => event.stopPropagation()}
                            title="Explain why this operation was scheduled here"
                          >
                            Why?
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {editable && (
        <div className="gantt-v2-hint">
          <Move size={15} />
          <span>Drag an operation to another machine. The backend must validate capability, sequence and calendar before saving.</span>
        </div>
      )}
    </div>
  );
}

function formatTimelineDay(planning, minute, fallbackStart) {
  const firstDate = planning
    .map((row) => new Date(row.start_datetime))
    .find((date) => !Number.isNaN(date.getTime()));

  if (firstDate) {
    const offsetMinutes = minute - fallbackStart;
    const date = new Date(firstDate.getTime() + offsetMinutes * 60000);
    return formatDate(date.toISOString());
  }

  return `T+${Math.round(minute / DAY)}d`;
}
