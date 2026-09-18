
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Boxes,
  CalendarClock,
  RefreshCw,
  Search,
  Truck,
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
import KpiCard from "../components/KpiCard";

import {
  getMaterials,
  getAllShortagePredictions,
} from "../api";

export default function Materials({ kpis }) {
  const [baseMaterials, setBaseMaterials] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [query, setQuery] = useState("");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [error, setError] = useState("");

  // ============================================================
  // LOAD MATERIALS
  // ============================================================

  const loadMaterials = async () => {
    setLoading(true);
    setError("");

    try {
      const data = await getMaterials({ limit: 500 });

      const materials = data.materials || [];

      setBaseMaterials(materials);

      // ========================================================
      // LOAD REAL SHORTAGE PREDICTIONS
      // ========================================================

      setPredictionLoading(true);

      const materialIds = materials.map(
        (material) => material.material_id,
      );

      const shortagePredictions =
        await getAllShortagePredictions(materialIds, {
          horizon_days: 120,
        });

      setPredictions(shortagePredictions);
    } catch (err) {
      console.error("Unable to load materials:", err);

      setError(
        err.response?.data?.detail ||
          err.message ||
          "Unable to load materials.",
      );
    } finally {
      setLoading(false);
      setPredictionLoading(false);
    }
  };

  useEffect(() => {
    let alive = true;

    const load = async () => {
      try {
        setLoading(true);
        setError("");

        const data = await getMaterials({ limit: 500 });

        if (!alive) return;

        const materials = data.materials || [];

        setBaseMaterials(materials);

        setPredictionLoading(true);

        const materialIds = materials.map(
          (material) => material.material_id,
        );

        const shortagePredictions =
          await getAllShortagePredictions(materialIds, {
            horizon_days: 120,
          });

        if (!alive) return;

        setPredictions(shortagePredictions);
      } catch (err) {
        if (!alive) return;

        console.error(
          "Unable to load materials:",
          err,
        );

        setError(
          err.response?.data?.detail ||
            err.message ||
            "Unable to load materials.",
        );
      } finally {
        if (alive) {
          setLoading(false);
          setPredictionLoading(false);
        }
      }
    };

    load();

    return () => {
      alive = false;
    };
  }, []);

  // ============================================================
  // MAP KPI DATA
  // ============================================================

  const materialKpis = useMemo(
    () =>
      new Map(
        (kpis?.materials || []).map((m) => [
          m.material_id,
          m,
        ]),
      ),
    [kpis],
  );

  // ============================================================
  // MAP SHORTAGE PREDICTIONS
  // ============================================================

  const predictionMap = useMemo(
    () =>
      new Map(
        predictions.map((prediction) => [
          prediction.material_id,
          prediction,
        ]),
      ),
    [predictions],
  );

  // ============================================================
  // MERGE MATERIAL + KPI + PREDICTION
  // ============================================================

  const materials = useMemo(
    () =>
      baseMaterials.map((material) => {
        const kpi =
          materialKpis.get(material.material_id) || {};

        const prediction =
          predictionMap.get(material.material_id) || {};

        return {
          ...material,
          ...kpi,

          // Real shortage prediction
          shortage_date:
            prediction.shortage_date || null,

          days_to_shortage:
            prediction.days_to_shortage ?? null,

          shortage_qty:
            Number(prediction.shortage_qty || 0),

          supplier_arrival_date:
            prediction.supplier_arrival_date || null,

          supplier_can_arrive_before_shortage:
            prediction.supplier_can_arrive_before_shortage,

          predicted_risk_level:
            prediction.risk_level ||
            material.risk_level ||
            "LOW",

          affected_orders:
            prediction.affected_orders || [],

          prediction_error:
            prediction.prediction_error || null,

          predicted_daily_consumption:
            Number(
              prediction.daily_consumption ??
                material.avg_daily_requirement ??
                0,
            ),

          predicted_current_stock:
            Number(
              prediction.current_stock ??
                material.on_hand_qty ??
                0,
            ),

          predicted_lead_time:
            Number(
              prediction.lead_time_days ??
                material.lead_time_days ??
                0,
            ),
        };
      }),
    [
      baseMaterials,
      materialKpis,
      predictionMap,
    ],
  );

  // ============================================================
  // FILTER
  // ============================================================

  const filtered = useMemo(
    () =>
      materials.filter((m) => {
        const matchesSearch =
          !query ||
          `${m.material_id} ${m.material_name} ${m.material_type}`
            .toLowerCase()
            .includes(query.toLowerCase());

        const risk =
          ["CRITICAL", "HIGH", "MEDIUM"].includes(
            String(
              m.predicted_risk_level || "",
            ).toUpperCase(),
          ) ||
          (
            m.days_to_shortage !== null &&
            Number(m.days_to_shortage) <= 15
          );

        return (
          matchesSearch &&
          (!criticalOnly || risk)
        );
      }),
    [materials, query, criticalOnly],
  );

  // ============================================================
  // KPI CALCULATIONS
  // ============================================================

  const critical = materials.filter(
    (m) => {
      const risk = String(
        m.predicted_risk_level || "LOW",
      ).toUpperCase();

      return (
        risk === "CRITICAL" ||
        risk === "HIGH"
      );
    },
  ).length;

  const predictedShortages =
    materials.filter(
      (m) =>
        m.shortage_date !== null &&
        m.days_to_shortage !== null,
    ).length;

  const averageCoverage = materials.length
    ? materials.reduce(
        (sum, m) =>
          sum +
          Number(
            m.coverage_days || 0,
          ),
        0,
      ) / materials.length
    : 0;

  // ============================================================
  // CHART
  // ============================================================

  const chart = filtered
    .slice(0, 15)
    .map((m) => ({
      material: m.material_id,

      stock: Number(
        m.predicted_current_stock || 0,
      ),

      safety: Number(
        m.safety_stock_qty || 0,
      ),
    }));

  // ============================================================
  // FORMAT DATE
  // ============================================================

  function formatDate(value) {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleDateString(
      "fr-FR",
    );
  }

  // ============================================================
  // RISK
  // ============================================================

  function getRiskStatus(material) {
    const risk = String(
      material.predicted_risk_level ||
        "LOW",
    ).toUpperCase();

    if (risk === "CRITICAL") {
      return "CRITICAL";
    }

    if (risk === "HIGH") {
      return "HIGH";
    }

    if (risk === "MEDIUM") {
      return "MEDIUM";
    }

    return "LOW";
  }

  function getRiskLabel(material) {
    const risk = getRiskStatus(material);

    if (risk === "CRITICAL") {
      return "CRITICAL";
    }

    if (risk === "HIGH") {
      return "HIGH RISK";
    }

    if (risk === "MEDIUM") {
      return "MEDIUM";
    }

    return "LOW";
  }

  // ============================================================
  // RENDER
  // ============================================================

  return (
    <>
      <PageHeader
        title="Material Availability"
        description="Monitor stock, shortage prediction, supplier lead time, coverage and production risk."
      />

      {error && (
        <div className="error-box">
          {error}
        </div>
      )}

      <section className="kpi-grid kpi-grid-4">
        <KpiCard
          title="Materials"
          value={
            materials.length || "—"
          }
          subtitle="Master data records"
          icon={<Boxes size={19} />}
        />

        <KpiCard
          title="Predicted Shortages"
          value={predictedShortages}
          subtitle="Materials with forecasted shortage"
          icon={
            <CalendarClock size={19} />
          }
          tone="amber"
        />

        <KpiCard
          title="High Risk"
          value={critical}
          subtitle="Critical or high shortage risk"
          icon={
            <AlertTriangle size={19} />
          }
          tone="red"
        />

        <KpiCard
          title="Avg Coverage"
          value={`${averageCoverage.toFixed(
            1,
          )}d`}
          subtitle="Current days of coverage"
          icon={<Boxes size={19} />}
          tone="green"
        />
      </section>

      {loading ? (
        <div className="loading-box">
          <RefreshCw className="spin" />
          Loading materials…
        </div>
      ) : (
        <div className="dashboard-grid">

          {/* ================================================== */}
          {/* STOCK CHART */}
          {/* ================================================== */}

          <div className="panel span-5">
            <div className="panel-header">
              <div>
                <h2>
                  Material Coverage
                </h2>

                <p>
                  Current stock versus safety stock.
                </p>
              </div>
            </div>

            {chart.length ? (
              <div className="chart-box">
                <ResponsiveContainer
                  width="100%"
                  height={450}
                >
                  <BarChart
                    data={chart}
                    layout="vertical"
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                    />

                    <XAxis type="number" />

                    <YAxis
                      dataKey="material"
                      type="category"
                      width={90}
                    />

                    <Tooltip />

                    <Bar
                      dataKey="stock"
                      name="Stock"
                      fill="#315A7D"
                      radius={[
                        0,
                        5,
                        5,
                        0,
                      ]}
                    />

                    <Bar
                      dataKey="safety"
                      name="Safety"
                      fill="#B79B6A"
                      radius={[
                        0,
                        5,
                        5,
                        0,
                      ]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState />
            )}
          </div>

          {/* ================================================== */}
          {/* MATERIAL RISK */}
          {/* ================================================== */}

          <div className="panel span-7">

            <div className="panel-header">
              <div>
                <h2>
                  Material Shortage Prediction
                </h2>

                <p>
                  {filtered.length} materials
                  displayed.
                  {predictionLoading &&
                    " Calculating predictions…"}
                </p>
              </div>
            </div>

            {/* TOOLBAR */}

            <div
              className="toolbar"
              style={{
                marginBottom: 12,
              }}
            >
              <div className="search-box compact">
                <Search size={15} />

                <input
                  placeholder="Search material…"
                  value={query}
                  onChange={(e) =>
                    setQuery(
                      e.target.value,
                    )
                  }
                />
              </div>

              <button
                className={`button ${
                  criticalOnly
                    ? "button-primary"
                    : "button-secondary"
                }`}
                onClick={() =>
                  setCriticalOnly(
                    (value) => !value,
                  )
                }
              >
                {criticalOnly
                  ? "High risk only"
                  : "All materials"}
              </button>
            </div>

            {/* TABLE */}

            {filtered.length ? (
              <div className="table-wrap">
                <table className="data-table">

                  <thead>
                    <tr>
                      <th>Material</th>
                      <th>Stock</th>
                      <th>Daily consumption</th>
                      <th>Shortage date</th>
                      <th>Days</th>
                      <th>Lead time</th>
                      <th>Supplier arrival</th>
                      <th>Risk</th>
                    </tr>
                  </thead>

                  <tbody>

                    {filtered.map(
                      (m) => {
                        const risk =
                          getRiskStatus(
                            m,
                          );

                        return (
                          <tr
                            key={
                              m.material_id
                            }
                          >

                            {/* MATERIAL */}

                            <td>
                              <strong>
                                {
                                  m.material_id
                                }
                              </strong>

                              <div className="muted-cell">
                                {
                                  m.material_name
                                }
                              </div>
                            </td>

                            {/* CURRENT STOCK */}

                            <td>
                              {fmt(
                                m.predicted_current_stock,
                              )}

                              <div className="muted-cell">
                                Safety:{" "}
                                {fmt(
                                  m.safety_stock_qty,
                                )}
                              </div>
                            </td>

                            {/* DAILY CONSUMPTION */}

                            <td>
                              {fmtDecimal(
                                m.predicted_daily_consumption,
                              )}
                              {" / day"}
                            </td>

                            {/* SHORTAGE DATE */}

                            <td>
                              {m.shortage_date ? (
                                <strong>
                                  {formatDate(
                                    m.shortage_date,
                                  )}
                                </strong>
                              ) : (
                                "No shortage"
                              )}
                            </td>

                            {/* DAYS TO SHORTAGE */}

                            <td>
                              {m.days_to_shortage !==
                              null ? (
                                <strong>
                                  {
                                    m.days_to_shortage
                                  }{" "}
                                  d
                                </strong>
                              ) : (
                                "—"
                              )}
                            </td>

                            {/* LEAD TIME */}

                            <td>
                              {fmtDecimal(
                                m.predicted_lead_time,
                              )}{" "}
                              d
                            </td>

                            {/* SUPPLIER ARRIVAL */}

                            <td>
                              <div>
                                <Truck
                                  size={14}
                                  style={{
                                    verticalAlign:
                                      "middle",
                                    marginRight:
                                      5,
                                  }}
                                />

                                {formatDate(
                                  m.supplier_arrival_date,
                                )}
                              </div>

                              {m.supplier_can_arrive_before_shortage !==
                                undefined && (
                                <div className="muted-cell">
                                  {m.supplier_can_arrive_before_shortage
                                    ? "Before shortage"
                                    : "After shortage"}
                                </div>
                              )}
                            </td>

                            {/* RISK */}

                            <td>
                              <StatusBadge
                                status={
                                  risk ===
                                  "CRITICAL"
                                    ? "CRITICAL"
                                    : risk ===
                                      "HIGH"
                                    ? "HIGH RISK"
                                    : risk ===
                                      "MEDIUM"
                                    ? "MEDIUM"
                                    : "LOW"
                                }
                              >
                                {
                                  getRiskLabel(
                                    m,
                                  )
                                }
                              </StatusBadge>
                            </td>

                          </tr>
                        );
                      },
                    )}

                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No materials found"
              />
            )}

          </div>
        </div>
      )}
    </>
  );
}

// ============================================================
// FORMATTERS
// ============================================================

function fmt(value) {
  return Number(
    value || 0,
  ).toLocaleString(
    "fr-FR",
    {
      maximumFractionDigits: 0,
    },
  );
}

function fmtDecimal(value) {
  return Number(
    value || 0,
  ).toLocaleString(
    "fr-FR",
    {
      minimumFractionDigits: 1,
      maximumFractionDigits: 2,
    },
  );
}

