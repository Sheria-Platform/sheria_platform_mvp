"use client";

import { useState, useEffect, useCallback } from "react";
import { useChatStore } from "@/store/chatStore";
import { apiFetch } from "@/lib/api";
import { AnalyticsPayload } from "@/types/api";
import { Button } from "@/components/ui/button";
import AnalyticsDashboard, {
  AnalyticsDashboardSkeleton,
} from "@/components/admin/AnalyticsDashboard";

export default function AnalyticsPage() {
  const user = useChatStore((s) => s.user);
  const [data, setData] = useState<AnalyticsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await apiFetch<AnalyticsPayload>(
        "/api/proxy/admin/analytics"
      );
      setData(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.role === "admin") fetchAnalytics();
  }, [user?.role, fetchAnalytics]);

  if (user?.role !== "admin") {
    return (
      <div className="p-8 text-center text-gray-500">
        Access restricted to administrators.
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-gray-500 mt-1 text-sm">
            Platform-wide usage metrics and judicial workload insights
          </p>
        </div>
        <Button variant="outline" onClick={fetchAnalytics} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {loading ? (
        <AnalyticsDashboardSkeleton />
      ) : error ? (
        <div className="text-center py-12 text-red-500">
          <p className="font-medium">Failed to load analytics</p>
          <p className="text-sm mt-1">{error}</p>
          <Button variant="outline" onClick={fetchAnalytics} className="mt-4">
            Retry
          </Button>
        </div>
      ) : data ? (
        <AnalyticsDashboard data={data} />
      ) : null}
    </div>
  );
}
