import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Factory,
  RefreshCw,
  TriangleAlert,
  Wrench,
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

import PageHeader from "../components/PageHeader";
import StatusBadge from "../components/StatusBadge";
import EmptyState from "../components/EmptyState";
import {
  createBreakdown,
  getMachineCalendar,
  getMachines,
} from "../api";

/**
 * Machine Management
 *
 * Responsibilities:
 * - Load machine master data
 * - Load machine KPI data
 * - Load machine calendar/capacity data
 * - Display utilization and availability
 * - Display capacity consistency checks
 * - Allow planner to simulate a machine breakdown
 */
export default function Machines({ kpis }) {
  const [baseMachines, setBaseMachines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selected, setSelected] = useState(null);

  const [calendarData, setCalendarData] = useState([]);
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [calendarError, setCalendarError] = useState("");
  const [calendarMachine, setCalendarMachine] = useState("ALL");

  /**
   * --------------------------------------------------------------------------
   * LOAD MACHINES
   * --------------------------------------------------------------------------
   */
  useEffect(() => {
    let alive = true;

    setLoading(true);
    setError("");

    getMachines()
      .then((data) => {
        if (!alive) return;

        setBaseMachines(
          Array.isArray(data?.machines)
            ? data.machines
            : []
        );
      })
      .catch((err) => {
        if (!alive) return;

        setError(
          err?.response?.data?.detail ||
            err?.message ||
            "Unable to load machines."
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
  }, []);

  /**
   * --------------------------------------------------------------------------
   * LOAD MACHINE CALENDAR
   * --------------------------------------------------------------------------
   */
  useEffect(() => {
    let alive = true;

    setCalendarLoading(true);
    setCalendarError("");

    getMachineCalendar()
      .then((data) => {
        if (!alive) return;

        setCalendarData(
          Array.isArray(data?.machines)
            ? data.machines
            : []
        );
      })
      .catch((err) => {
        if (!alive) return;

        setCalendarError(
          err?.response?.data?.detail ||
            err?.message ||
            "Unable to load machine calendar."
        );
      })
      .finally(() => {
        if (alive) {
          setCalendarLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, []);

  /**
   * --------------------------------------------------------------------------
   * MACHINE KPIs
   * --------------------------------------------------------------------------
   */
  const machineKpis = useMemo(() => {
    const machines = Array.isArray(kpis?.machines)
      ? kpis.machines
      : [];

    return new Map(
      machines.map((machine) => [
        machine.machine_id,
        machine,
      ])
    );
  }, [kpis]);

  /**
   * Merge master machine data + KPI data.
   */
  const machines = useMemo(() => {
    return baseMachines.map((machine) => ({
      ...machine,
      ...(machineKpis.get(machine.machine_id) || {}),
    }));
  }, [baseMachines, machineKpis]);

  /**
   * --------------------------------------------------------------------------
   * CHART DATA
   * --------------------------------------------------------------------------
   */
  const chart = useMemo(() => {
    return machines.map((machine) => ({
      machine: machine.machine_id,

      utilization: Number(
        machine.utilization_pct ?? 0
      ),

      availability: Number(
        machine.availability_pct ?? 0
      ),
    }));
  }, [machines]);

  /**
   * --------------------------------------------------------------------------
   * SELECTED CALENDAR DATA
   * --------------------------------------------------------------------------
   */
  const visibleCalendarMachines = useMemo(() => {
    return calendarData.filter(
      (machine) =>
        calendarMachine === "ALL" ||
        machine.machine_id === calendarMachine
    );
  }, [calendarData, calendarMachine]);

  /**
   * --------------------------------------------------------------------------
   * CAPACITY CONSISTENCY STATUS
   * --------------------------------------------------------------------------
   */
  const capacityStatus = useMemo(() => {
    const errors = visibleCalendarMachines.filter(
      (machine) =>
        machine.capacity_consistency_status === "ERROR"
    );

    const warnings = visibleCalendarMachines.filter(
      (machine) =>
        machine.capacity_consistency_status === "WARNING"
    );

    return {
      errors,
      warnings,
    };
  }, [visibleCalendarMachines]);

  /**
   * --------------------------------------------------------------------------
   * RENDER
   * --------------------------------------------------------------------------
   */
  return (
    <>
      <PageHeader
        title="Machine Management"
        description="Capacity, availability, utilization, maintenance and breakdown response."
      />

      {/* ------------------------------------------------------------------ */}
      {/* GLOBAL MACHINE ERROR                                               */}
      {/* ------------------------------------------------------------------ */}

      {error && (
        <div className="error-box">
          {error}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* MACHINE SECTION                                                     */}
      {/* ------------------------------------------------------------------ */}

      {loading ? (
        <div className="loading-box">
          <RefreshCw className="spin" />
          Loading machines…
        </div>
      ) : machines.length ? (
        <>
          {/* MACHINE CARDS */}
          <div className="machine-card-grid">
            {machines.map((machine) => (
              <MachineCard
                key={machine.machine_id}
                machine={machine}
                onBreakdown={() =>
                  setSelected(machine.machine_id)
                }
              />
            ))}
          </div>

          {/* DASHBOARD */}
          <section className="dashboard-grid">
            {/* UTILIZATION / AVAILABILITY */}
            <div className="panel span-7">
              <div className="panel-header">
                <div>
                  <h2>
                    Utilization & Availability
                  </h2>

                  <p>
                    Run KPI when a completed optimization
                    exists; otherwise availability is shown.
                  </p>
                </div>
              </div>

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
                      dataKey="availability"
                      name="Availability"
                      fill="#6B9188"
                      radius={[5, 5, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* PLANNER READING */}
            <div className="panel span-5">
              <div className="panel-header">
                <div>
                  <h2>
                    Planner reading
                  </h2>

                  <p>
                    Use these thresholds to spot
                    bottlenecks.
                  </p>
                </div>
              </div>

              <div className="management-list">
                <div>
                  <strong>&lt; 70%</strong>
                  <span>
                    Under-utilized resource
                  </span>
                </div>

                <div>
                  <strong>70–90%</strong>
                  <span>
                    Normal planning zone
                  </span>
                </div>

                <div>
                  <strong>&gt; 90%</strong>
                  <span>
                    Potential overload / low flexibility
                  </span>
                </div>

                <div>
                  <strong>Breakdown</strong>
                  <span>
                    Creates an event that the next
                    CP-SAT run must respect
                  </span>
                </div>
              </div>
            </div>
          </section>
        </>
      ) : (
        <EmptyState />
      )}

      {/* ------------------------------------------------------------------ */}
      {/* MACHINE CALENDAR                                                    */}
      {/* ------------------------------------------------------------------ */}

      <section className="panel machine-calendar-panel">
        <div className="panel-header">
          <div>
            <h2>
              Machine Calendar & Capacity
            </h2>

            <p>
              Machine-specific scheduled time,
              maintenance, available hours and effective
              capacity from Machine_Calendar.
            </p>
          </div>

          <select
            className="select-control"
            value={calendarMachine}
            onChange={(event) =>
              setCalendarMachine(event.target.value)
            }
          >
            <option value="ALL">
              All machines
            </option>

            {calendarData.map((machine) => (
              <option
                key={machine.machine_id}
                value={machine.machine_id}
              >
                {machine.machine_id}
              </option>
            ))}
          </select>
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* CALENDAR LOADING                                                  */}
        {/* ---------------------------------------------------------------- */}

        {calendarLoading ? (
          <div className="loading-box">
            <RefreshCw className="spin" />
            Loading machine calendar…
          </div>
        ) : calendarError ? (
          <div className="error-box">
            {calendarError}
          </div>
        ) : (
          <>
            {/* ------------------------------------------------------------ */}
            {/* CAPACITY CONSISTENCY CHECK                                    */}
            {/* ------------------------------------------------------------ */}

            {capacityStatus.errors.length > 0 ? (
              <div className="error-box capacity-check-box">
                <TriangleAlert size={17} />

                <div>
                  <strong>
                    Capacity consistency check
                  </strong>

                  <span>
                    {capacityStatus.errors.length} machine(s)
                    exceed the 10% capacity/cycle mismatch
                    threshold.
                  </span>
                </div>
              </div>
            ) : capacityStatus.warnings.length > 0 ? (
              <div className="warning-box capacity-check-box">
                <TriangleAlert size={17} />

                <div>
                  <strong>
                    Capacity consistency check
                  </strong>

                  <span>
                    {capacityStatus.warnings.length} machine(s)
                    have a 5–10% difference between
                    capacity_units_hour and base_cycle_sec.
                  </span>
                </div>
              </div>
            ) : (
              <div className="success-box capacity-check-box">
                <CheckCircle2 size={17} />

                <div>
                  <strong>
                    Capacity model consistent
                  </strong>

                  <span>
                    capacity_units_hour and base_cycle_sec
                    are within the 5% tolerance.
                  </span>
                </div>
              </div>
            )}

            {/* ------------------------------------------------------------ */}
            {/* CALENDAR TABLE                                                */}
            {/* ------------------------------------------------------------ */}

            {visibleCalendarMachines.length === 0 ? (
              <EmptyState />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Machine</th>
                      <th>Scheduled</th>
                      <th>Maintenance</th>
                      <th>Available</th>
                      <th>
                        Calendar availability
                      </th>
                      <th>
                        Capacity master
                      </th>
                      <th>
                        Implied from cycle
                      </th>
                      <th>Gap</th>
                      <th>Check</th>
                      <th>
                        Effective capacity
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {visibleCalendarMachines.map(
                      (machine) => (
                        <tr
                          key={machine.machine_id}
                        >
                          {/* MACHINE */}
                          <td>
                            <strong>
                              {machine.machine_id}
                            </strong>

                            <br />

                            <span className="muted">
                              {machine.machine_name ||
                                "—"}
                            </span>
                          </td>

                          {/* SCHEDULED */}
                          <td>
                            {Number(
                              machine.scheduled_hours ??
                                0
                            ).toFixed(2)}{" "}
                            h
                          </td>

                          {/* MAINTENANCE */}
                          <td>
                            {Number(
                              machine.maintenance_hours ??
                                0
                            ).toFixed(2)}{" "}
                            h
                          </td>

                          {/* AVAILABLE */}
                          <td>
                            <strong>
                              {Number(
                                machine.planned_available_hours ??
                                  0
                              ).toFixed(2)}{" "}
                              h
                            </strong>
                          </td>

                          {/* CALENDAR AVAILABILITY */}
                          <td>
                            {Number(
                              machine.calendar_availability_pct ??
                                0
                            ).toFixed(2)}
                            %
                          </td>

                          {/* CAPACITY MASTER */}
                          <td>
                            {Number(
                              machine.capacity_units_hour ??
                                0
                            ).toFixed(1)}{" "}
                            u/h
                          </td>

                          {/* IMPLIED CAPACITY */}
                          <td>
                            {Number(
                              machine.implied_capacity_units_hour ??
                                0
                            ).toFixed(1)}{" "}
                            u/h
                          </td>

                          {/* GAP */}
                          <td>
                            {machine.capacity_gap_pct ==
                            null
                              ? "—"
                              : `${Number(
                                  machine.capacity_gap_pct
                                ).toFixed(2)}%`}
                          </td>

                          {/* CHECK */}
                          <td>
                            <StatusBadge
                              status={
                                machine.capacity_consistency_status ||
                                "UNKNOWN"
                              }
                            >
                              {machine.capacity_consistency_status ||
                                "UNKNOWN"}
                            </StatusBadge>
                          </td>

                          {/* EFFECTIVE CAPACITY */}
                          <td>
                            <strong>
                              {Number(
                                machine.effective_capacity_units_hour ??
                                  0
                              ).toFixed(1)}{" "}
                              u/h
                            </strong>
                          </td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* BREAKDOWN MODAL                                                     */}
      {/* ------------------------------------------------------------------ */}

      {selected && (
        <BreakdownModal
          machineId={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

/**
 * ============================================================================
 * MACHINE CARD
 * ============================================================================
 */

function MachineCard({
  machine,
  onBreakdown,
}) {
  const util = Number(
    machine?.utilization_pct ?? 0
  );

  const capacity = Number(
    machine?.capacity_units_hour ?? 0
  );

  const availability = Number(
    machine?.availability_pct ?? 0
  );

  const isHighLoad = util > 90;

  return (
    <div className="machine-card">
      <div className="machine-card-head">
        {/* ICON */}
        <div className="machine-avatar">
          <Factory size={18} />
        </div>

        {/* MACHINE NAME */}
        <div>
          <strong>
            {machine?.machine_id || "—"}
          </strong>

          <span>
            {machine?.machine_name ||
              "Unnamed machine"}
          </span>
        </div>

        {/* STATUS */}
        <StatusBadge
          status={
            isHighLoad
              ? "HIGH LOAD"
              : "AVAILABLE"
          }
        >
          {isHighLoad
            ? "HIGH LOAD"
            : "AVAILABLE"}
        </StatusBadge>
      </div>

      {/* METRICS */}
      <div className="machine-metrics">
        <div>
          <span>
            Capacity/h
          </span>

          <strong>
            {capacity.toLocaleString()}
          </strong>
        </div>

        <div>
          <span>
            Availability
          </span>

          <strong>
            {availability.toFixed(1)}%
          </strong>
        </div>

        <div>
          <span>
            Utilization
          </span>

          <strong>
            {util.toFixed(1)}%
          </strong>
        </div>
      </div>

      {/* BREAKDOWN */}
      <button
        type="button"
        className="button button-secondary full-width"
        onClick={onBreakdown}
      >
        <Wrench size={15} />

        Simulate breakdown
      </button>
    </div>
  );
}

/**
 * ============================================================================
 * BREAKDOWN MODAL
 * ============================================================================
 */

function BreakdownModal({
  machineId,
  onClose,
}) {
  const [form, setForm] = useState({
    start: "2026-09-15T10:00",
    end: "2026-09-15T16:00",
    reason: "Emergency breakdown",
  });

  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  /**
   * --------------------------------------------------------------------------
   * FORM SUBMISSION
   * --------------------------------------------------------------------------
   */
  async function submit(event) {
    event.preventDefault();

    if (busy) {
      return;
    }

    setBusy(true);
    setMessage("");

    /**
     * Basic client-side validation.
     */
    if (!form.start || !form.end) {
      setMessage(
        "Start and end dates are required."
      );

      setBusy(false);
      return;
    }

    if (
      new Date(form.end) <=
      new Date(form.start)
    ) {
      setMessage(
        "The breakdown end time must be later than the start time."
      );

      setBusy(false);
      return;
    }

    try {
      await createBreakdown(
        machineId,
        form
      );

      setMessage(
        "Breakdown created successfully. Run a new optimization to propagate the event into the schedule."
      );
    } catch (err) {
      setMessage(
        err?.response?.data?.detail ||
          err?.message ||
          "Unable to create breakdown."
      );
    } finally {
      setBusy(false);
    }
  }

  /**
   * --------------------------------------------------------------------------
   * INPUT UPDATE
   * --------------------------------------------------------------------------
   */
  function updateField(field, value) {
    setForm((previous) => ({
      ...previous,
      [field]: value,
    }));
  }

  /**
   * --------------------------------------------------------------------------
   * MODAL
   * --------------------------------------------------------------------------
   */
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (
          event.target === event.currentTarget &&
          !busy
        ) {
          onClose();
        }
      }}
    >
      <form
        className="modal"
        onSubmit={submit}
        onMouseDown={(event) =>
          event.stopPropagation()
        }
      >
        {/* HEADER */}
        <div className="modal-header">
          <div>
            <h2>
              Simulate breakdown • {machineId}
            </h2>

            <p>
              This event will be stored in
              PostgreSQL.
            </p>
          </div>

          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        {/* FORM */}
        <div className="form-grid">
          <label>
            Start

            <input
              type="datetime-local"
              value={form.start}
              onChange={(event) =>
                updateField(
                  "start",
                  event.target.value
                )
              }
              disabled={busy}
              required
            />
          </label>

          <label>
            End

            <input
              type="datetime-local"
              value={form.end}
              onChange={(event) =>
                updateField(
                  "end",
                  event.target.value
                )
              }
              disabled={busy}
              required
            />
          </label>

          <label className="span-2">
            Reason

            <input
              value={form.reason}
              onChange={(event) =>
                updateField(
                  "reason",
                  event.target.value
                )
              }
              disabled={busy}
              placeholder="Enter breakdown reason"
            />
          </label>
        </div>

        {/* MESSAGE */}
        {message && (
          <div className="info-box">
            {message}
          </div>
        )}

        {/* ACTIONS */}
        <div className="modal-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={onClose}
            disabled={busy}
          >
            Close
          </button>

          <button
            type="submit"
            className="button button-danger"
            disabled={busy}
          >
            <AlertTriangle size={15} />

            {busy
              ? "Saving…"
              : "Create breakdown"}
          </button>
        </div>
      </form>
    </div>
  );
}