"use client";

import { DropZone } from "@/components/upload/DropZone";
import { FileList } from "@/components/upload/FileList";
import { IngestionJobsPanel } from "@/components/upload/IngestionJobsPanel";
import { Button } from "@/components/ui/button";
import { useUpload } from "@/hooks/useUpload";

export default function UploadPage() {
  const { files, addFiles, uploadAll, removeFile } = useUpload();
  const hasFiles = files.length > 0;
  const allDone = hasFiles && files.every((f) => f.status === "done");
  const isUploading = files.some((f) => f.status === "uploading");

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-5">
      <div>
        <h1 className="text-2xl font-bold mb-1" style={{ color: "#1a3a6b" }}>
          Upload Court Documents
        </h1>
        <p className="text-gray-500 text-sm">
          Upload judgments, pleadings, and exhibits. They will be indexed into the
          Sheria knowledge base for AI-powered retrieval.
        </p>
      </div>

      <DropZone onDrop={addFiles} disabled={isUploading} />

      {hasFiles && (
        <div className="bg-white border rounded-xl p-4 space-y-4">
          <FileList files={files} onRemove={removeFile} />

          {!allDone && (
            <Button
              onClick={uploadAll}
              disabled={isUploading}
              className="w-full"
              style={{ backgroundColor: "#1a3a6b" }}
            >
              {isUploading ? "Uploading…" : "Upload All"}
            </Button>
          )}

          {allDone && (
            <p className="text-sm text-green-600 text-center font-medium">
              All files uploaded — ingestion running below ↓
            </p>
          )}
        </div>
      )}

      <IngestionJobsPanel files={files} />
    </div>
  );
}
