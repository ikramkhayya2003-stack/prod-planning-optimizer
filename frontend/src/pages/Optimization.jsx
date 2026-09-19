import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  BrainCircuit,
  CheckCircle2,
  Clock,
  Play,
  Scale,
  SlidersHorizontal,
  RefreshCw,
  AlertCircle,
} from "lucide-react";

import PageHeader from "../components/PageHeader";
import StatusBadge from "../components/StatusBadge";
import KpiCard from "../components/KpiCard";

import {
  startOptimization,
  getRun,
  getKpis,
} from "../api";


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

  return error?.message || "An unexpected error occurred.";
}


// ============================================================
// PRESETS
// ============================================================

const presets = {
  service: {
    tardiness: 0.70,
    setup: 0.15,
    inventory: 0.10,
    idle: 0.05,
  },

  inventory: {
    tardiness: 0.30,
    setup: 0.20,
    inventory: 0.40,
    idle: 0.10,
  },

  utilization: {
    tardiness: 0.30,
    setup: 0.20,
    inventory: 0.10,
    idle: 0.40,
  },
};


// ============================================================
// STATUS HELPERS
// ============================================================

const TERMINAL_STATUSES = new Set([
  "COMPLETED",
  "FAILED",
]);

const ACTIVE_STATUSES = new Set([
  "QUEUED",
  "RUNNING",
]);


// ============================================================
// MAIN COMPONENT
// ============================================================

