"use client";

import { useHealth } from "@/hooks/useHealth";
import { ServiceCard } from "./ServiceCard";
import { StatusBadge } from "./StatusBadge";
import { Skeleton } from "@/components/ui/skeleton";

export function HealthDashboard() {
  const { health, loading, error } = useHealth();

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-red-500 text-sm">
        Failed to reach health endpoint: {error}
      </div>
    );
  }

  if (!health) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <StatusBadge status={health.status} />
        <span className="text-sm text-gray-500">
          Last updated:{" "}
          {new Date(health.timestamp).toLocaleTimeString("en-KE")}
        </span>
        <span className="text-xs text-gray-400 ml-auto">v{health.version}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(health.services).map(([name, svc]) => (
          <ServiceCard key={name} name={name} health={svc} />
        ))}
      </div>
    </div>
  );
}
