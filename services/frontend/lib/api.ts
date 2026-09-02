// API client for the CircuitMind backend gateway.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface AnalyzeResponse {
  job_id: string;
  bom_id: string;
  status: string;
  message: string;
}

export interface AgentEvent {
  agent: string;
  action: string;
  detail: Record<string, unknown>;
  ts: string;
}

export interface ReviewItem {
  line_number: number;
  reference_designator: string;
  original_mpn: string;
  original_description: string;
  quantity: number;
  alternate_mpn: string | null;
  alternate_manufacturer: string | null;
  alternate_description: string | null;
  compatibility_score: number | null;
}

export interface ReviewPayload {
  job_id: string;
  items: ReviewItem[];
}

export interface PurchaseOrderRow {
  component_mpn: string | null;
  supplier: string | null;
  quantity: number;
  unit_price: number;
  total_price: number;
  lead_time_days: number;
}

export interface ResultsResponse {
  job_id: string;
  bom_id: string;
  status: string;
  purchase_orders: PurchaseOrderRow[];
  total_cost: number;
}

// Non-negotiable substitution dimensions the user can require an alternate to
// match against the original part. Must mirror the backend ALLOWED_CONSTRAINTS.
export const CONSTRAINT_OPTIONS: { key: string; label: string; hint: string }[] = [
  { key: "package", label: "Package / footprint", hint: "Same physical footprint" },
  { key: "pin_count", label: "Pin count", hint: "Same number of pins" },
  { key: "manufacturer", label: "Manufacturer", hint: "Same manufacturer only" },
  { key: "voltage", label: "Voltage range", hint: "Must cover original's voltage window" },
];

export async function uploadBom(file: File): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/bom/analyze`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed (${res.status}): ${text}`);
  }
  return res.json();
}

export async function submitApproval(
  jobId: string,
  approvals: Record<string, boolean>
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approvals }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Approval failed (${res.status}): ${text}`);
  }
}

export interface ConstraintLineItem {
  line_number: number;
  reference_designator: string;
  mpn: string;
  quantity: number;
  description: string;
}

export interface ConstraintPayload {
  job_id: string;
  allowed_constraints: string[];
  line_items: ConstraintLineItem[];
}

export async function submitConstraints(
  jobId: string,
  constraints: Record<string, string | number>
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/constraints`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ constraints }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Constraints submit failed (${res.status}): ${text}`);
  }
}

export async function fetchResults(jobId: string): Promise<ResultsResponse> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/results`);
  if (!res.ok) throw new Error(`Results fetch failed (${res.status})`);
  return res.json();
}

export function streamUrl(jobId: string): string {
  return `${API_BASE}/api/v1/jobs/${jobId}/stream`;
}
