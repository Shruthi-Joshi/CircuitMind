"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import FileUpload from "@/components/FileUpload";
import LogStream from "@/components/LogStream";
import ApprovalModal from "@/components/ApprovalModal";
import ResultsPanel from "@/components/ResultsPanel";
import SelectConstraintsModal from "@/components/SelectConstraintsModal";
import {
  AgentEvent,
  ConstraintPayload,
  ResultsResponse,
  ReviewPayload,
  fetchResults,
  streamUrl,
  submitApproval,
  submitConstraints,
  uploadBom,
} from "@/lib/api";

type Phase =
  | "idle"
  | "uploading"
  | "processing"
  | "awaiting_constraints"
  | "awaiting_approval"
  | "completed"
  | "failed";

export default function Home() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [review, setReview] = useState<ReviewPayload | null>(null);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [constraintPayload, setConstraintPayload] =
    useState<ConstraintPayload | null>(null);
  const [constraintsModalOpen, setConstraintsModalOpen] = useState(false);

  const esRef = useRef<EventSource | null>(null);

  const openStream = useCallback((id: string) => {
    esRef.current?.close();
    const es = new EventSource(streamUrl(id));
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.addEventListener("agent", (e) => {
      try {
        const evt = JSON.parse((e as MessageEvent).data) as AgentEvent;
        setEvents((prev) => [...prev, evt]);
      } catch {
        /* ignore malformed */
      }
    });

    es.addEventListener("constraints_required", (e) => {
      try {
        const payload = JSON.parse(
          (e as MessageEvent).data
        ) as ConstraintPayload;
        if (payload && payload.job_id) {
          setConstraintPayload(payload);
          setConstraintsModalOpen(true);
          setPhase("awaiting_constraints");
        }
      } catch {
        /* ignore */
      }
    });

    es.addEventListener("approval_required", (e) => {
      try {
        const payload = JSON.parse((e as MessageEvent).data) as ReviewPayload;
        if (payload && payload.items && payload.items.length > 0) {
          setReview(payload);
          setPhase("awaiting_approval");
        }
      } catch {
        /* ignore */
      }
    });

    es.addEventListener("done", async (e) => {
      setConnected(false);
      es.close();
      try {
        const data = JSON.parse((e as MessageEvent).data) as {
          status: string;
        };
        if (data.status === "failed") {
          setPhase("failed");
          return;
        }
      } catch {
        /* ignore */
      }
      const res = await fetchResults(id);
      setResults(res);
      setPhase("completed");
    });
  }, []);

  useEffect(() => () => esRef.current?.close(), []);

  const handleUpload = useCallback(
    async (file: File) => {
      setError(null);
      setEvents([]);
      setResults(null);
      setReview(null);
      setConstraintPayload(null);
      setConstraintsModalOpen(false);
      setPhase("uploading");
      try {
        const res = await uploadBom(file);
        setJobId(res.job_id);
        setPhase("processing");
        openStream(res.job_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setPhase("failed");
      }
    },
    [openStream]
  );

  const handleConstraints = useCallback(
    async (constraints: Record<string, string | number>) => {
      if (!jobId) return;
      setSubmitting(true);
      try {
        await submitConstraints(jobId, constraints);
        setConstraintsModalOpen(false);
        setConstraintPayload(null);
        setPhase("processing");
        // Resume streaming to catch matching + approval / done events.
        if (!esRef.current || esRef.current.readyState === EventSource.CLOSED) {
          openStream(jobId);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setSubmitting(false);
      }
    },
    [jobId, openStream]
  );

  const handleApproval = useCallback(
    async (approvals: Record<string, boolean>) => {
      if (!jobId) return;
      setSubmitting(true);
      try {
        await submitApproval(jobId, approvals);
        setReview(null);
        setPhase("processing");
        // Stream continues emitting PO Generator events; if the SSE was closed,
        // reopen to catch the final "done" event.
        if (!esRef.current || esRef.current.readyState === EventSource.CLOSED) {
          openStream(jobId);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setSubmitting(false);
      }
    },
    [jobId, openStream]
  );

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-circuit-accent">
          CircuitMind AI
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Autonomous agentic procurement · upload a BOM, watch the agents work,
          approve substitutions, get optimized split purchase orders.
        </p>
      </header>

      <section className="mb-6">
        <FileUpload
          onUpload={handleUpload}
          disabled={phase === "uploading" || phase === "processing"}
        />
        {error && (
          <div className="mt-3 rounded border border-circuit-red/40 bg-circuit-red/10 px-4 py-2 text-sm text-circuit-red">
            {error}
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="h-[28rem]">
          <LogStream events={events} connected={connected} />
        </div>
        <div>
          {results ? (
            <ResultsPanel results={results} />
          ) : (
            <div className="flex h-[28rem] items-center justify-center rounded-lg border border-circuit-border bg-circuit-panel text-sm text-gray-500">
              {phase === "idle"
                ? "Purchase orders will appear here after processing."
                : phase === "awaiting_constraints"
                ? "Define your constraints to continue…"
                : phase === "awaiting_approval"
                ? "Awaiting your approval…"
                : "Processing…"}
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 flex items-center gap-2 text-xs text-gray-500">
        <span>Status:</span>
        <span
          className={[
            "rounded px-2 py-0.5 font-semibold",
            phase === "completed"
              ? "bg-circuit-green/20 text-circuit-green"
              : phase === "failed"
              ? "bg-circuit-red/20 text-circuit-red"
              : phase === "awaiting_approval"
              ? "bg-circuit-amber/20 text-circuit-amber"
              : phase === "awaiting_constraints"
              ? "bg-circuit-accent/20 text-circuit-accent"
              : "bg-circuit-border text-gray-300",
          ].join(" ")}
        >
          {phase}
        </span>
        {jobId && <span className="text-gray-600">job {jobId.slice(0, 8)}</span>}
      </div>

      {review && phase === "awaiting_approval" && (
        <ApprovalModal
          payload={review}
          onSubmit={handleApproval}
          submitting={submitting}
        />
      )}

      <SelectConstraintsModal
        isOpen={constraintsModalOpen && phase === "awaiting_constraints"}
        onClose={() => setConstraintsModalOpen(false)}
        onSubmitConstraints={handleConstraints}
      />
    </main>
  );
}
