import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";

interface OrderItem {
  id: string;
  sku: string;
  product_name: string;
  variant_name: string;
  quantity: number;
  unit_price: string;
  total_price: string;
}

interface Order {
  id: string;
  order_number: string;
  status: string;
  subtotal: string;
  tax_amount: string;
  shipping_amount: string;
  total_amount: string;
  currency: string;
  customer_name: string | null;
  customer_email: string | null;
  ordered_at: string;
  shipped_at: string | null;
  items: OrderItem[];
}

const transitions: Record<string, string[]> = {
  pending: ["confirmed", "cancelled"],
  confirmed: ["processing", "cancelled"],
  processing: ["shipped"],
  shipped: ["delivered", "returned"],
};

export default function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const api = useApi();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");

  const load = () => api<Order>(`/orders/${id}`).then(setOrder).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [api, id]);

  const transition = async (status: string) => {
    setError("");
    try {
      await api(`/orders/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  };

  if (!order) return <p className="text-gray-500">Loading...</p>;

  const allowed = transitions[order.status] ?? [];

  return (
    <div className="space-y-6">
      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">{error}</div>}

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-semibold text-gray-900">{order.order_number}</h2>
          <span className="text-sm font-medium px-3 py-1 rounded-full bg-gray-100 text-gray-700">{order.status}</span>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm mb-6">
          <dt className="text-gray-500">Customer</dt><dd className="text-gray-900">{order.customer_name ?? "—"}</dd>
          <dt className="text-gray-500">Email</dt><dd className="text-gray-900">{order.customer_email ?? "—"}</dd>
          <dt className="text-gray-500">Ordered</dt><dd className="text-gray-900">{new Date(order.ordered_at).toLocaleString()}</dd>
          <dt className="text-gray-500">Shipped</dt><dd className="text-gray-900">{order.shipped_at ? new Date(order.shipped_at).toLocaleString() : "—"}</dd>
          <dt className="text-gray-500">Subtotal</dt><dd className="text-gray-900">{order.currency} {order.subtotal}</dd>
          <dt className="text-gray-500">Tax</dt><dd className="text-gray-900">{order.currency} {order.tax_amount}</dd>
          <dt className="text-gray-500">Shipping</dt><dd className="text-gray-900">{order.currency} {order.shipping_amount}</dd>
          <dt className="text-gray-500 font-medium">Total</dt><dd className="text-gray-900 font-medium">{order.currency} {order.total_amount}</dd>
        </dl>

        {allowed.length > 0 && (
          <div className="flex gap-2">
            {allowed.map((s) => (
              <button
                key={s}
                onClick={() => transition(s)}
                className={`px-3 py-1.5 text-sm font-medium rounded-md ${
                  s === "cancelled" ? "bg-red-100 text-red-700 hover:bg-red-200" : "bg-gray-900 text-white hover:bg-gray-800"
                }`}
              >
                Mark {s}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-3">Line Items</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="pb-2 font-medium">SKU</th>
              <th className="pb-2 font-medium">Product</th>
              <th className="pb-2 font-medium">Variant</th>
              <th className="pb-2 font-medium">Qty</th>
              <th className="pb-2 font-medium">Unit Price</th>
              <th className="pb-2 font-medium">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {order.items.map((i) => (
              <tr key={i.id}>
                <td className="py-2 font-mono text-xs">{i.sku}</td>
                <td className="py-2">{i.product_name}</td>
                <td className="py-2">{i.variant_name}</td>
                <td className="py-2">{i.quantity}</td>
                <td className="py-2">{i.unit_price}</td>
                <td className="py-2">{i.total_price}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
