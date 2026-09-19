import { NavLink } from "react-router-dom";
import {
  Activity,
  Bot,
  AlertTriangle,
  BarChart3,
  CalendarDays,
  ChevronRight,
  Factory,
  FileSpreadsheet,
  Gauge,
  Layers3,
  LayoutDashboard,
  Package,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Workflow,
} from "lucide-react";

const groups = [
  {
    label: "Overview",
    items: [
      ["Dashboard", "/", LayoutDashboard],
      ["Performance", "/performance", BarChart3],
    ],
  },
  {
    label: "Planning",
    items: [
      ["Planning Assistant", "/assistant", Bot],
      ["Orders", "/orders", Package],
      ["Production Plan", "/planning", CalendarDays],
      ["Gantt Schedule", "/gantt", Workflow],
    ],
  },
  {
    label: "Resources",
    items: [
      ["Machines", "/machines", Factory],
      ["Materials", "/materials", Layers3],
      ["Products & BOM", "/products", SlidersHorizontal],
    ],
  },
  {
    label: "Decision Support",
    items: [
      ["Optimization Center", "/optimization", Gauge],
      ["What-if Scenarios", "/scenarios", Sparkles],
      ["Data Management", "/data", FileSpreadsheet],
    ],
  },
];

export default function Layout({ children, apiOnline }) {
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Factory size={21} />
          </div>
          <div>
            <div className="brand-title">PROD OPTIMIZER</div>
            <div className="brand-subtitle">Smart Manufacturing</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {groups.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map(([label, path, Icon]) => (
                <NavLink
                  key={path}
                  to={path}
                  end={path === "/"}
                  className={({ isActive }) =>
                    `nav-link ${isActive ? "active" : ""}`
                  }
                >
                  <Icon size={17} />
                  <span>{label}</span>
                  <ChevronRight size={14} className="nav-chevron" />
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="online-indicator">
            <span className={`status-dot ${apiOnline ? "online" : "offline"}`} />
            <span>{apiOnline ? "API connected" : "API offline"}</span>
          </div>
          <NavLink to="/settings" className="settings-link">
            <Settings size={16} />
            Settings
          </NavLink>
        </div>
      </aside>

      <div className="main-shell">
        <header className="top-header">
          <div>
            <div className="breadcrumb">Production Planning / Smart Scheduling</div>
            <div className="page-context">Kénitra Plant • Automotive Wiring Harness</div>
          </div>
          <div className="top-header-right">
            <div className="header-chip">
              <CalendarDays size={15} />
              <span>Planning horizon: 07 Sep → 16 Oct 2026</span>
            </div>
            <div className="header-chip">
              <Activity size={15} />
              <span>Decision support</span>
            </div>
          </div>
        </header>

        <main className="content-area">{children}</main>
      </div>
    </div>
  );
}
