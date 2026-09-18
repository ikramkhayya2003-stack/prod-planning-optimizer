import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Filter,
  Package,
  Search,
  X,
} from "lucide-react";

import PageHeader from "../components/PageHeader";

import {
  getOrders,
} from "../api";


// ============================================================
// RISK CONFIG
// ============================================================

const RISK_CONFIG = {
  HIGH: {
    label: "HIGH",
    color: "risk-high",
    icon: "🔴",
  },

  MEDIUM: {
    label: "MEDIUM",
    color: "risk-medium",
    icon: "🟠",
  },

  LOW: {
    label: "LOW",
    color: "risk-low",
    icon: "🟢",
  },
};


// ============================================================
// FORMATTERS
// ============================================================

function formatDate(value) {

  if (!value) {
    return "—";
  }

  const date =
    new Date(value);

  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return "—";
  }

  return date.toLocaleDateString(
    "fr-FR"
  );
}


function formatDateTime(value) {

  if (!value) {
    return "—";
  }

  const date =
    new Date(value);

  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return "—";
  }

  return date.toLocaleString(
    "fr-FR",
    {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }
  );
}


function formatNumber(value) {

  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "0";
  }

  return Number(
    value
  ).toLocaleString(
    "fr-FR"
  );
}


// ============================================================
// RISK BADGE
// ============================================================

function RiskBadge({
  risk,
}) {

  const normalized =
    String(
      risk || "LOW"
    ).toUpperCase();

  const config =
    RISK_CONFIG[
      normalized
    ] ||
    RISK_CONFIG.LOW;

  return (
    <span
      className={
        `risk-badge ${config.color}`
      }
    >
      <span>
        {config.icon}
      </span>

      {config.label}
    </span>
  );
}


// ============================================================
// MAIN PAGE
// ============================================================

