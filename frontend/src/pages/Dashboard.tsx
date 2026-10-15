import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

interface Member {
  id: string;
  clerk_user_id: string;
  role: string;
  joined_at: string;
}

export default function Dashboard() {
  const api = useApi();
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Member[]>("/tenants/members").then(setMembers).catch((e) => setError(e.message));
  }, [api]);

  return (
    <div>
      <h2 className="text-2xl font-semibold text-gray-900 mb-6">Dashboard</h2>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">{error}</div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-3">Team Members</h3>
        {members.length === 0 && !error ? (
          <p className="text-gray-500">No team yet — create an organization first.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {members.map((m) => (
              <li key={m.id} className="py-3 flex items-center justify-between">
                <span className="text-sm text-gray-900">{m.clerk_user_id}</span>
                <span className="text-xs font-medium px-2 py-1 rounded-full bg-gray-100 text-gray-600">
                  {m.role}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
