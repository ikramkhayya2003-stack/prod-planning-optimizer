export default function KpiCard({ title, value, subtitle, icon, tone = "blue", trend }) {
  return (
    <div className={`kpi-card tone-${tone}`}>
      <div className="kpi-card-top">
        <div className="kpi-title">{title}</div>
        <div className="kpi-icon">{icon}</div>
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-meta">
        <span>{subtitle}</span>
        {trend && <span className={`kpi-trend ${trend.positive ? "positive" : "negative"}`}>{trend.text}</span>}
      </div>
    </div>
  );
}
