import { useQuery } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, CheckCircle, FileCheck, FileDiff } from "lucide-react";
import { useState } from "react";
import { api, qk } from "../../api";
import { Badge } from "../../ui/Badge";
import { Card } from "../../ui/Card";
import { ErrorState } from "../../ui/States";

export default function DocumentComparePage() {
  const [targetAppId, setTargetAppId] = useState("APP-2026-000107");

  const { data: crossDoc, isLoading, error, refetch } = useQuery({
    queryKey: qk.crossDoc(targetAppId),
    queryFn: () => api.crossDoc(targetAppId),
  });

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-solid/10 text-brand-solid">
              <FileDiff size={20} />
            </span>
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              Cross-Document Intelligence & Contradiction Analyzer
            </h1>
            <Badge tone="pending" size="sm">MULTI-DOC AI CHECK</Badge>
          </div>
          <p className="mt-1 text-sm text-ink-3">
            Cross-compares claims across distinct affidavits, municipal approvals, architect certificates, and land titles to catch internal inconsistencies, contradictory figures, and missing mandatory filings.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="text-xs font-medium text-ink-3">Application:</label>
          <select
            className="rounded-md border border-edge bg-canvas-subtle p-1.5 text-xs text-ink"
            value={targetAppId}
            onChange={(e) => setTargetAppId(e.target.value)}
          >
            <option value="APP-2026-000107">APP-2026-000107 (Panchganga Institute of Technology)</option>
            <option value="APP-2026-000101">APP-2026-000101 (Sahyadri College of Engineering)</option>
            <option value="APP-2026-000111">APP-2026-000111 (Marathwada Academy of Technology)</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3">
          <FileDiff size={32} className="animate-spin text-brand-solid" />
          <span className="text-sm text-ink-3">Running cross-document comparison and contradiction detection...</span>
        </div>
      ) : error || !crossDoc ? (
        <ErrorState error={error} title="Failed to load cross-document analysis" onRetry={() => void refetch()} />
      ) : (
        <div className="space-y-6">
          {/* Key Metrics */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Documents Analyzed</span>
              <div className="text-2xl font-bold text-ink">{crossDoc.documents_analyzed}</div>
              <span className="text-[11px] text-ink-3">Uploaded filings verified</span>
            </Card>

            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Contradictions Flagged</span>
              <div className={`text-2xl font-bold ${crossDoc.contradictions_count > 0 ? "text-amber-600" : "text-emerald-600"}`}>
                {crossDoc.contradictions_count}
              </div>
              <span className="text-[11px] text-ink-3">Cross-document field mismatches</span>
            </Card>

            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Completeness Score</span>
              <div className="text-2xl font-bold text-ink">{crossDoc.completeness?.completeness_score}%</div>
              <span className="text-[11px] text-emerald-600">
                {crossDoc.completeness?.present_count} / {crossDoc.completeness?.required_count} Mandatory Documents
              </span>
            </Card>

            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Missing Filings</span>
              <div className="text-2xl font-bold text-ink">
                {crossDoc.completeness?.missing_types?.length ?? 0}
              </div>
              <span className="text-[11px] text-ink-3">Statutory prerequisites omitted</span>
            </Card>
          </div>

          {/* Contradictions Section */}
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
              <AlertTriangle size={16} className="text-amber-500" />
              Observed Cross-Document Contradictions & Discrepancies
            </h2>

            {crossDoc.contradictions?.length > 0 ? (
              <div className="space-y-3">
                {crossDoc.contradictions.map((c: any, idx: number) => (
                  <div key={idx} className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm text-ink flex items-center gap-2">
                        <AlertCircle size={15} className="text-amber-600" />
                        {c.title}
                      </span>
                      <Badge tone={c.severity === "high" ? "mismatch" : "pending"} size="sm">
                        {c.severity?.toUpperCase()} SEVERITY
                      </Badge>
                    </div>
                    <p className="text-xs text-ink-2">{c.detail}</p>
                    <div className="rounded bg-canvas p-2.5 border border-edge text-xs grid grid-cols-1 md:grid-cols-2 gap-2">
                      <div className="space-y-0.5">
                        <span className="text-[11px] font-semibold text-ink-3">Primary Source Claim:</span>
                        <div className="font-mono text-ink text-[11px]">
                          {c.evidence?.[0]?.source_file ?? "Document A"}: &quot;{c.evidence?.[0]?.claimed_value ?? "N/A"}&quot;
                        </div>
                      </div>
                      <div className="space-y-0.5">
                        <span className="text-[11px] font-semibold text-ink-3">Conflicting Source Claim:</span>
                        <div className="font-mono text-ink text-[11px]">
                          {c.evidence?.[1]?.source_file ?? "Document B"}: &quot;{c.evidence?.[1]?.claimed_value ?? "N/A"}&quot;
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-6 text-center text-xs text-emerald-700 dark:text-emerald-300 flex items-center justify-center gap-2">
                <CheckCircle size={16} />
                <span>Zero cross-document contradictions detected across all analyzed certificates.</span>
              </div>
            )}
          </Card>

          {/* Completeness Checklist */}
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
              <FileCheck size={16} />
              Statutory Mandatory Document Checklist
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              {crossDoc.completeness?.missing_types?.length > 0 && (
                <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 space-y-1.5">
                  <span className="font-semibold text-red-700 dark:text-red-300 block">Missing Filings (Deficiency Trigger):</span>
                  <ul className="list-disc list-inside space-y-1 text-ink-2">
                    {crossDoc.completeness.missing_types.map((m: string) => (
                      <li key={m} className="font-mono">{m}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 space-y-1.5">
                <span className="font-semibold text-emerald-700 dark:text-emerald-300 block">Successfully Submitted & Verified:</span>
                <ul className="list-disc list-inside space-y-1 text-ink-2">
                  {crossDoc.completeness?.present_types?.map((p: string) => (
                    <li key={p} className="font-mono">{p}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
