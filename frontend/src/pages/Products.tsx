import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";

interface Product {
  id: string;
  name: string;
  brand: string | null;
  category: string | null;
  status: string;
  variants: { id: string; sku: string; price: string }[];
  created_at: string;
}

export default function Products() {
  const api = useApi();
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", brand: "", category: "", sku: "", price: "" });
  const [saving, setSaving] = useState(false);

  const load = () => api<Product[]>("/products").then(setProducts).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [api]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api("/products", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          brand: form.brand || undefined,
          category: form.category || undefined,
          variants: form.sku ? [{ sku: form.sku, name: "Default", price: Number(form.price) }] : undefined,
        }),
      });
      setForm({ name: "", brand: "", category: "", sku: "", price: "" });
      setShowForm(false);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-gray-900">Products</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800"
        >
          {showForm ? "Cancel" : "New Product"}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">{error}</div>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white border border-gray-200 rounded-lg p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <input required placeholder="Product name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm" />
            <input placeholder="Brand" value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm" />
            <input placeholder="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm" />
          </div>
          <p className="text-xs text-gray-500 font-medium">First variant (optional)</p>
          <div className="grid grid-cols-2 gap-4">
            <input placeholder="SKU" value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm" />
            <input placeholder="Price" type="number" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm" />
          </div>
          <button disabled={saving} type="submit" className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800 disabled:opacity-50">
            {saving ? "Creating..." : "Create Product"}
          </button>
        </form>
      )}

      <div className="bg-white rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Brand</th>
              <th className="px-4 py-3 font-medium">Category</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Variants</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {products.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <Link to={`/products/${p.id}`} className="text-blue-600 hover:underline">{p.name}</Link>
                </td>
                <td className="px-4 py-3 text-gray-600">{p.brand ?? "—"}</td>
                <td className="px-4 py-3 text-gray-600">{p.category ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-medium px-2 py-1 rounded-full ${
                    p.status === "active" ? "bg-green-100 text-green-700" :
                    p.status === "archived" ? "bg-gray-100 text-gray-600" :
                    "bg-yellow-100 text-yellow-700"
                  }`}>{p.status}</span>
                </td>
                <td className="px-4 py-3 text-gray-600">{p.variants.length}</td>
              </tr>
            ))}
            {products.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">No products yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
