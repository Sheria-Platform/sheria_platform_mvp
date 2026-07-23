import { AnalyticsPayload } from "@/types/api";

// ── Colour maps ────────────────────────────────────────────────────────────

const RISK_COLORS: Record<string, string> = {
  low: "bg-green-500",
  medium: "bg-amber-500",
  high: "bg-orange-500",
  critical: "bg-red-600",
};

const ACTION_BADGE: Record<string, string> = {
  approve: "bg-green-100 text-green-700",
  suspend: "bg-red-100 text-red-700",
  reactivate: "bg-blue-100 text-blue-700",
  role_change: "bg-purple-100 text-purple-700",
};

// ── Sub-components ─────────────────────────────────────────────────────────

function StatBar({
  label,
  value,
  total,
  color = "bg-judicial-navy",
}: {
  label: string;
  value: number;
  total: number;
  color?: string;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="capitalize text-gray-700">{label}</span>
        <span className="text-gray-500 font-mono">
          {value}{" "}
          <span className="text-xs text-gray-400">({pct}%)</span>
        </span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-bold text-judicial-navy mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function SectionHeading({ title }: { title: string }) {
  return (
    <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
      {title}
    </h2>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function AnalyticsDashboard({
  data,
}: {
  data: AnalyticsPayload;
}) {
  const { overview, verifications, predictions } = data;

  // Totals for bar calculations
  const totalRoleUsers = Object.values(data.users_by_role).reduce(
    (s, n) => s + n,
    0
  );
  const totalRisk = Object.values(predictions.by_risk_level).reduce(
    (s, n) => s + n,
    0
  );
  const totalDocTypes = Object.values(verifications.by_document_type).reduce(
    (s, n) => s + n,
    0
  );
  const totalPredCourts = data.predictions.top_courts.reduce(
    (s, c) => s + c.count,
    0
  );

  return (
    <div className="space-y-10">
      {/* 1 ── Platform Overview ──────────────────────────────────────── */}
      <section>
        <SectionHeading title="Platform Overview" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Users" value={overview.total_users} />
          <StatCard
            label="Active Users"
            value={overview.active_users}
            sub={`${overview.pending_users} pending · ${overview.suspended_users} suspended`}
          />
          <StatCard
            label="Verifications"
            value={overview.total_verifications}
          />
          <StatCard
            label="Predictions"
            value={overview.total_predictions}
          />
          <StatCard
            label="Chat Sessions"
            value={overview.total_chat_sessions}
          />
          <StatCard
            label="Ingestion Jobs"
            value={overview.total_ingestion_jobs}
          />
        </div>
      </section>

      {/* 2 ── User Distribution ──────────────────────────────────────── */}
      <section>
        <SectionHeading title="User Distribution" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* By role */}
          <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              By Role
            </p>
            {Object.entries(data.users_by_role).map(([role, count]) => (
              <StatBar
                key={role}
                label={role}
                value={count}
                total={totalRoleUsers}
              />
            ))}
            {Object.keys(data.users_by_role).length === 0 && (
              <p className="text-sm text-gray-400">No data</p>
            )}
          </div>

          {/* By court station */}
          <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Top Court Stations
            </p>
            {data.top_court_stations.map(({ court_station, count }) => (
              <StatBar
                key={court_station}
                label={court_station}
                value={count}
                total={overview.total_users}
              />
            ))}
            {data.top_court_stations.length === 0 && (
              <p className="text-sm text-gray-400">No data</p>
            )}
            <p className="text-xs text-gray-400 pt-1">
              {data.recent_registrations_7d} new registration
              {data.recent_registrations_7d !== 1 ? "s" : ""} in the last 7
              days
            </p>
          </div>
        </div>
      </section>

      {/* 3 ── Verification Intelligence ──────────────────────────────── */}
      <section>
        <SectionHeading title="Verification Intelligence" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white border border-gray-200 rounded-xl p-5 flex flex-col items-center justify-center">
            <p className="text-xs text-gray-400 uppercase tracking-wide">
              Authenticity Rate
            </p>
            <p className="text-4xl font-bold text-green-600 mt-2">
              {verifications.authenticity_rate}%
            </p>
            <p className="text-xs text-gray-400 mt-1">
              {verifications.authentic_count} authentic /{" "}
              {verifications.fraudulent_count} flagged
            </p>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-5 flex flex-col items-center justify-center">
            <p className="text-xs text-gray-400 uppercase tracking-wide">
              Avg. Confidence
            </p>
            <p className="text-4xl font-bold text-judicial-navy mt-2">
              {verifications.avg_confidence.toFixed(2)}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              across {verifications.total} verifications
            </p>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              By Document Type
            </p>
            {Object.entries(verifications.by_document_type).map(
              ([type, count]) => (
                <StatBar
                  key={type}
                  label={type.replace(/_/g, " ")}
                  value={count}
                  total={totalDocTypes}
                  color="bg-amber-500"
                />
              )
            )}
            {Object.keys(verifications.by_document_type).length === 0 && (
              <p className="text-sm text-gray-400">No data</p>
            )}
          </div>
        </div>
      </section>

      {/* 4 ── Judicial Workload ──────────────────────────────────────── */}
      <section>
        <SectionHeading title="Judicial Workload" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Risk levels */}
          <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Risk Level Distribution
            </p>
            {(["low", "medium", "high", "critical"] as const).map((level) => {
              const count = predictions.by_risk_level[level] ?? 0;
              return (
                <StatBar
                  key={level}
                  label={level}
                  value={count}
                  total={totalRisk}
                  color={RISK_COLORS[level]}
                />
              );
            })}
            <p className="text-xs text-gray-400 pt-1">
              Avg. estimated duration:{" "}
              <span className="font-semibold text-gray-600">
                {predictions.avg_estimated_months} months
              </span>
            </p>
          </div>

          {/* Top courts */}
          <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Top Courts by Predictions
            </p>
            {predictions.top_courts.map(({ court, count }) => (
              <StatBar
                key={court}
                label={court}
                value={count}
                total={totalPredCourts}
                color="bg-purple-500"
              />
            ))}
            {predictions.top_courts.length === 0 && (
              <p className="text-sm text-gray-400">No data</p>
            )}
          </div>
        </div>
      </section>

      {/* 5 ── Admin Audit Log ────────────────────────────────────────── */}
      <section>
        <SectionHeading title="Admin Audit Log" />
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          {data.audit_log.length === 0 ? (
            <p className="text-center py-10 text-gray-400 text-sm">
              No audit log entries
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wide font-medium">
                    Action
                  </th>
                  <th className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wide font-medium">
                    Admin
                  </th>
                  <th className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wide font-medium">
                    Detail
                  </th>
                  <th className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wide font-medium">
                    IP
                  </th>
                  <th className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wide font-medium">
                    Timestamp
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.audit_log.map((entry) => (
                  <tr key={entry.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full capitalize font-medium ${
                          ACTION_BADGE[entry.action] ??
                          "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {entry.action.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700 font-mono text-xs">
                      {entry.admin}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs max-w-xs truncate">
                      {entry.detail
                        ? Object.entries(entry.detail)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(" · ")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                      {entry.ip_address ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
                      {new Date(entry.created_at).toLocaleString("en-KE", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────

export function AnalyticsDashboardSkeleton() {
  return (
    <div className="space-y-10 animate-pulse">
      <section>
        <div className="h-4 w-40 bg-gray-200 rounded mb-4" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="bg-gray-100 rounded-xl p-5 h-24"
            />
          ))}
        </div>
      </section>
      <section>
        <div className="h-4 w-40 bg-gray-200 rounded mb-4" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-gray-100 rounded-xl h-48" />
          <div className="bg-gray-100 rounded-xl h-48" />
        </div>
      </section>
      <section>
        <div className="h-4 w-40 bg-gray-200 rounded mb-4" />
        <div className="bg-gray-100 rounded-xl h-32" />
      </section>
    </div>
  );
}
