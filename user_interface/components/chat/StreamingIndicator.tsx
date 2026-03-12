import { PipelineStepStatus } from "@/types/chat";
import { cn } from "@/lib/utils";

const STEP_LABELS: Record<string, string> = {
  planner: "Planning query",
  retriever: "Searching case law",
  responder: "Generating response",
};

interface StreamingIndicatorProps {
  steps?: PipelineStepStatus[];
}

export function StreamingIndicator({ steps }: StreamingIndicatorProps) {
  if (!steps) return null;

  return (
    <div className="flex items-center gap-4 py-2 px-1 text-xs text-gray-500">
      {steps.map((s, i) => (
        <div key={s.step} className="flex items-center gap-1.5">
          <span
            className={cn(
              "w-2 h-2 rounded-full",
              s.status === "complete"
                ? "bg-green-500"
                : s.status === "active"
                ? "animate-pulse"
                : "bg-gray-300"
            )}
            style={s.status === "active" ? { backgroundColor: "#2a579e" } : undefined}
          />
          <span
            style={s.status === "active" ? { color: "#1a3a6b", fontWeight: 500 } : undefined}
          >
            {STEP_LABELS[s.step]}
          </span>
          {i < steps.length - 1 && <span className="text-gray-300">→</span>}
        </div>
      ))}
    </div>
  );
}
