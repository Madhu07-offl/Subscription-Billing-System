import { useState } from 'react';
import { api, fetchAll } from '../api';
import { Icon, inr, useAsync, useDebounced } from '../ui';

/** page + search state for list screens; the search resets the page. */
export function useListState(initialTab) {
  const [page, setPage] = useState(1);
  const [q, setQRaw] = useState('');
  const [tab, setTabRaw] = useState(initialTab);
  const dq = useDebounced(q.trim(), 300);
  const setQ = v => { setQRaw(v); setPage(1); };
  const setTab = v => { setTabRaw(v); setPage(1); };
  return { page, setPage, q, setQ, dq, tab, setTab };
}

/** Active products (with variants), plans and customers for pickers. */
export function useCatalog({ customers = false, products = true, plans = true } = {}) {
  return useAsync(async () => {
    const [p, pl, c] = await Promise.all([
      products ? fetchAll(api.products, { isActive: true }) : [],
      plans ? fetchAll(api.plans, { isActive: true }) : [],
      customers ? fetchAll(api.customers) : [],
    ]);
    return { products: p, plans: pl, customers: c };
  }, []);
}

export const blankLine = () => ({ key: Math.random().toString(36).slice(2), productId: '', variantId: '', quantity: 1 });

/**
 * Editable product lines. lines: [{ key, productId, variantId, quantity }].
 * The price shown is the catalogue price (sales price + variant extra); the server re-prices on save.
 */
export function LineEditor({ lines, onChange, products, error }) {
  const upd = (i, patch) => onChange(lines.map((l, k) => (k === i ? { ...l, ...patch } : l)));
  const total = lines.reduce((a, l) => {
    const p = products.find(x => x.id === l.productId);
    const v = p?.variants.find(x => x.id === l.variantId);
    return a + (p ? (+p.salesPrice + (v ? +v.extraPrice : 0)) * (+l.quantity || 0) : 0);
  }, 0);
  return (
    <div className="lines">
      <div className="lines-h"><span>Product</span><span>Variant</span><span>Qty</span><span /></div>
      {lines.map((l, i) => {
        const p = products.find(x => x.id === l.productId);
        const variants = (p?.variants || []).filter(v => !v.isArchived);
        return (
          <div className="line" key={l.key}>
            <select className="input" aria-label="Product" value={l.productId} onChange={e => upd(i, { productId: e.target.value, variantId: '' })}>
              <option value="">Choose a product…</option>
              {products.map(x => <option key={x.id} value={x.id}>{x.name} · {inr(x.salesPrice)}</option>)}
            </select>
            <select className="input" aria-label="Variant" value={l.variantId} disabled={!variants.length} onChange={e => upd(i, { variantId: e.target.value })}>
              <option value="">{variants.length ? 'Standard' : 'No variants'}</option>
              {variants.map(v => <option key={v.id} value={v.id}>{v.attribute}: {v.value}{+v.extraPrice > 0 ? ` (+${inr(v.extraPrice)})` : ''}</option>)}
            </select>
            <input className="input" aria-label="Quantity" type="number" min="1" step="1" value={l.quantity} onChange={e => upd(i, { quantity: e.target.value })} />
            <button type="button" className="icon-btn sm" aria-label="Remove line" disabled={lines.length === 1}
              onClick={() => onChange(lines.filter((_, k) => k !== i))}><Icon name="trash" /></button>
          </div>
        );
      })}
      <div className="lines-f">
        <button type="button" className="btn btn-sm btn-ghost" onClick={() => onChange([...lines, blankLine()])}><Icon name="plus" />Add line</button>
        <span className="dim">Estimated before tax: <b className="text">{inr(total)}</b></span>
      </div>
      {error && <div className="err-txt">{error}</div>}
    </div>
  );
}

/** Validates lines; returns an error string or null. */
export function checkLines(lines, { required = true } = {}) {
  const filled = lines.filter(l => l.productId);
  if (required && filled.length === 0) return 'Add at least one product.';
  if (filled.some(l => !(+l.quantity >= 1) || !Number.isInteger(+l.quantity))) return 'Quantities must be whole numbers of at least 1.';
  return null;
}

export const toLineInput = lines => lines.filter(l => l.productId).map(l => ({
  productId: l.productId, ...(l.variantId ? { variantId: l.variantId } : {}), quantity: +l.quantity,
}));

export const can = (user, ...roles) => roles.includes(user.role);
