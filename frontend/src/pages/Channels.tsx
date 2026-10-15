import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

interface Channel {
  id: string;
  platform: string;
  name: string;
  external_account_id: string | null;
  status: string;
  status_message: string | null;
  last_sync_at: string | null;
  is_active: boolean;
  created_at: string;
}

export default function Channels() {
  const api = useApi();
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ platform: "amazon", name: "", external_account_id: "" });
  const [saving, setSaving] = useState(false);

  const load = () => api<Channel[]>("/channels").then(setChannels).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [api]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api("/channels", {
        method: "POST",
        body: JSON.stringify({
          platform: form.platform,
          name: form.name,
          external_account_id: form.external_account_id || undefined,
        }),
      });
      setForm({ platform: "amazon", name: "", external_account_id: "" });
      setShowForm(false);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create");
    } finally {
      setSaving(false);
    }
  };

  const statusColor: Record<string, string> = {
    connected: "bg-green-100 text-green-700",
    pending: "bg-yellow-100 text-yellow-700",
    disconnected: "bg-gray-100 text-gray-600",
    error: "bg-red-100 text-red-700",
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-gray-900">Channels</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800"
        >
          {showForm ? "Cancel" : "Connect Channel"}
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">{error}</div>}

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white border border-gray-200 rounded-lg p-6 mb-6 space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Platform</label>
              <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm">
                <option value="amazon">Amazon</option>
                <option value="google_merchant">Google Merchant</option>
                <option value="shopify">Shopify</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Display Name</label>
              <input required placeholder="e.g. Amazon India" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Seller/Merchant ID</label>
              <input placeholder="Optional" value={form.external_account_id} onChange={(e) => setForm({ ...form, external_account_id: e.target.value })} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
            </div>
          </div>
          <button disabled={saving} type="submit" className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800 disabled:opacity-50">
            {saving ? "Connecting..." : "Connect"}
          </button>
        </form>
      )}

      <div className="bg-white rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Platform</th>
              <th className="px-4 py-3 font-medium">Seller ID</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Last Sync</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {channels.map((c) => (
              <tr key={c.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-gray-900 font-medium">{c.name}</td>
                <td className="px-4 py-3 text-gray-600">{c.platform}</td>
                <td className="px-4 py-3 text-gray-600 font-mono text-xs">{c.external_account_id ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-medium px-2 py-1 rounded-full ${statusColor[c.status] ?? "bg-gray-100 text-gray-600"}`}>
                    {c.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">
                  {c.last_sync_at ? new Date(c.last_sync_at).toLocaleString() : "Never"}
                </td>
              </tr>
            ))}
            {channels.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">No channels connected</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
