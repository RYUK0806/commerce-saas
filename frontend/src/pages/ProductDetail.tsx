import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";

interface Variant {
  id: string;
  sku: string;
  name: string;
  price: string;
  is_active: boolean;
}

interface Product {
  id: string;
  name: string;
  brand: string | null;
  category: string | null;
  description: string | null;
  status: string;
  hsn_code: string | null;
  tax_rate: string | null;
  variants: Variant[];
  images: { id: string; url: string; alt_text: string | null; is_primary: boolean }[];
}

export default function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const api = useApi();
  const [product, setProduct] = useState<Product | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: "", brand: "", category: "", description: "", status: "" });
  const [variantForm, setVariantForm] = useState({ sku: "", name: "", price: "" });
  const [showVariantForm, setShowVariantForm] = useState(false);

  const load = () =>
    api<Product>(`/products/${id}`).then((p) => {
      setProduct(p);
      setForm({ name: p.name, brand: p.brand ?? "", category: p.category ?? "", description: p.description ?? "", status: p.status });
    }).catch((e) => setError(e.message));

  useEffect(() => { load(); }, [api, id]);

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api(`/products/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: form.name,
          brand: form.brand || null,
          category: form.category || null,
          description: form.description || null,
          status: form.status,
        }),
      });
      setEditing(false);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update");
    }
  };

  const handleAddVariant = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api(`/products/${id}/variants`, {
        method: "POST",
        body: JSON.stringify({ sku: variantForm.sku, name: variantForm.name, price: Number(variantForm.price) }),
      });
      setVariantForm({ sku: "", name: "", price: "" });
      setShowVariantForm(false);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add variant");
    }
  };

  const handleDeleteVariant = async (variantId: string) => {
    try {
      await api(`/products/variants/${variantId}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    }
  };

  if (!product) return <p className="text-gray-500">Loading...</p>;

  return (
    <div className="space-y-6">
      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">{error}</div>}

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-semibold text-gray-900">{product.name}</h2>
          <button onClick={() => setEditing(!editing)} className="text-sm text-blue-600 hover:underline">
            {editing ? "Cancel" : "Edit"}
          </button>
        </div>

        {editing ? (
          <form onSubmit={handleUpdate} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name" className="border border-gray-300 rounded-md px-3 py-2 text-sm" />
              <input value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} placeholder="Brand" className="border border-gray-300 rounded-md px-3 py-2 text-sm" />
              <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Category" className="border border-gray-300 rounded-md px-3 py-2 text-sm" />
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm">
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="archived">Archived</option>
              </select>
            </div>
            <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description" rows={3} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
            <button type="submit" className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800">Save</button>
          </form>
        ) : (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-gray-500">Brand</dt><dd className="text-gray-900">{product.brand ?? "—"}</dd>
            <dt className="text-gray-500">Category</dt><dd className="text-gray-900">{product.category ?? "—"}</dd>
            <dt className="text-gray-500">Status</dt><dd className="text-gray-900">{product.status}</dd>
            <dt className="text-gray-500">Description</dt><dd className="text-gray-900 col-span-2">{product.description ?? "—"}</dd>
          </dl>
        )}
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">Variants</h3>
          <button onClick={() => setShowVariantForm(!showVariantForm)} className="text-sm text-blue-600 hover:underline">
            {showVariantForm ? "Cancel" : "Add Variant"}
          </button>
        </div>

        {showVariantForm && (
          <form onSubmit={handleAddVariant} className="flex gap-3 mb-4">
            <input required placeholder="SKU" value={variantForm.sku} onChange={(e) => setVariantForm({ ...variantForm, sku: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm flex-1" />
            <input required placeholder="Name" value={variantForm.name} onChange={(e) => setVariantForm({ ...variantForm, name: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm flex-1" />
            <input required placeholder="Price" type="number" step="0.01" value={variantForm.price} onChange={(e) => setVariantForm({ ...variantForm, price: e.target.value })} className="border border-gray-300 rounded-md px-3 py-2 text-sm w-32" />
            <button type="submit" className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800">Add</button>
          </form>
        )}

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="pb-2 font-medium">SKU</th>
              <th className="pb-2 font-medium">Name</th>
              <th className="pb-2 font-medium">Price</th>
              <th className="pb-2 font-medium">Active</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {product.variants.map((v) => (
              <tr key={v.id}>
                <td className="py-2 font-mono text-xs">{v.sku}</td>
                <td className="py-2">{v.name}</td>
                <td className="py-2">{v.price}</td>
                <td className="py-2">{v.is_active ? "Yes" : "No"}</td>
                <td className="py-2 text-right">
                  <button onClick={() => handleDeleteVariant(v.id)} className="text-red-600 hover:underline text-xs">Delete</button>
                </td>
              </tr>
            ))}
            {product.variants.length === 0 && (
              <tr><td colSpan={5} className="py-4 text-center text-gray-500">No variants</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
