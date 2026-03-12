import { cn } from "@/lib/utils";

type Status = "healthy" | "degraded" | "unhealthy";

const STYLES: Record<Status, string> = {
  healthy: "bg-green-100 text-green-700",
  degraded: "bg-yellow-100 text-yellow-700",
  unhealthy: "bg-red-100 text-red-700",
};

const LABELS: Record<Status, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  unhealthy: "Down",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
        STYLES[status]
      )}
    >
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full",
          status === "healthy"
            ? "bg-green-500"
            : status === "degraded"
            ? "bg-yellow-500"
            : "bg-red-500"
        )}
      />
      {LABELS[status]}
    </span>
  );
}