export default function Orders() {

  const [
    orders,
    setOrders,
  ] = useState([]);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState("");

  const [
    search,
    setSearch,
  ] = useState("");

  const [
    customer,
    setCustomer,
  ] = useState("ALL");

  const [
    priority,
    setPriority,
  ] = useState("ALL");

  const [
    statusFilter,
    setStatusFilter,
  ] = useState("ALL");

  const [
    riskFilter,
    setRiskFilter,
  ] = useState("ALL");

  const [
    selectedOrder,
    setSelectedOrder,
  ] = useState(null);


  // ==========================================================
  // LOAD
  // ==========================================================

  async function loadOrders() {

    try {

      setLoading(true);
      setError("");

      const runId =
        localStorage.getItem(
          "latest_run_id"
        );

      const data =
        await getOrders({
          limit: 500,
          run_id:
            runId || undefined,
        });

      setOrders(
        Array.isArray(
          data.orders
        )
          ? data.orders
          : []
      );

    } catch (err) {

      console.error(
        "Orders loading error:",
        err
      );

      setError(
        err?.response?.data?.detail ||
        "Unable to load orders."
      );

    } finally {

      setLoading(false);

    }
  }


  useEffect(() => {
    loadOrders();
  }, []);


  // ==========================================================
  // FILTER OPTIONS
  // ==========================================================

  const customers =
    useMemo(() => {

      const values =
        orders
          .map(
            (order) =>
              order.customer
          )
          .filter(Boolean);

      return [
        "ALL",
        ...Array.from(
          new Set(values)
        ),
      ];

    }, [orders]);


  // ==========================================================
  // FILTERED ORDERS
  // ==========================================================

  const filteredOrders =
    useMemo(() => {

      return orders.filter(
        (order) => {

          const searchValue =
            search
              .trim()
              .toLowerCase();

          const matchesSearch =
            !searchValue ||
            String(
              order.order_id ||
              ""
            )
              .toLowerCase()
              .includes(searchValue) ||
            String(
              order.product_id ||
              ""
            )
              .toLowerCase()
              .includes(searchValue) ||
            String(
              order.customer ||
              ""
            )
              .toLowerCase()
              .includes(searchValue);


          const matchesCustomer =
            customer === "ALL" ||
            order.customer ===
              customer;


          const matchesPriority =
            priority === "ALL" ||
            order.priority_class ===
              priority;


          const matchesStatus =
            statusFilter === "ALL" ||
            order.order_status ===
              statusFilter;


          const orderRisk =
            String(
              order.risk ||
              "LOW"
            ).toUpperCase();


          const matchesRisk =
            riskFilter === "ALL" ||
            orderRisk ===
              riskFilter;


          return (
            matchesSearch &&
            matchesCustomer &&
            matchesPriority &&
            matchesStatus &&
            matchesRisk
          );

        }
      );

    }, [
      orders,
      search,
      customer,
      priority,
      statusFilter,
      riskFilter,
    ]);


  // ==========================================================
  // RISK KPI
  // ==========================================================

  const highRiskCount =
    orders.filter(
      (order) =>
        String(
          order.risk ||
          "LOW"
        ).toUpperCase()
        === "HIGH"
    ).length;


  const mediumRiskCount =
    orders.filter(
      (order) =>
        String(
          order.risk ||
          "LOW"
        ).toUpperCase()
        === "MEDIUM"
    ).length;


  const lowRiskCount =
    orders.filter(
      (order) =>
        String(
          order.risk ||
          "LOW"
        ).toUpperCase()
        === "LOW"
    ).length;


  const lateCount =
    orders.filter(
      (order) =>
        Number(
          order.delay_hours ||
          0
        ) > 0
    ).length;


  return (
    <div className="orders-page">
      <PageHeader
        title="Orders"
        description={
          "Order management and delivery-risk analysis."
        }
      />


      {/* ======================================================
          KPI CARDS
      ====================================================== */}

      <div className="kpi-grid">

        <KpiCard
          icon={
            <Package size={18} />
          }
          label="Total Orders"
          value={
            formatNumber(
              orders.length
            )
          }
        />

        <KpiCard
          icon={
            <AlertTriangle
              size={18}
            />
          }
          label="High Risk"
          value={
            formatNumber(
              highRiskCount
            )
          }
          danger
        />

        <KpiCard
          icon={
            <Clock3 size={18} />
          }
          label="Late Orders"
          value={
            formatNumber(
              lateCount
            )
          }
        />

        <KpiCard
          icon={
            <CheckCircle2
              size={18}
            />
          }
          label="Low Risk"
          value={
            formatNumber(
              lowRiskCount
            )
          }
        />

      </div>


      {/* ======================================================
          FILTER BAR
      ====================================================== */}

      <div className="panel">

        <div className="filter-toolbar">

          <div className="search-box">

            <Search
              size={16}
            />

            <input
              value={search}
              onChange={(event) =>
                setSearch(
                  event.target.value
                )
              }
              placeholder="Search order, product or customer..."
            />

          </div>


          <select
            value={customer}
            onChange={(event) =>
              setCustomer(
                event.target.value
              )
            }
          >

            {customers.map(
              (value) => (
                <option
                  key={value}
                  value={value}
                >
                  {value === "ALL"
                    ? "All customers"
                    : value}
                </option>
              )
            )}

          </select>


          <select
            value={priority}
            onChange={(event) =>
              setPriority(
                event.target.value
              )
            }
          >

            <option value="ALL">
              All priorities
            </option>

            <option value="A">
              Priority A
            </option>

            <option value="B">
              Priority B
            </option>

            <option value="C">
              Priority C
            </option>

          </select>


          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(
                event.target.value
              )
            }
          >

            <option value="ALL">
              All status
            </option>

            <option value="OPEN">
              OPEN
            </option>

            <option value="PLANNED">
              PLANNED
            </option>

            <option value="IN PRODUCTION">
              IN PRODUCTION
            </option>

            <option value="COMPLETED">
              COMPLETED
            </option>

          </select>


          <select
            value={riskFilter}
            onChange={(event) =>
              setRiskFilter(
                event.target.value
              )
            }
          >

            <option value="ALL">
              All risks
            </option>

            <option value="HIGH">
              🔴 HIGH
            </option>

            <option value="MEDIUM">
              🟠 MEDIUM
            </option>

            <option value="LOW">
              🟢 LOW
            </option>

          </select>


          <button
            type="button"
            className="button button-secondary"
            onClick={() => {
              setSearch("");
              setCustomer("ALL");
              setPriority("ALL");
              setStatusFilter("ALL");
              setRiskFilter("ALL");
            }}
          >
            <Filter size={16} />
            Reset
          </button>

        </div>

      </div>


      {/* ======================================================
          ERROR
      ====================================================== */}

      {error && (
        <div className="alert alert-error">
          <X size={16} />
          {error}
        </div>
      )}


      {/* ======================================================
          TABLE
      ====================================================== */}

      <div className="panel">

        <div className="panel-header">

          <div>

            <h2>
              Order Risk Analysis
            </h2>

            <p>
              {filteredOrders.length}
              {" "}orders displayed.
            </p>

          </div>

          <button
            type="button"
            className="button button-secondary"
            onClick={loadOrders}
          >
            Refresh
          </button>

        </div>


        {loading ? (

          <div className="loading-state">
            Loading orders...
          </div>

        ) : filteredOrders.length === 0 ? (

          <div className="empty-state">
            No orders match the current filters.
          </div>

        ) : (

          <div className="table-wrapper">

            <table className="data-table">

              <thead>

                <tr>
                  <th>Order</th>
                  <th>Customer</th>
                  <th>Product</th>
                  <th>Qty</th>
                  <th>Priority</th>
                  <th>Risk</th>
                  <th>Expected Completion</th>
                  <th>Due Date</th>
                  <th>Delay</th>
                  <th>Action</th>
                </tr>

              </thead>


              <tbody>

                {filteredOrders.map(
                  (order) => (

                    <tr
                      key={
                        order.order_id
                      }
                    >

                      <td>
                        <strong>
                          {order.order_id}
                        </strong>

                        {order.is_urgent && (
                          <span className="urgent-tag">
                            URGENT
                          </span>
                        )}
                      </td>


                      <td>
                        {order.customer}
                      </td>


                      <td>
                        {order.product_id}
                      </td>


                      <td>
                        {formatNumber(
                          order.order_qty
                        )}
                      </td>


                      <td>
                        <PriorityBadge
                          priority={
                            order.priority_class
                          }
                        />
                      </td>


                      <td>
                        <RiskBadge
                          risk={
                            order.risk
                          }
                        />
                      </td>


                      <td>
                        {formatDateTime(
                          order.expected_completion
                        )}
                      </td>


                      <td>
                        {formatDate(
                          order.requested_due_date
                        )}
                      </td>


                      <td>

                        <DelayValue
                          hours={
                            order.delay_hours
                          }
                        />

                      </td>


                      <td>

                        <button
                          type="button"
                          className="button button-small"
                          onClick={() =>
                            setSelectedOrder(
                              order
                            )
                          }
                        >
                          Why?
                        </button>

                      </td>

                    </tr>

                  )
                )}

              </tbody>

            </table>

          </div>

        )}

      </div>


      {/* ======================================================
          LEGEND
      ====================================================== */}

      <div className="risk-legend">

        <RiskBadge risk="HIGH" />

        <RiskBadge risk="MEDIUM" />

        <RiskBadge risk="LOW" />

      </div>


      {/* ======================================================
          DETAIL DRAWER
      ====================================================== */}

      {selectedOrder && (

        <OrderRiskDrawer
          order={
            selectedOrder
          }
          onClose={() =>
            setSelectedOrder(
              null
            )
          }
        />

      )}

    </div>
  );
}


