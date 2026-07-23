import { Button } from "@/components/ui/button";

export function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs text-gray-400 uppercase tracking-wide">{label}</span>
      <p className="text-sm text-gray-800 mt-0.5">{value}</p>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    active:    "bg-green-100 text-green-700",
    approved:  "bg-blue-100 text-blue-700",
    pending:   "bg-amber-100 text-amber-800",
    suspended: "bg-red-100 text-red-700",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${map[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}

export function EmptyState({ message, sub }: { message: string; sub: string }) {
  return (
    <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
      <p className="text-gray-400 font-medium">{message}</p>
      <p className="text-gray-300 text-sm mt-1">{sub}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="text-center py-12 text-destructive">
      <p className="font-medium">Failed to load</p>
      <p className="text-sm mt-1">{message}</p>
      <Button variant="outline" className="mt-4" onClick={onRetry}>Retry</Button>
    </div>
  );
}

export function formatDate(iso: string | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-KE", {
    day: "numeric", month: "short", year: "numeric",
  });
}
