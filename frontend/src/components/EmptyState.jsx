import { Inbox } from "lucide-react";

export default function EmptyState({ title = "No data available", description = "Run an optimization or load data to populate this view." }) {
  return (
    <div className="empty-state">
      <Inbox size={28} />
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  );
}
