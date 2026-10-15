import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

interface Variant {
  id: string;
  sku: string;
  name: string;
}

interface Product {
  id: string;
  name: string;
  variants: Variant[];
}

interface Stock {
  variant_id: string;
  on_hand: number;
  reserved: number;
  available: number;
  is_low_stock?: boolean;
}

export default function Inventory() {
  const api = useApi();
  const [products, setProducts] = useState<Product[]>([]);
  const [stockMap, setStockMap] = useState<Record<string, Stock>>({});
  const [error, setError] = useState("");
  const [movementForm, setMovementForm] = useState({ variant_id: "", type: "purchase", quantity: "" });
  const [saving, setSaving] = useState(false);

  const loadProducts = async () => {
    try {
      const data = await api<Product[]>("/products");
      setProducts(data);
      const map: Record<string, Stock> = {};
      for (const p of data) {
        for (const v of p.variants) {
          try {
            map[v.id] = await api<Stock>(`/inventory/stock/${v.id}`);
          } catch {
            map[v.id] = { variant_id: v.id, on_hand: 0, reserved: 0, available: 0 };
          }
        }
      }
      setStockMap(map);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  };

  useEffect(() => { loadProducts(); }, [api]);

  const handleMovement = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api("/inventory/movements", {
        method: "POST",
        body: JSON.stringify({
          variant_id: movementForm.variant_id,
          movement_type: movementForm.type,
          quantity: Number(movementForm.quantity),
        }),
      });
      setMovementForm({ variant_id: "", type: "purchase", quantity: "" });
      loadProducts();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to record movement");
    } finally {
      setSaving(false);
    }
  };

  const allVariants = products.flatMap((p) => p.variants.map((v) => ({ ...v, productName: p.name })));

  return (
    <div>
      <h2 className="text-2xl font-semibold text-gray-900 mb-6">Inventory</h2>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">{error}</div>}

      <form onSubmit={handleMovement} className="bg-white border border-gray-200 rounded-lg p-4 mb-6 flex gap-3 items-end">
        <div className="flex-1">
          <label className="block text-xs text-gray-500 mb-1">Variant</label>
          <select required value={movementForm.variant_id} onChange={(e) => setMovementForm({ ...movementForm, variant_id: e.target.value })} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm">
            <option value="">Select variant...</option>
            {allVariants.map((v) => (
              <option key={v.id} value={v.id}>{v.productName} — {v.sku}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Type</label>
          <select value={movementForm.type} onChange={(e) => setMovementForm({ ...movementForm, type: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm">
            <option value="purchase">Purchase (+)</option>
            <option value="adjustment">Adjustment (+/-)</option>
            <option value="damage">Damage (-)</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Quantity</label>
          <input required type="number" value={movementForm.quantity} onChange={(e) => setMovementForm({ ...movementForm, quantity: e.target.value })} className="w-28 border border-gray-300 rounded-md px-3 py-2 text-sm" />
        </div>
        <button disabled={saving} type="submit" className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800 disabled:opacity-50">
          {saving ? "..." : "Record"}
        </button>
      </form>

      <div className="bg-white rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="px-4 py-3 font-medium">Product</th>
              <th className="px-4 py-3 font-medium">SKU</th>
              <th className="px-4 py-3 font-medium">On Hand</th>
              <th className="px-4 py-3 font-medium">Reserved</th>
              <th className="px-4 py-3 font-medium">Available</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {allVariants.map((v) => {
              const s = stockMap[v.id];
              return (
                <tr key={v.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-900">{v.productName}</td>
                  <td className="px-4 py-3 font-mono text-xs">{v.sku}</td>
                  <td className="px-4 py-3">{s?.on_hand ?? 0}</td>
                  <td className="px-4 py-3">{s?.reserved ?? 0}</td>
                  <td className="px-4 py-3 font-medium">{s?.available ?? 0}</td>
                  <td className="px-4 py-3">
                    {s?.is_low_stock ? (
                      <span className="text-xs font-medium px-2 py-1 rounded-full bg-red-100 text-red-700">Low stock</span>
                    ) : (
                      <span className="text-xs font-medium px-2 py-1 rounded-full bg-green-100 text-green-700">OK</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {allVariants.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">No variants — add products first</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
