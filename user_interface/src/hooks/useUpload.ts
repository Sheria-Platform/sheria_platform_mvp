"use client";

import { useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { UploadPresignRequest, UploadPresignResponse } from "@/types/api";

export interface UploadFile {
  id: string;
  file: File;
  status: "pending" | "uploading" | "done" | "error";
  progress: number;
  error?: string;
  fileId?: string;
}

export function useUpload() {
  const [files, setFiles] = useState<UploadFile[]>([]);

  const updateFile = useCallback(
    (id: string, update: Partial<UploadFile>) =>
      setFiles((prev) =>
        prev.map((f) => (f.id === id ? { ...f, ...update } : f))
      ),
    []
  );

  const addFiles = useCallback((accepted: File[]) => {
    const newFiles: UploadFile[] = accepted.map((file) => ({
      id: Math.random().toString(36).substring(2),
      file,
      status: "pending",
      progress: 0,
    }));
    setFiles((prev) => [...prev, ...newFiles]);
  }, []);

  const uploadFile = useCallback(
    async (uploadFile: UploadFile) => {
      updateFile(uploadFile.id, { status: "uploading", progress: 10 });
      try {
        const presign = await apiFetch<UploadPresignResponse>(
          "/api/v1/upload/generate-presigned-url",
          {
            method: "POST",
            body: JSON.stringify({
              filename: uploadFile.file.name,
              content_type: uploadFile.file.type || "application/octet-stream",
            } satisfies UploadPresignRequest),
          }
        );

        updateFile(uploadFile.id, { progress: 40 });

        await fetch(presign.upload_url, {
          method: "PUT",
          body: uploadFile.file,
          headers: { "Content-Type": uploadFile.file.type || "application/octet-stream" },
        });

        updateFile(uploadFile.id, {
          status: "done",
          progress: 100,
          fileId: presign.file_id,
        });
      } catch (err) {
        updateFile(uploadFile.id, {
          status: "error",
          error: (err as Error).message,
        });
      }
    },
    [updateFile]
  );

  const uploadAll = useCallback(async () => {
    const pending = files.filter((f) => f.status === "pending");
    await Promise.all(pending.map(uploadFile));
  }, [files, uploadFile]);

  const removeFile = useCallback((id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  return { files, addFiles, uploadAll, uploadFile, removeFile };
}
