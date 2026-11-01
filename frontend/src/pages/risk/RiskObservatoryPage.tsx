import { useQuery } from "@tanstack/react-query";
import { Activity, AlertOctagon, AlertTriangle, CheckCircle, ChevronRight, Info, Layers, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { api, qk } from "../../api";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { ErrorState } from "../../ui/States";

const TIER_COLORS: Record<string, { badge: "verified" | "neutral" | "pending" | "expired" | "mismatch"; bg: string }> = {
  A: { badge: "verified", bg: "bg-emerald-500/10" },
  B: { badge: "neutral", bg: "bg-blue-500/10" },
  C: { badge: "pending", bg: "bg-amber-500/10" },
  D: { badge: "expired", bg: "bg-orange-500/10" },
  E: { badge: "mismatch", bg: "bg-red-500/10" },
};

export default function RiskObservatoryPage() {
  const [selectedInstId, setSelectedInstId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const { data: sector, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: qk.sectorRisk,
    queryFn: () => api.sectorRisk(),
  });

  const { data: instDetail } = useQuery({
    queryKey: qk.instRisk(selectedInstId ?? ""),
    queryFn: () => api.institutionRisk(selectedInstId!),
    enabled: !!selectedInstId,
  });

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3">
        <Activity size={32} className="animate-spin text-brand-solid" />
        <span className="text-sm text-ink-3">Computing sector institutional risk observatory...</span>
      </div>
    );
  }

  if (error || !sector) return <ErrorState error={error} title="Failed to load Risk Observatory" onRetry={() => void refetch()} />;

  const filteredInsts = sector.institutions?.filter((i: any) =>
    i.institution_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    i.aicte_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    i.state.toLowerCase().includes(searchQuery.toLowerCase())
  ) ?? [];

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-solid/10 text-brand-solid">
              <Activity size={20} />
            </span>
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              Institutional Risk Intelligence Observatory
            </h1>
            <Badge tone="neutral" size="sm">RISK ENGINE V2</Badge>
          </div>
          <p className="mt-1 text-sm text-ink-3">
            Multi-factor, explainable risk scoring evaluating historical non-compliance recidivism, document replacement velocity, and cross-application faculty/seal overlaps.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void refetch()} disabled={isFetching}>
          <RefreshCw size={14} className={`mr-1 ${isFetching ? "animate-spin" : ""}`} />
          Refresh Metrics
        </Button>
      </div>

      {/* Sector Tier Distribution Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {(["A", "B", "C", "D", "E"] as const).map((tier) => {
          const count = sector.tier_distribution?.[tier] ?? 0;
          const conf = TIER_COLORS[tier];
          return (
            <Card key={tier} className={`p-4 space-y-1.5 border-t-4 ${conf.bg} border-t-current`}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-ink-2">Tier {tier}</span>
                <Badge tone={conf.badge} size="sm">
                  {tier === "A" ? "Low Risk" : tier === "B" ? "Moderate" : tier === "C" ? "Elevated" : tier === "D" ? "High" : "Critical"}
                </Badge>
              </div>
              <div className="text-2xl font-bold text-ink">{count}</div>
              <p className="text-[11px] text-ink-3">
                {tier === "A" && "Clean compliance history"}
                {tier === "B" && "Minor observations noted"}
                {tier === "C" && "Recurrent rectifications"}
                {tier === "D" && "High replacement velocity"}
                {tier === "E" && "Shared faculty / seal overlaps"}
              </p>
            </Card>
          );
        })}
      </div>

      {/* Main Observatory Layout: List on Left, Drilldown on Right */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Search & Institution Table (7 cols) */}
        <Card className="p-5 lg:col-span-7 space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
              <ShieldAlert size={16} />
              Evaluated Institutions ({filteredInsts.length})
            </h2>
            <div className="relative w-full sm:w-64">
              <Search size={14} className="absolute left-2.5 top-2.5 text-ink-3" />
              <input
                type="text"
                placeholder="Search institution, AICTE ID..."
                className="w-full rounded-md border border-edge bg-canvas-subtle pl-8 pr-3 py-1.5 text-xs text-ink"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge font-semibold uppercase text-ink-3">
                  <th className="pb-2.5">Institution</th>
                  <th className="pb-2.5">State</th>
                  <th className="pb-2.5">Tier</th>
                  <th className="pb-2.5">Risk Score</th>
                  <th className="pb-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {filteredInsts.map((inst: any) => {
                  const conf = TIER_COLORS[inst.risk_tier] ?? TIER_COLORS.B;
                  const isSelected = selectedInstId === inst.institution_id;
                  return (
                    <tr
                      key={inst.institution_id}
                      className={`hover:bg-canvas-subtle transition-colors cursor-pointer ${
                        isSelected ? "bg-canvas-subtle font-medium" : ""
                      }`}
                      onClick={() => setSelectedInstId(inst.institution_id)}
                    >
                      <td className="py-2.5">
                        <div className="font-semibold text-ink">{inst.institution_name}</div>
                        <div className="font-mono text-[11px] text-ink-3">{inst.aicte_id}</div>
                      </td>
                      <td className="py-2.5 text-ink-2">{inst.state}</td>
                      <td className="py-2.5">
                        <Badge tone={conf.badge} size="sm">
                          Tier {inst.risk_tier}
                        </Badge>
                      </td>
                      <td className="py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-16 rounded-full bg-edge overflow-hidden">
                            <div
                              className={`h-full ${
                                inst.risk_score > 60
                                  ? "bg-red-500"
                                  : inst.risk_score > 35
                                  ? "bg-amber-500"
                                  : "bg-emerald-500"
                              }`}
                              style={{ width: `${Math.min(inst.risk_score, 100)}%` }}
                            />
                          </div>
                          <span className="font-mono font-bold text-ink">{inst.risk_score.toFixed(0)}</span>
                        </div>
                      </td>
                      <td className="py-2.5 text-right">
                        <Button
                          variant={isSelected ? "primary" : "ghost"}
                          size="sm"
                          className="h-7 text-xs px-2"
                        >
                          View Factors
                          <ChevronRight size={12} className="ml-1" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Right Column: Explainable Risk Factor Drilldown (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {selectedInstId && instDetail ? (
            <Card className="p-5 space-y-4 border-l-4 border-l-brand-solid">
              <div>
                <div className="flex items-center justify-between">
                  <Badge tone={TIER_COLORS[instDetail.risk_tier]?.badge ?? "neutral"} size="sm">
                    Tier {instDetail.risk_tier} Risk Profile
                  </Badge>
                  <span className="font-mono text-xs text-ink-3">{instDetail.aicte_id}</span>
                </div>
                <h3 className="mt-1 text-base font-bold text-ink">{instDetail.institution_name}</h3>
                <p className="text-xs text-ink-3">{instDetail.address}, {instDetail.state}</p>
              </div>

              {/* Score Meter */}
              <div className="rounded-lg bg-canvas-subtle p-3 border border-edge flex items-center justify-between">
                <div>
                  <span className="text-xs text-ink-3">Composite Risk Score</span>
                  <div className="text-2xl font-bold text-ink">{instDetail.composite_risk_score.toFixed(1)} / 100</div>
                </div>
                <div className="text-right">
                  <span className="text-xs text-ink-3">Determination</span>
                  <div className="text-xs font-semibold text-ink">
                    {instDetail.risk_tier === "E" ? "Vigilance Audit Recommended" :
                     instDetail.risk_tier === "D" ? "Pre-Scrutiny Surprise Inspection" :
                     instDetail.risk_tier === "C" ? "Detailed Document Scrutiny" : "Standard Automated Review"}
                  </div>
                </div>
              </div>

              {/* Explainable Contributing Factors */}
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1">
                  <Layers size={14} />
                  Contributing Risk Factors & Evidence
                </h4>

                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {instDetail.factors?.length > 0 ? (
                    instDetail.factors.map((f: any, idx: number) => (
                      <div key={idx} className="rounded-md border border-edge p-3 bg-canvas space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-xs text-ink flex items-center gap-1.5">
                            {f.severity === "critical" ? (
                              <AlertOctagon size={13} className="text-red-500" />
                            ) : f.severity === "high" ? (
                              <AlertTriangle size={13} className="text-amber-500" />
                            ) : (
                              <Info size={13} className="text-blue-500" />
                            )}
                            {f.title}
                          </span>
                          <span className="font-mono font-bold text-xs text-amber-600">
                            +{f.score_contribution.toFixed(1)}
                          </span>
                        </div>
                        <p className="text-[11px] text-ink-3">{f.explanation}</p>
                        {f.evidence_references?.length > 0 && (
                          <div className="mt-1 text-[10px] font-mono text-ink-3 bg-canvas-subtle p-1 rounded">
                            Ref: {JSON.stringify(f.evidence_references[0])}
                          </div>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="p-4 text-center text-xs text-emerald-600 flex items-center justify-center gap-2">
                      <CheckCircle size={14} />
                      Zero anomalous risk factors detected.
                    </div>
                  )}
                </div>
              </div>
            </Card>
          ) : (
            <Card className="p-8 text-center space-y-2 bg-canvas-subtle/50">
              <Activity size={24} className="mx-auto text-ink-3" />
              <h3 className="text-sm font-semibold text-ink">Select an Institution</h3>
              <p className="text-xs text-ink-3">
                Click any institution row to inspect its explainable risk breakdown and evidence citations.
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
