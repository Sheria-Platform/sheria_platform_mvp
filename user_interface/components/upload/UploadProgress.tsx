import { UploadFile } from "@/hooks/useUpload";
import { cn } from "@/lib/utils";

export function UploadProgress({ file }: { file: UploadFile }) {
  const statusColor = {
    pending: "text-gray-500",
    uploading: "text-blue-600",
    done: "text-green-600",
    error: "text-red-600",
  }[file.status];

  const statusLabel = {
    pending: "Pending",
    uploading: `Uploading ${file.progress}%`,
    done: "Done ✓",
    error: `Error: ${file.error}`,
  }[file.status];

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="truncate max-w-[60%] text-gray-700">{file.file.name}</span>
        <span className={cn("text-xs font-medium", statusColor)}>{statusLabel}</span>
      </div>
      {file.status === "uploading" && (
        <div className="w-full bg-gray-200 rounded-full h-1.5">
          <div
            className="h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${file.progress}%`, backgroundColor: "#1a3a6b" }}
          />
        </div>
      )}
    </div>
  );
}
