"use client";

import { useMemo, useState } from "react";
import type { ReviewPayload } from "@/lib/api";

interface Props {
  payload: ReviewPayload;
  onSubmit: (approvals: Record<string, boolean>) => void;
  submitting?: boolean;
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-gray-400";
  if (score >= 0.97) return "text-circuit-green";
  if (score >= 0.95) return "text-circuit-amber";
  return "text-circuit-red";
}

export default function ApprovalModal({ payload, onSubmit, submitting }: Props) {
  // Default: approve every proposed alternate.
  const initial = useMemo(() => {
    const map: Record<string, boolean> = {};
    payload.items.forEach((it) => {
      map[it.original_mpn] = true;
    });
    return map;
  }, [payload]);

  const [approvals, setApprovals] = useState<Record<string, boolean>>(initial);

  const toggle = (mpn: string, value: boolean) =>
    setApprovals((prev) => ({ ...prev, [mpn]: value }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-lg border border-circuit-border bg-circuit-bg shadow-2xl">
        <div className="border-b border-circuit-border px-6 py-4">
          <h2 className="text-lg font-semibold text-circuit-amber">
            ⏸ Human Approval Required
          </h2>
          <p className="mt-1 text-sm text-gray-400">
            {payload.items.length} out-of-stock component
            {payload.items.length === 1 ? "" : "s"} matched to drop-in
            replacements. Review and approve substitutions before purchase
            orders are generated.
          </p>
        </div>

        <div className="space-y-4 p-6">
          {payload.items.map((item) => (
            <div
              key={item.original_mpn}
              className="rounded-lg border border-circuit-border bg-circuit-panel p-4"
            >
              <div className="mb-3 flex items-center justify-between">
                <span className="text-xs text-gray-500">
                  Line {item.line_number}
                  {item.reference_designator
                    ? ` · ${item.reference_designator}`
                    : ""}{" "}
                  · qty {item.quantity}
                </span>
                <span
                  className={`text-sm font-semibold ${scoreColor(
                    item.compatibility_score
                  )}`}
                >
                  {item.compatibility_score !== null
                    ? `${(item.compatibility_score * 100).toFixed(1)}% match`
                    : "—"}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {/* Original (out of stock) */}
                <div className="rounded border border-circuit-red/40 bg-circuit-red/5 p-3">
                  <div className="mb-1 text-xs uppercase text-circuit-red">
                    ⚠ Out of Stock
                  </div>
                  <div className="font-semibold text-gray-100">
                    {item.original_mpn}
                  </div>
                  <div className="mt-1 text-xs text-gray-400">
                    {item.original_description || "—"}
                  </div>
                </div>

                {/* Proposed alternate */}
                <div className="rounded border border-circuit-green/40 bg-circuit-green/5 p-3">
                  <div className="mb-1 text-xs uppercase text-circuit-green">
                    ◆ Proposed Alternate
                  </div>
                  <div className="font-semibold text-gray-100">
                    {item.alternate_mpn}
                  </div>
                  <div className="text-xs text-gray-500">
                    {item.alternate_manufacturer}
                  </div>
                  <div className="mt-1 text-xs text-gray-400">
                    {item.alternate_description || "—"}
                  </div>
                </div>
              </div>

              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => toggle(item.original_mpn, true)}
                  className={[
                    "rounded px-3 py-1 text-xs font-semibold transition",
                    approvals[item.original_mpn]
                      ? "bg-circuit-green text-black"
                      : "bg-circuit-border text-gray-300 hover:bg-circuit-green/30",
                  ].join(" ")}
                >
                  ✓ Approve
                </button>
                <button
                  onClick={() => toggle(item.original_mpn, false)}
                  className={[
                    "rounded px-3 py-1 text-xs font-semibold transition",
                    !approvals[item.original_mpn]
                      ? "bg-circuit-red text-black"
                      : "bg-circuit-border text-gray-300 hover:bg-circuit-red/30",
                  ].join(" ")}
                >
                  ✕ Reject
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-3 border-t border-circuit-border px-6 py-4">
          <button
            disabled={submitting}
            onClick={() => onSubmit(approvals)}
            className="rounded bg-circuit-accent px-5 py-2 text-sm font-semibold text-black transition hover:bg-cyan-300 disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Confirm & Generate Purchase Orders"}
          </button>
        </div>
      </div>
    </div>
  );
}