export default function Optimization({
  runId,
  runStatus,
  kpis,
  onRunCreated,
}) {

  // ----------------------------------------------------------
  // LOCAL CONFIGURATION
  // ----------------------------------------------------------

  const [
    weights,
    setWeights,
  ] = useState({
    tardiness: 0.50,
    setup: 0.20,
    inventory: 0.15,
    idle: 0.15,
  });


  const [
    seconds,
    setSeconds,
  ] = useState(60);


  const [
    workers,
    setWorkers,
  ] = useState(8);

  const [planningStart, setPlanningStart] = useState("2026-09-07");
  const [planningEnd, setPlanningEnd] = useState("2026-10-16");
  const [includeWeekends, setIncludeWeekends] = useState(false);
  const [includeOvertime, setIncludeOvertime] = useState(false);


  // ----------------------------------------------------------
  // RUN STATE
  // ----------------------------------------------------------

  const [
    currentRunId,
    setCurrentRunId,
  ] = useState(
    runId ||
    localStorage.getItem(
      "latest_run_id"
    ) ||
    ""
  );


  const [
    currentStatus,
    setCurrentStatus,
  ] = useState(
    runStatus ||
    localStorage.getItem(
      "latest_run_status"
    ) ||
    "READY"
  );


  const [
    currentKpis,
    setCurrentKpis,
  ] = useState(
    kpis || null
  );


  const [
    busy,
    setBusy,
  ] = useState(false);


  const [
    loadingRun,
    setLoadingRun,
  ] = useState(false);


  const [
    error,
    setError,
  ] = useState("");


  const [
    lastUpdated,
    setLastUpdated,
  ] = useState(null);


  // ==========================================================
  // WEIGHT SUM
  // ==========================================================

  const totalWeight = useMemo(
    () => {

      return Object.values(
        weights
      ).reduce(
        (
          total,
          value
        ) =>
          total +
          Number(value || 0),
        0
      );

    },
    [weights]
  );


  const weightsValid =
    Math.abs(
      totalWeight - 1
    ) < 0.001;


  // ==========================================================
  // KPI SUMMARY
  // ==========================================================

  const summary =
    currentKpis?.summary ||
    kpis?.summary ||
    {};


  // ==========================================================
  // ACTIVE STATUS
  // ==========================================================

  const isActive =
    ACTIVE_STATUSES.has(
      String(
        currentStatus ||
        ""
      ).toUpperCase()
    );


  const isCompleted =
    String(
      currentStatus ||
      ""
    ).toUpperCase()
    === "COMPLETED";


  const isFailed =
    String(
      currentStatus ||
      ""
    ).toUpperCase()
    === "FAILED";


  // ==========================================================
  // CHANGE WEIGHT
  // ==========================================================

  function setWeight(
    key,
    value
  ) {

    const numericValue =
      Number(value);

    setWeights(
      (previous) => ({
        ...previous,
        [key]:
          Number.isFinite(
            numericValue
          )
            ? numericValue
            : 0,
      })
    );
  }


  // ==========================================================
  // PRESET
  // ==========================================================

  function applyPreset(
    name
  ) {

    if (
      !presets[name]
    ) {
      return;
    }

    setWeights(
      {
        ...presets[name],
      }
    );

    setError("");
  }


  // ==========================================================
  // LOAD RUN STATUS
  // ==========================================================

  async function refreshRun(
    targetRunId
  ) {

    if (!targetRunId) {
      return null;
    }

    try {

      const result =
        await getRun(
          targetRunId
        );

      const status =
        result?.status ||
        "READY";

      setCurrentRunId(
        result.run_id ||
        targetRunId
      );

      setCurrentStatus(
        status
      );

      setLastUpdated(
        new Date()
      );

      localStorage.setItem(
        "latest_run_id",
        result.run_id ||
        targetRunId
      );

      localStorage.setItem(
        "latest_run_status",
        status
      );

      return result;

    } catch (err) {

      console.error(
        "Run status error:",
        err
      );

      throw err;
    }
  }


  // ==========================================================
  // LOAD KPIS
  // ==========================================================

  async function refreshKpis(
    targetRunId
  ) {

    if (!targetRunId) {
      return null;
    }

    try {

      const result =
        await getKpis(
          targetRunId
        );

      setCurrentKpis(
        result
      );

      return result;

    } catch (err) {

      console.error(
        "KPI loading error:",
        err
      );

      // Do not fail the run status just
      // because KPI data is not ready yet.
      return null;
    }
  }


  // ==========================================================
  // POLLING
  // ==========================================================

  useEffect(
    () => {

      if (!currentRunId) {
        return undefined;
      }

      let cancelled = false;

      async function poll() {

        try {

          const run =
            await refreshRun(
              currentRunId
            );

          if (
            cancelled ||
            !run
          ) {
            return;
          }

          const status =
            String(
              run.status ||
              ""
            ).toUpperCase();

          // --------------------------------------------------
          // LOAD KPI ONLY WHEN USEFUL
          // --------------------------------------------------

          if (
            status === "COMPLETED"
          ) {

            await refreshKpis(
              currentRunId
            );

            return;
          }

          // --------------------------------------------------
          // TERMINAL FAILURE
          // --------------------------------------------------

          if (
            status === "FAILED"
          ) {

            return;
          }

        } catch (err) {

          if (!cancelled) {

            console.error(
              "Polling error:",
              err
            );

          }
        }

      }


      // Immediate refresh
      poll();


      // ------------------------------------------------------
      // Poll every 2 seconds only while active
      // ------------------------------------------------------

      const intervalId =
        setInterval(
          async () => {

            const status =
              String(
                localStorage.getItem(
                  "latest_run_status"
                ) ||
                currentStatus ||
                ""
              ).toUpperCase();

            if (
              !ACTIVE_STATUSES.has(
                status
              )
            ) {
              return;
            }

            await poll();

          },
          2000
        );


      return () => {

        cancelled = true;

        clearInterval(
          intervalId
        );

      };

    },
    [
      currentRunId,
    ]
  );


  // ==========================================================
  // SYNC PROPS FROM PARENT
  // ==========================================================

  useEffect(
    () => {

      if (runId) {

        setCurrentRunId(
          runId
        );

        localStorage.setItem(
          "latest_run_id",
          runId
        );
      }

    },
    [runId]
  );


  useEffect(
    () => {

      if (runStatus) {

        setCurrentStatus(
          runStatus
        );

        localStorage.setItem(
          "latest_run_status",
          runStatus
        );
      }

    },
    [runStatus]
  );


  useEffect(
    () => {

      if (kpis) {
        setCurrentKpis(
          kpis
        );
      }

    },
    [kpis]
  );


  // ==========================================================
  // RUN OPTIMIZATION
  // ==========================================================

  async function runOptimization() {

    if (!weightsValid) {

      setError(
        "The objective weights must sum to 100%."
      );

      return;
    }

    if (!planningStart || !planningEnd || planningEnd < planningStart) {
      setError("The planning horizon is invalid.");
      return;
    }


    if (isActive) {

      setError(
        "An optimization is already running."
      );

      return;
    }


    try {

      setBusy(
        true
      );

      setError("");


      // ------------------------------------------------------
      // REQUEST
      // ------------------------------------------------------

      const payload = {

        max_time_seconds:
          Number(seconds),

        num_workers:
          Number(workers),

        random_seed:
          42,

        planning_start_date: planningStart,
        planning_end_date: planningEnd,
        include_weekends: includeWeekends,
        include_overtime: includeOvertime,

        weights: {

          tardiness:
            Number(
              weights.tardiness
            ),

          setup:
            Number(
              weights.setup
            ),

          inventory:
            Number(
              weights.inventory
            ),

          idle:
            Number(
              weights.idle
            ),
        },
      };


      console.log(
        "OPTIMIZATION REQUEST",
        payload
      );


      // ------------------------------------------------------
      // POST /optimize
      // ------------------------------------------------------

      const result =
        await startOptimization(
          payload
        );


      console.log(
        "OPTIMIZATION RESPONSE",
        result
      );


      if (
        !result?.run_id
      ) {

        throw new Error(
          "The API did not return a run_id."
        );

      }


      // ------------------------------------------------------
      // STORE RUN
      // ------------------------------------------------------

      const newRunId =
        result.run_id;


      setCurrentRunId(
        newRunId
      );


      setCurrentStatus(
        result.status ||
        "QUEUED"
      );


      setCurrentKpis(
        null
      );


      localStorage.setItem(
        "latest_run_id",
        newRunId
      );


      localStorage.setItem(
        "latest_run_status",
        result.status ||
        "QUEUED"
      );


      setLastUpdated(
        new Date()
      );


      // ------------------------------------------------------
      // INFORM PARENT
      // ------------------------------------------------------

      if (
        typeof onRunCreated
        === "function"
      ) {

        onRunCreated(
          result
        );

      }

    } catch (err) {

      console.error(
        "Optimization request failed:",
        err
      );


      const message = getErrorMessage(err);

      setError(message);

    } finally {

      setBusy(
        false
      );

    }
  }


  // ==========================================================
  // MANUAL REFRESH
  // ==========================================================

  async function handleRefresh() {

    if (
      !currentRunId
    ) {

      return;

    }

    try {

      setLoadingRun(
        true
      );

      setError("");

      await refreshRun(
        currentRunId
      );

      const storedStatus =
        localStorage.getItem(
          "latest_run_status"
        );

      if (
        storedStatus ===
        "COMPLETED"
      ) {

        await refreshKpis(
          currentRunId
        );

      }

    } catch (err) {

      setError(
        "Unable to refresh the optimization status."
      );

    } finally {

      setLoadingRun(
        false
      );

    }
  }


  // ==========================================================
  // DISPLAY STATUS
  // ==========================================================

  const displayStatus =
    currentStatus ||
    "READY";


  const statusMessage =
    isCompleted
      ? "Optimization completed successfully."
      : isFailed
        ? "Optimization finished with an error or without a feasible solution."
        : isActive
          ? "CP-SAT solver is working..."
          : currentRunId
            ? "Run created. Waiting for solver..."
            : "No optimization run yet.";


  // ==========================================================
  // RENDER
  // ==========================================================

  return (
    <>

      <PageHeader
        title="Optimization Center"
        description="Configure the planning objective, launch CP-SAT, and monitor the optimization run in real time."
      />

      <section className="panel" style={{ marginBottom: 20 }}>
        <div className="panel-header">
          <div>
            <h2>Planning Horizon</h2>
            <p>Select the period used by the CP-SAT scheduling engine.</p>
          </div>
          <Clock size={20} />
        </div>

        <div className="form-grid">
          <label>
            From
            <input
              type="date"
              value={planningStart}
              onChange={(e) => {
                setPlanningStart(e.target.value);
                if (planningEnd < e.target.value) {
                  setPlanningEnd(e.target.value);
                }
              }}
            />
          </label>

          <label>
            To
            <input
              type="date"
              min={planningStart}
              value={planningEnd}
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
      </section>


      {/* ======================================================
          MAIN GRID
      ====================================================== */}

      <section
        className="dashboard-grid"
      >

        {/* ====================================================
            OBJECTIVES
        ==================================================== */}

        <div
          className="panel span-7"
        >

          <div
            className="panel-header"
          >

            <div>

              <h2>
                Objective configuration
              </h2>

              <p>
                Adjust the relative importance of
                service, setup, inventory and
                machine idle time.
              </p>

            </div>


            <StatusBadge
              status={
                weightsValid
                  ? "READY"
                  : "INVALID"
              }
            >
              {
                weightsValid
                  ? "READY"
                  : "WEIGHTS ≠ 100%"
              }
            </StatusBadge>

          </div>


          {/* ==================================================
              PRESETS
          ================================================== */}

          <div
            className="preset-row"
          >

            <button
              type="button"
              className="preset-card"
              onClick={() =>
                applyPreset(
                  "service"
                )
              }
            >

              <span>
                <Scale size={17} />
              </span>

              <strong>
                Customer Service First
              </strong>

              <small>
                Prioritize due dates and
                priority-A orders.
              </small>

            </button>


            <button
              type="button"
              className="preset-card"
              onClick={() =>
                applyPreset(
                  "inventory"
                )
              }
            >

              <span>
                <SlidersHorizontal
                  size={17}
                />
              </span>

              <strong>
                Inventory Reduction
              </strong>

              <small>
                Reduce average inventory
                while protecting service.
              </small>

            </button>


            <button
              type="button"
              className="preset-card"
              onClick={() =>
                applyPreset(
                  "utilization"
                )
              }
            >

              <span>
                <SlidersHorizontal
                  size={17}
                />
              </span>

              <strong>
                Machine Utilization
              </strong>

              <small>
                Reduce internal idle time
                and improve machine loading.
              </small>

            </button>

          </div>


          {/* ==================================================
              SLIDERS
          ================================================== */}

          <div
            className="slider-list"
          >

            {Object.entries(
              {
                tardiness:
                  "Customer service / tardiness",

                setup:
                  "Setup time",

                inventory:
                  "Inventory",

                idle:
                  "Machine idle time",
              }
            ).map(
              ([
                key,
                label,
              ]) => (

                <div
                  className="slider-row"
                  key={key}
                >

                  <div>

                    <strong>
                      {label}
                    </strong>

                    <span>
                      {(
                        Number(
                          weights[key]
                        ) * 100
                      ).toFixed(0)}
                      %
                    </span>

                  </div>


                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={
                      weights[key]
                    }
                    onChange={(
                      event
                    ) =>
                      setWeight(
                        key,
                        event.target.value
                      )
                    }
                  />

                </div>

              )
            )}

          </div>


          {/* ==================================================
              TOTAL WEIGHT
          ================================================== */}

          <div
            className={
              `weight-total ${
                weightsValid
                  ? "weight-valid"
                  : "weight-invalid"
              }`
            }
          >

            <span>
              Total weight
            </span>

            <strong>
              {
                (
                  totalWeight *
                  100
                ).toFixed(0)
              }%
            </strong>

            <small>
              {
                weightsValid
                  ? "Valid objective configuration."
                  : "Weights must sum to exactly 100%."
              }
            </small>

          </div>


          {/* ==================================================
              PARAMETERS
          ================================================== */}

          <div
            className="run-parameters"
          >

            <label>

              Solve time (seconds)

              <input
                type="number"
                min="5"
                max="3600"
                value={
                  seconds
                }
                onChange={(
                  event
                ) =>
                  setSeconds(
                    event.target.value
                  )
                }
              />

            </label>


            <label>

              Workers

              <input
                type="number"
                min="1"
                max="64"
                value={
                  workers
                }
                onChange={(
                  event
                ) =>
                  setWorkers(
                    event.target.value
                  )
                }
              />

            </label>

          </div>


          {/* ==================================================
              ERROR
          ================================================== */}

          {error && (

            <div
              className="error-box"
            >

              <AlertCircle
                size={17}
              />

              <span>
                {error}
              </span>

            </div>

          )}


          {/* ==================================================
              RUN BUTTON
          ================================================== */}

          <button
            type="button"
            className="button button-primary large-button"
            onClick={
              runOptimization
            }
            disabled={
              busy ||
              isActive ||
              !weightsValid
            }
          >

            {busy ? (

              <>
                <Clock
                  size={17}
                  className="spin"
                />

                Submitting...
              </>

            ) : isActive ? (

              <>
                <Clock
                  size={17}
                  className="spin"
                />

                Optimization running...
              </>

            ) : (

              <>
                <Play
                  size={17}
                />

                Run CP-SAT Optimization
              </>

            )}

          </button>

        </div>


        {/* ====================================================
            LATEST RUN
        ==================================================== */}

        <div
          className="panel span-5"
        >

          <div
            className="panel-header"
          >

            <div>

              <h2>
                Latest optimization
              </h2>

              <p>
                Real-time state of the selected run.
              </p>

            </div>


            <button
              type="button"
              className="button button-secondary"
              onClick={
                handleRefresh
              }
              disabled={
                !currentRunId ||
                loadingRun
              }
            >

              <RefreshCw
                size={15}
                className={
                  loadingRun
                    ? "spin"
                    : ""
                }
              />

              Refresh

            </button>

          </div>


          <div
            className="optimization-status"
          >

            <StatusBadge
              status={
                displayStatus
              }
            >
              {
                displayStatus
              }
            </StatusBadge>


            <strong>
              {
                currentRunId ||
                "No run yet"
              }
            </strong>


            <span>
              {statusMessage}
            </span>


            {lastUpdated && (

              <small>
                Last update:{" "}
                {
                  lastUpdated.toLocaleTimeString(
                    "fr-FR"
                  )
                }
              </small>

            )}

          </div>


          <div
            className="mini-kpi-list"
          >

            <Mini
              label="Service"
              value={
                `${Number(
                  summary.service_rate_pct ||
                  0
                ).toFixed(1)}%`
              }
            />


            <Mini
              label="Late orders"
              value={
                summary.late_orders ??
                "—"
              }
            />


            <Mini
              label="Setup"
              value={
                `${
                  (
                    Number(
                      summary.total_setup_min ||
                      0
                    ) / 60
                  ).toFixed(1)
                }h`
              }
            />


            <Mini
              label="Avg tardiness"
              value={
                `${
                  Number(
                    summary.avg_tardiness_hours ||
                    0
                  ).toFixed(1)
                }h`
              }
            />

          </div>

        </div>

      </section>


      {/* ======================================================
          GLOBAL KPI CARDS
      ====================================================== */}

      <section
        className="kpi-grid kpi-grid-3"
      >

        <KpiCard
          title="Solver"
          value={
            displayStatus
          }
          subtitle="Latest optimization status"
          icon={
            <BrainCircuit
              size={19}
            />
          }
        />


        <KpiCard
          title="Objective"
          value={
            currentKpis?.objective_value ??
            kpis?.objective_value ??
            "—"
          }
          subtitle="Latest objective value"
          icon={
            <Scale
              size={19}
            />
          }
          tone="green"
        />


        <KpiCard
          title="Plan Quality"
          value={
            isCompleted
              ? "Available"
              : isFailed
                ? "Not available"
                : "Pending"
          }
          subtitle={
            isCompleted
              ? "Planning and KPI records stored in PostgreSQL"
              : "Waiting for a completed optimization run"
          }
          icon={
            <CheckCircle2
              size={19}
            />
          }
          tone="blue"
        />

      </section>

    </>
  );
}


// ============================================================
// MINI KPI
// ============================================================

function Mini({
  label,
  value,
}) {

  return (

    <div
      className="mini-row"
    >

      <span>
        {label}
      </span>

      <strong>
        {value}
      </strong>

    </div>

  );
}