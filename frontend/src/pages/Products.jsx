import { useEffect, useMemo, useState } from "react";
import { Boxes, ChevronDown, ChevronRight, GitBranch, RefreshCw, Search } from "lucide-react";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import StatusBadge from "../components/StatusBadge";
import { getProduct, getProducts } from "../api";

export default function Products() {
  const [products, setProducts] = useState([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(null);
  const [details, setDetails] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getProducts({ limit: 500 })
      .then((data) => alive && setProducts(data.products || []))
      .catch((err) => alive && setError(err.response?.data?.detail || "Unable to load products."))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  const filtered = useMemo(() => products.filter((p) => `${p.product_id} ${p.product_name} ${p.family}`.toLowerCase().includes(query.toLowerCase())), [products, query]);

  async function toggle(productId) {
    if (open === productId) {
      setOpen(null);
      return;
    }
    setOpen(productId);
    if (!details[productId]) {
      try {
        const detail = await getProduct(productId);
        setDetails((prev) => ({ ...prev, [productId]: detail }));
      } catch (err) {
        setError(err.response?.data?.detail || `Unable to load ${productId}.`);
      }
    }
  }

  return (
    <>
      <PageHeader title="Products & BOM" description="Explore product families, BOM structure, routing sequence and compatible machines from PostgreSQL." />
      {error && <div className="error-box">{error}</div>}
      <div className="toolbar panel"><div className="search-box"><Search size={16} /><input placeholder="Search product, family…" value={query} onChange={(e) => setQuery(e.target.value)} /></div><div className="toolbar-spacer" /><span className="section-counter">{filtered.length} products</span></div>
      {loading ? <div className="loading-box"><RefreshCw className="spin" /> Loading products…</div> : filtered.length ? <div className="product-grid">{filtered.map((p) => { const detail = details[p.product_id]; return <div className="product-card" key={p.product_id}><button className="product-card-head" onClick={() => toggle(p.product_id)}><div><span className="product-code">{p.family}</span><strong>{p.product_id}</strong><span className="muted-cell">{p.product_name}</span></div>{open === p.product_id ? <ChevronDown size={18} /> : <ChevronRight size={18} />}</button>{open === p.product_id && <div className="product-detail"><div className="product-summary"><StatusBadge status={p.product_status}>{p.product_status}</StatusBadge><span>Cycle: {Number(p.cycle_time_min_per_unit || 0).toFixed(2)} min/u</span><span>Revision: {p.revision}</span></div><div className="detail-label"><GitBranch size={15} /> Routing</div>{detail?.routing?.length ? detail.routing.map((r) => <div className="routing-row" key={`${r.operation_seq}-${r.operation_code}`}><span>{r.operation_seq}</span><strong>{r.operation_code}</strong><span>{r.compatible_machines}</span><em>{Number(r.operation_time_min_per_unit || 0).toFixed(2)} min/u</em></div>) : <div className="loading-box">Loading routing…</div>}<div className="detail-label"><Boxes size={15} /> BOM</div>{detail?.bom?.length ? <div className="bom-list">{detail.bom.map((b) => <div className="bom-row" key={b.material_id}><strong>{b.material_id}</strong><span>{Number(b.qty_per_unit || 0).toLocaleString("fr-FR")} / unit</span><em>scrap {Number(b.scrap_factor_pct || 0).toFixed(1)}%</em></div>)}</div> : <EmptyState title="No BOM data" description="Check the product BOM in PostgreSQL." />}</div>}</div>; })}</div> : <EmptyState title="No products found" />}
    </>
  );
}
