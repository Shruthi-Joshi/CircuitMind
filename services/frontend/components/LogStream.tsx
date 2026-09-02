"use client";

import { useEffect, useRef } from "react";
import type { AgentEvent } from "@/lib/api";

interface Props {
  events: AgentEvent[];
  connected: boolean;
}

const AGENT_COLOR: Record<string, string> = {
  "BOM Parser": "text-circuit-accent",
  "Constraints Gate": "text-cyan-400",
  "Market Check": "text-blue-400",
  "Alternate Match": "text-purple-400",
  "Human Approval Gate": "text-circuit-amber",
  "PO Generator": "text-circuit-green",
};

const ACTION_ICON: Record<string, string> = {
  start: "▶",
  complete: "✓",
  error: "✕",
  in_stock: "✓",
  out_of_stock: "⚠",
  alternate_found: "◆",
  no_alternate: "✕",
  awaiting_approval: "⏸",
  approval_received: "▶",
  po_created: "🛒",
  searching: "⌕",
  awaiting_constraints: "⌨",
  constraints_received: "▶",
  constraints_relaxed: "↔",
  class_mismatch_rejected: "⊘",
};

function formatDetail(detail: Record<string, unknown>): string {
  const entries = Object.entries(detail);
  if (entries.length === 0) return "";
  return entries.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join("  ");
}

export default function LogStream({ events, connected }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex h-full flex-col rounded-lg border border-circuit-border bg-circuit-panel">
      <div className="flex items-center justify-between border-b border-circuit-border px-4 py-2">
        <span className="text-sm font-semibold text-gray-200">
          Agent Execution Log
        </span>
        <span className="flex items-center gap-2 text-xs">
          <span
            className={[
              "inline-block h-2 w-2 rounded-full",
              connected ? "bg-circuit-green pulse-dot" : "bg-gray-500",
            ].join(" ")}
          />
          {connected ? "streaming" : "idle"}
        </span>
      </div>
      <div className="log-scroll flex-1 overflow-y-auto p-4 text-xs leading-relaxed">
        {events.length === 0 ? (
          <p className="text-gray-500">Waiting for agent activity…</p>
        ) : (
          events.map((evt, i) => (
            <div key={i} className="mb-1 flex gap-2">
              <span className="shrink-0 text-gray-600">
                {new Date(evt.ts).toLocaleTimeString()}
              </span>
              <span className="shrink-0 w-4 text-center">
                {ACTION_ICON[evt.action] ?? "•"}
              </span>
              <span
                className={[
                  "shrink-0 font-semibold",
                  AGENT_COLOR[evt.agent] ?? "text-gray-300",
                ].join(" ")}
              >
                [{evt.agent}]
              </span>
              <span className="text-gray-400">
                {evt.action}
                {Object.keys(evt.detail || {}).length > 0 && (
                  <span className="ml-2 text-gray-500">
                    {formatDetail(evt.detail)}
                  </span>
                )}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
