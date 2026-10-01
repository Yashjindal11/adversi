import type { ClaimStatus } from "../types";

const LABEL: Record<ClaimStatus, string> = {
  supported: "supported",
  partially_supported: "partially supported",
  unsupported: "unsupported",
  contradicted: "contradicted",
  uncertain: "uncertain",
  unverified: "unverified",
};

export function StatusPill({ status }: { status: ClaimStatus }) {
  return <span className={`pill s-${status}`}>{LABEL[status]}</span>;
}

export const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${Math.round(v * 100)}%`);
export const num = (v: number | null | undefined, d = 2) => (v == null ? "n/a" : v.toFixed(d));
