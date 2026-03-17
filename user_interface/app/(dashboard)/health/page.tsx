"use client";

import { useChatStore } from "@/store/chatStore";
import { HealthDashboard } from "@/components/health/HealthDashboard";

export default function HealthPage() {
  const user = useChatStore((s) => s.user);

  if (user?.role !== "admin") {
    return (
      <div className="p-8 text-center text-gray-500">
        Access restricted to administrators.
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-2" style={{ color: "#1a3a6b" }}>
        System Status
      </h1>
      <p className="text-gray-500 text-sm mb-6">
        Real-time health of all Sheria Platform services. Auto-refreshes every 30 seconds.
      </p>
      <HealthDashboard />
    </div>
  );
}
