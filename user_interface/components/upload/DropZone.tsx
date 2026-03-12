"use client";

import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { cn } from "@/lib/utils";

const ACCEPTED = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "text/html": [".html"],
  "text/plain": [".txt"],
};

interface DropZoneProps {
  onDrop: (files: File[]) => void;
  disabled?: boolean;
}

export function DropZone({ onDrop, disabled }: DropZoneProps) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    disabled,
    maxSize: 50 * 1024 * 1024, // 50 MB
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors",
        isDragActive
          ? "border-blue-500 bg-blue-50"
          : "border-gray-300 hover:border-blue-400 hover:bg-gray-50",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      <input {...getInputProps()} />
      <div className="text-4xl mb-3">📄</div>
      <p className="text-sm font-medium text-gray-700">
        {isDragActive ? "Drop files here" : "Drag & drop court documents here"}
      </p>
      <p className="text-xs text-gray-400 mt-1">
        PDF, DOCX, HTML, TXT — up to 50 MB each
      </p>
    </div>
  );
}
