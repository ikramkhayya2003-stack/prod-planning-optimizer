import { RefreshCw } from "lucide-react";

export default function PageHeader({ title, description, action, actionLabel, actionIcon }) {
  return (
    <div className="page-header">
      <div>
        <div className="eyebrow">PRODUCTION PLANNING OPTIMIZER</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && (
        <button className="button button-primary" onClick={action}>
          {actionIcon || <RefreshCw size={17} />}
          {actionLabel || "Refresh"}
        </button>
      )}
    </div>
  );
}
