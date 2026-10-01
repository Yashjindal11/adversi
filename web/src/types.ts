// Mirrors the Python result schema (adversi.protocol). Only fields the UI uses are typed.

export type ClaimStatus =
  | "supported"
  | "partially_supported"
  | "unsupported"
  | "contradicted"
  | "uncertain"
  | "unverified";

export interface Attribution {
  agent: string;
  role: string;
  step: string;
  confidence: number | null;
}

export interface Claim {
  id: string;
  statement: string;
  claim_type: string;
  basis: string;
  attributions: Attribution[];
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  assumption_ids: string[];
  merged_from: string[];
  status: ClaimStatus;
  proposed_status: ClaimStatus | null;
  status_rationale: string | null;
  policy_note: string | null;
  confidence: number | null;
}

export interface Provenance {
  source_type: string;
  uri: string | null;
  title: string | null;
  tool_name: string | null;
  retrieved_at: string | null;
  produced_by: string;
}

export interface Evidence {
  id: string;
  source_id: string | null;
  excerpt: string;
  provenance: Provenance;
  supports: string[];
  contradicts: string[];
  cited_by: string;
  excerpt_verified: boolean;
  reliability: number | null;
  reliability_rationale: string | null;
}

export interface Source {
  id: string;
  provenance: Provenance;
  truncated: boolean;
}

export interface Assumption {
  id: string;
  statement: string;
  critical: boolean;
  claim_ids: string[];
}

export interface Perspective {
  agent: string;
  role: string;
  model: string;
  step: string;
  round: number;
  verdict: string | null;
  position: string;
  summary: string;
  claim_ids: string[];
  counterarguments: string[];
  uncertainties: string[];
  open_questions: string[];
  confidence: number | null;
}

export interface DebateTurn {
  round: number;
  agent: string;
  role: string;
  stance: string;
  argument: string;
  claim_ids: string[];
  concedes: boolean;
}

export interface Rebuttal {
  agent: string;
  response: string;
  concedes: boolean;
}

export interface Challenge {
  id: string;
  target_claim_id: string;
  challenger: string;
  kind: string;
  argument: string;
  rebuttals: Rebuttal[];
  outcome: string;
}

export interface CritiqueFinding {
  id: string;
  critic: string;
  kind: string;
  severity: "low" | "medium" | "high";
  description: string;
  target_ids: string[];
}

export interface Synthesis {
  answer: string;
  summary: string;
  established_claim_ids: string[];
  disputed_claim_ids: string[];
  uncertain_claim_ids: string[];
  rejected_claim_ids: string[];
  caveats: string[];
  recommendations: string[];
}

export interface Uncertainty {
  answer_confidence: number | null;
  verdict_entropy: number | null;
  confidence_spread: number | null;
  contested_claim_ratio: number | null;
  unresolved_claim_ratio: number | null;
  external_evidence_coverage: number | null;
  citation_rejection_rate: number | null;
  notes: string[];
}

export interface UsageSummary {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  latency_s: number;
}

export interface RunMetadata {
  run_id: string;
  adversi_version: string;
  schema_version: string;
  workflow: string;
  mode: string | null;
  profile: string | null;
  started_at: string;
  duration_s: number | null;
  status: string;
  steps: { name: string; kind: string; duration_s: number | null; ok: boolean }[];
  agents: Record<string, string>;
  tools: string[];
  usage: UsageSummary;
  usage_by_model: Record<string, UsageSummary>;
  errors: { step: string | null; agent: string | null; type: string; message: string }[];
}

export interface AdverSIResult {
  schema_version: string;
  question: string;
  perspectives: Perspective[];
  claims: Claim[];
  assumptions: Assumption[];
  sources: Source[];
  evidence: Evidence[];
  rejected_citations: { agent: string; source_id: string | null; reason: string }[];
  debate: DebateTurn[];
  challenges: Challenge[];
  critique: CritiqueFinding[];
  judgment: { overall_assessment: string; answer_confidence: number | null } | null;
  synthesis: Synthesis | null;
  uncertainty: Uncertainty;
  unresolved_questions: string[];
  metadata: RunMetadata;
}

export interface RunEvent {
  seq: number;
  type: string;
  timestamp: string;
  step: string | null;
  agent: string | null;
  data: Record<string, unknown>;
}

export interface RunSummary {
  run_id: string;
  question: string;
  mode: string;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  created_at: string;
  error: string | null;
}

export interface Meta {
  version: string;
  modes: string[];
  profiles: string[];
  tools: string[];
  providers: { name: string; configured: boolean; description: string }[];
}
