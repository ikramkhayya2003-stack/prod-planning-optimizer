import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Factory,
  Info,
  PackageCheck,
  ShieldCheck,
  X,
} from "lucide-react";
import { explainPlanningOperation } from "../api";

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function reasonIcon(type) {
  switch (type) {
    case "load":
      return <Factory size={17} />;
    case "setup":
      return <Clock3 size={17} />;
    case "material":
      return <PackageCheck size={17} />;
    case "due_date":
      return <ShieldCheck size={17} />;
    default:
      return <CheckCircle2 size={17} />;
  }
}

function ReasonRow({ reason }) {
  const status = reason.status || "neutral";
  const Icon = status === "negative" ? AlertTriangle : reasonIcon;

  return (
    <div className={`explain-reason explain-reason-${status}`}>
      <div className="explain-reason-icon">
        {status === "negative" ? <AlertTriangle size={17} /> : reasonIcon(reason.type)}
      </div>
      <div className="explain-reason-body">
        <strong>{reason.title}</strong>
        <span>{reason.message}</span>
      </div>
      <div className="explain-reason-status">
        {status === "positive" ? "✓" : status === "negative" ? "!" : "•"}
      </div>
    </div>
  );
}

export default function ExplainPlanPanel({ runId, operation, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      if (!runId || !operation?.id) return;
      setLoading(true);
      setError("");
      setData(null);

      try {
        const result = await explainPlanningOperation(runId, operation.id);
        if (active) setData(result);
      } catch (err) {
        if (active) {
          setError(
            err?.response?.data?.detail ||
              err?.message ||
              "Unable to explain this operation.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
  }, [runId, operation?.id]);

  return (
    <aside className="explain-panel">
      <div className="explain-panel-header">
        <div>
          <div className="explain-eyebrow">DECISION SUPPORT</div>
          <h3>Explain the Plan</h3>
        </div>
        <button type="button" className="gantt-icon-button" onClick={onClose} title="Close">
          <X size={17} />
        </button>
      </div>

      {operation && (
        <div className="explain-operation-card">
          <div className="explain-operation-main">
            <strong>{operation.order_id || "Order"}</strong>
            <span>{operation.operation_code || `OP ${operation.operation_seq ?? ""}`}</span>
          </div>
          <div className="explain-machine-badge">
            <Factory size={15} />
            {operation.machine_id || "—"}
          </div>
        </div>
      )}

      {loading && (
        <div className="explain-loading">
          <div className="explain-spinner" />
          <span>Analyzing the optimized decision...</span>
        </div>
      )}

      {!loading && error && (
        <div className="explain-error">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      {!loading && data && (
        <>
          <div className="explain-summary">
            <div className="explain-summary-icon">
              <CheckCircle2 size={21} />
            </div>
            <div>
              <span>Why this machine?</span>
              <p>{data.summary}</p>
            </div>
          </div>

          <div className="explain-section-title">Decision evidence</div>
          <div className="explain-reasons">
            {data.reasons?.map((reason) => (
              <ReasonRow key={reason.type} reason={reason} />
            ))}
          </div>

          <div className="explain-section-title">Order context</div>
          <div className="explain-context-grid">
            <div><span>Customer</span><strong>{data.customer || "—"}</strong></div>
            <div><span>Priority</span><strong>{data.priority_class || "—"}</strong></div>
            <div><span>Due date</span><strong>{formatDate(data.due_date)}</strong></div>
            <div><span>Scheduled end</span><strong>{formatDate(data.end_datetime)}</strong></div>
          </div>

          <div className="explain-section-title">Compatible alternatives</div>
          <div className="explain-candidates">
            {(data.candidate_machines || []).map((candidate) => (
              <div className={`explain-candidate ${candidate.selected ? "selected" : ""}`} key={candidate.machine_id}>
                <div>
                  <strong>{candidate.machine_id}</strong>
                  {candidate.selected && <span className="explain-selected">SELECTED</span>}
                </div>
                <span>{Math.round(candidate.scheduled_minutes)} min load · {Math.round(candidate.setup_minutes)} min setup</span>
                {!candidate.selected && <ChevronRight size={15} />}
              </div>
            ))}
          </div>

          <div className="explain-note">
            <Info size={15} />
            <span>{data.explainability_note}</span>
          </div>
        </>
      )}
    </aside>
  );
}
