import { ServiceHealth } from "@/types/api";
import { StatusBadge } from "./StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const SERVICE_ICONS: Record<string, string> = {
  postgres: "🐘",
  redis: "⚡",
  qdrant: "🔍",
  neo4j: "🕸️",
  ollama: "🤖",
  minio: "🪣",
};

interface ServiceCardProps {
  name: string;
  health: ServiceHealth;
}

export function ServiceCard({ name, health }: ServiceCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center justify-between">
          <span className="flex items-center gap-2">
            <span>{SERVICE_ICONS[name.toLowerCase()] ?? "⚙️"}</span>
            <span className="capitalize">{name}</span>
          </span>
          <StatusBadge status={health.status} />
        </CardTitle>
      </CardHeader>
      <CardContent>
        {health.latency_ms !== undefined && (
          <p className="text-xs text-gray-500">
            Latency: <span className="font-medium text-gray-700">{health.latency_ms}ms</span>
          </p>
        )}
        {health.message && (
          <p className="text-xs text-gray-400 mt-1">{health.message}</p>
        )}
      </CardContent>
    </Card>
  );
}
