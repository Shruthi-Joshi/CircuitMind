"use client";

import { useCallback, useRef, useState } from "react";

interface Props {
  onUpload: (file: File) => void;
  disabled?: boolean;
}

const ACCEPT = ".pdf,.xlsx,.xls,.csv,.tsv,.txt";

export default function FileUpload({ onUpload, disabled }: Props) {
  const [dragging, setDragging] = useState(false);
  const [filename, setFilename] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      setFilename(file.name);
      onUpload(file);
    },
    [onUpload]
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      handleFile(e.dataTransfer.files?.[0]);
    },
    [disabled, handleFile]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      aria-label="Upload BOM file"
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && !disabled) {
          inputRef.current?.click();
        }
      }}
      className={[
        "cursor-pointer rounded-lg border-2 border-dashed p-10 text-center transition",
        dragging
          ? "border-circuit-accent bg-circuit-accent/10"
          : "border-circuit-border bg-circuit-panel",
        disabled ? "cursor-not-allowed opacity-50" : "hover:border-circuit-accent",
      ].join(" ")}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        disabled={disabled}
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      <div className="text-4xl">📄</div>
      <p className="mt-3 text-sm text-gray-300">
        {filename ? (
          <span className="text-circuit-accent">{filename}</span>
        ) : (
          <>
            Drag &amp; drop a BOM file here, or{" "}
            <span className="text-circuit-accent underline">browse</span>
          </>
        )}
      </p>
      <p className="mt-1 text-xs text-gray-500">
        Supports PDF, XLSX, CSV, TSV, TXT
      </p>
    </div>
  );
}