// ============================================================
// KPI CARD
// ============================================================

function KpiCard({
  icon,
  label,
  value,
  danger = false,
}) {

  return (

    <div
      className={
        `kpi-card ${
          danger
            ? "kpi-danger"
            : ""
        }`
      }
    >

      <div className="kpi-icon">
        {icon}
      </div>

      <div>
        <span className="kpi-label">
          {label}
        </span>

        <strong className="kpi-value">
          {value}
        </strong>
      </div>

    </div>
  );
}


// ============================================================
// PRIORITY
// ============================================================

function PriorityBadge({
  priority,
}) {

  const value =
    priority ||
    "—";

  return (
    <span
      className={
        `priority-badge priority-${value}`
      }
    >
      {value}
    </span>
  );
}


// ============================================================
// DELAY
// ============================================================

function DelayValue({
  hours,
}) {

  const value =
    Number(
      hours || 0
    );

  if (value <= 0) {

    return (
      <span className="delay-ok">
        On time
      </span>
    );
  }

  return (
    <span className="delay-danger">
      +{value.toFixed(1)} h
    </span>
  );
}


// ============================================================
// RISK DRAWER
// ============================================================

function OrderRiskDrawer({
  order,
  onClose,
}) {

  const reasons =
    Array.isArray(
      order.risk_reasons
    )
      ? order.risk_reasons
      : (
          Array.isArray(
            order.reasons
          )
            ? order.reasons
            : [
                "No detailed reason returned by API."
              ]
        );


  const materials =
    Array.isArray(
      order.material_risks
    )
      ? order.material_risks
      : [];


  return (

    <div className="drawer-overlay">

      <aside className="risk-drawer">

        <div className="drawer-header">

          <div>

            <span>
              Order Risk Analysis
            </span>

            <h2>
              {order.order_id}
            </h2>

          </div>

          <button
            type="button"
            className="icon-button"
            onClick={onClose}
          >
            <X size={18} />
          </button>

        </div>


        <div className="drawer-risk">

          <RiskBadge
            risk={
              order.risk
            }
          />

        </div>


        <div className="risk-summary">

          <InfoRow
            label="Customer"
            value={
              order.customer
            }
          />

          <InfoRow
            label="Product"
            value={
              order.product_id
            }
          />

          <InfoRow
            label="Priority"
            value={
              order.priority_class
            }
          />

          <InfoRow
            label="Expected completion"
            value={
              formatDateTime(
                order.expected_completion
              )
            }
          />

          <InfoRow
            label="Due date"
            value={
              formatDate(
                order.requested_due_date
              )
            }
          />

          <InfoRow
            label="Delay"
            value={
              Number(
                order.delay_days ||
                0
              ) > 0
                ? `${Number(
                    order.delay_days
                  ).toFixed(1)} days`
                : "On time"
            }
          />

        </div>


        <div className="drawer-section">

          <h3>
            Why is this order at risk?
          </h3>

          <div className="reason-list">

            {reasons.map(
              (reason, index) => (

                <div
                  className="reason-item"
                  key={index}
                >

                  <AlertTriangle
                    size={16}
                  />

                  <span>
                    {reason}
                  </span>

                </div>

              )
            )}

          </div>

        </div>


        {materials.length > 0 && (

          <div className="drawer-section">

            <h3>
              Material Risk
            </h3>

            <div className="mini-table">

              {materials.map(
                (material) => (

                  <div
                    className="mini-row"
                    key={
                      material.material_id
                    }
                  >

                    <strong>
                      {material.material_id}
                    </strong>

                    <span>
                      Coverage:{" "}
                      {
                        material.coverage_days
                      } days
                    </span>

                    <span>
                      LT:{" "}
                      {
                        material.lead_time_days
                      } days
                    </span>

                  </div>

                )
              )}

            </div>

          </div>

        )}

      </aside>

    </div>
  );
}


// ============================================================
// INFO ROW
// ============================================================

function InfoRow({
  label,
  value,
}) {

  return (

    <div className="info-row">

      <span>
        {label}
      </span>

      <strong>
        {value || "—"}
      </strong>

    </div>
  );
}