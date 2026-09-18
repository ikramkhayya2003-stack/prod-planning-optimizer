export default function StatusBadge({ status, children }) {
  const value = String(status || "").toLowerCase();
  const tone = value.includes("late") || value.includes("high") || value.includes("fail")
    ? "danger"
    : value.includes("risk") || value.includes("medium") || value.includes("running")
      ? "warning"
      : value.includes("completed") || value.includes("on time") || value.includes("optimal") || value.includes("planned")
        ? "success"
        : "neutral";

  return <span className={`badge badge-${tone}`}>{children || status}</span>;
}
