import { UploadFile } from "@/hooks/useUpload";
import { UploadProgress } from "./UploadProgress";
import { Button } from "@/components/ui/button";

interface FileListProps {
  files: UploadFile[];
  onRemove: (id: string) => void;
}

export function FileList({ files, onRemove }: FileListProps) {
  if (files.length === 0) return null;

  return (
    <div className="space-y-3">
      {files.map((f) => (
        <div key={f.id} className="flex items-start gap-2">
          <div className="flex-1">
            <UploadProgress file={f} />
          </div>
          {f.status !== "uploading" && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 text-gray-400 hover:text-red-500 shrink-0"
              onClick={() => onRemove(f.id)}
            >
              ×
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}
