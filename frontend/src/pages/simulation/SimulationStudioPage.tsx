import { useMutation, useQuery } from "@tanstack/react-query";
import { FileSliders, Play, RotateCcw, Scale, Sliders, TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";
import { api, qk } from "../../api";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";

interface ParamOverrides {
  faculty_ratio: number;
  min_bandwidth_mbps: number;
  min_land_acres: number;
}

export default function SimulationStudioPage() {
  const [baseVersion, setBaseVersion] = useState("aicte-aph-2024-27");
  const [targetVersion, setTargetVersion] = useState("aicte-aph-2027-28-draft");
  const [overrides, setOverrides] = useState<ParamOverrides>({
    faculty_ratio: 15,
    min_bandwidth_mbps: 500,
    min_land_acres: 2.5,
  });

  const { data: rulesets } = useQuery({
    queryKey: qk.rulesetsList,
    queryFn: () => api.rulesets(),
  });

  const { data: diffData, isFetching: diffLoading, refetch: runDiff } = useQuery({
    queryKey: qk.rulesetDiff(baseVersion, targetVersion),
    queryFn: () => api.compareRulesets(baseVersion, targetVersion),
    enabled: false,
  });

  const simMutation = useMutation({
    mutationFn: (payload: any) => api.simulateRules(payload),
  });

  const handleRunSimulation = () => {
    simMutation.mutate({
      baseline_version: baseVersion,
      simulated_version: targetVersion,
      parameter_overrides: {
        faculty_student_ratio: overrides.faculty_ratio,
        internet_bandwidth_mbps: overrides.min_bandwidth_mbps,
        land_area_acres: overrides.min_land_acres,
      },
    });
  };

  const simResult = simMutation.data;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-solid/10 text-brand-solid">
              <Scale size={20} />
            </span>
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              Regulatory Intelligence 2.0: What-If Simulation Studio
            </h1>
            <Badge tone="pending" size="sm">SIMULATION SANDBOX</Badge>
          </div>
          <p className="mt-1 text-sm text-ink-3">
            Forecast the nationwide regulatory impact of proposed Approval Process Handbook amendments across all institutional applications prior to formal gazette notification.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setOverrides({ faculty_ratio: 20, min_bandwidth_mbps: 300, min_land_acres: 2.5 });
              void runDiff();
            }}
          >
            <RotateCcw size={14} className="mr-1" />
            Reset Defaults
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleRunSimulation}
            disabled={simMutation.isPending}
          >
            <Play size={14} className="mr-1 fill-current" />
            {simMutation.isPending ? "Simulating..." : "Run Sector Simulation"}
          </Button>
        </div>
      </div>

      {/* Control Studio Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Ruleset Version Selector */}
        <Card className="p-5 space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
            <FileSliders size={16} />
            Ruleset Comparative Base
          </h2>

          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-ink-2">Baseline Gazette Ruleset</label>
              <select
                className="mt-1 block w-full rounded-md border border-edge bg-canvas-subtle p-2 text-sm text-ink"
                value={baseVersion}
                onChange={(e) => setBaseVersion(e.target.value)}
              >
                {rulesets?.map((rs) => (
                  <option key={rs.id} value={rs.id}>
                    {rs.title} ({rs.academic_year})
                  </option>
                )) ?? <option value="aicte-aph-2024-27">AICTE APH 2024-27 (Current)</option>}
              </select>
            </div>

            <div>
              <label className="text-xs font-medium text-ink-2">Proposed / Draft Ruleset</label>
              <select
                className="mt-1 block w-full rounded-md border border-edge bg-canvas-subtle p-2 text-sm text-ink"
                value={targetVersion}
                onChange={(e) => setTargetVersion(e.target.value)}
              >
                {rulesets?.map((rs) => (
                  <option key={rs.id} value={rs.id}>
                    {rs.title} {rs.status === "draft" ? "[Draft]" : ""}
                  </option>
                )) ?? <option value="aicte-aph-2027-28-draft">AICTE APH 2027-28 [Consultation Draft]</option>}
              </select>
            </div>

            <Button
              variant="secondary"
              size="sm"
              className="w-full text-xs"
              onClick={() => void runDiff()}
              disabled={diffLoading}
            >
              {diffLoading ? "Analyzing Diff..." : "Inspect Clause Differences"}
            </Button>
          </div>
        </Card>

        {/* Policy Parameter Levers */}
        <Card className="p-5 space-y-4 lg:col-span-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
            <Sliders size={16} />
            What-If Policy Levers & Sensitivity Overrides
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Faculty Student Ratio */}
            <div className="rounded-lg border border-edge p-3 bg-canvas-subtle space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-medium text-ink">Faculty:Student Ratio</span>
                <span className="text-xs font-bold text-brand-solid">1:{overrides.faculty_ratio}</span>
              </div>
              <input
                type="range"
                min="10"
                max="25"
                step="1"
                value={overrides.faculty_ratio}
                onChange={(e) => setOverrides({ ...overrides, faculty_ratio: parseInt(e.target.value, 10) })}
                className="w-full accent-brand-solid"
              />
              <p className="text-[11px] text-ink-3">Standard APH norm is 1:20. Lower ratio requires hiring more faculty.</p>
            </div>

            {/* Minimum Bandwidth */}
            <div className="rounded-lg border border-edge p-3 bg-canvas-subtle space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-medium text-ink">Min Internet Bandwidth</span>
                <span className="text-xs font-bold text-brand-solid">{overrides.min_bandwidth_mbps} Mbps</span>
              </div>
              <input
                type="range"
                min="100"
                max="1000"
                step="100"
                value={overrides.min_bandwidth_mbps}
                onChange={(e) => setOverrides({ ...overrides, min_bandwidth_mbps: parseInt(e.target.value, 10) })}
                className="w-full accent-brand-solid"
              />
              <p className="text-[11px] text-ink-3">Simulate nationwide high-speed connectivity requirement changes.</p>
            </div>

            {/* Land Area */}
            <div className="rounded-lg border border-edge p-3 bg-canvas-subtle space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-medium text-ink">Min Land Area</span>
                <span className="text-xs font-bold text-brand-solid">{overrides.min_land_acres} Acres</span>
              </div>
              <input
                type="range"
                min="1.0"
                max="5.0"
                step="0.5"
                value={overrides.min_land_acres}
                onChange={(e) => setOverrides({ ...overrides, min_land_acres: parseFloat(e.target.value) })}
                className="w-full accent-brand-solid"
              />
              <p className="text-[11px] text-ink-3">Urban / rural zoning buffer requirement testing.</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Ruleset Diff Panel (if loaded) */}
      {diffData && (
        <Card className="p-5 border-l-4 border-l-brand-solid space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">
              Clause Differences: {diffData.base_version} → {diffData.target_version}
            </h3>
            <div className="flex gap-2">
              <Badge tone="verified" size="sm">{diffData.added_rules?.length ?? 0} Added</Badge>
              <Badge tone="pending" size="sm">{diffData.modified_rules?.length ?? 0} Modified</Badge>
              <Badge tone="mismatch" size="sm">{diffData.removed_rules?.length ?? 0} Deprecated</Badge>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="p-3 bg-canvas-subtle rounded border border-edge">
              <span className="font-semibold text-ink">Newly Introduced Clauses:</span>
              <ul className="mt-1 list-disc list-inside space-y-1 text-ink-2">
                {diffData.added_rules?.map((r: any) => (
                  <li key={r.id}><span className="font-mono text-ink">{r.id}</span>: {r.title}</li>
                )) ?? <li>None</li>}
              </ul>
            </div>
            <div className="p-3 bg-canvas-subtle rounded border border-edge">
              <span className="font-semibold text-ink">Modified Thresholds:</span>
              <ul className="mt-1 list-disc list-inside space-y-1 text-ink-2">
                {diffData.modified_rules?.map((r: any) => (
                  <li key={r.id}><span className="font-mono text-ink">{r.id}</span>: {r.title}</li>
                )) ?? <li>None</li>}
              </ul>
            </div>
          </div>
        </Card>
      )}

      {/* Simulation Results Output */}
      {simResult && (
        <div className="space-y-6">
          {/* Key Metric Highlights */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Applications Evaluated</span>
              <div className="text-2xl font-bold text-ink">{simResult.applications_simulated}</div>
              <span className="text-[11px] text-ink-3">Live synthetic database pool</span>
            </Card>

            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Sector Baseline Score</span>
              <div className="text-2xl font-bold text-ink">{simResult.baseline_average_score}%</div>
              <span className="text-[11px] text-emerald-600">Current handbook rules</span>
            </Card>

            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Simulated Sector Score</span>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold text-ink">{simResult.simulated_average_score}%</span>
                {simResult.simulated_average_score < simResult.baseline_average_score ? (
                  <TrendingDown size={18} className="text-amber-500" />
                ) : (
                  <TrendingUp size={18} className="text-emerald-500" />
                )}
              </div>
              <span className="text-[11px] text-amber-600">
                {(simResult.simulated_average_score - simResult.baseline_average_score).toFixed(1)}% Projected Shift
              </span>
            </Card>

            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">New Deficiencies Created</span>
              <div className="text-2xl font-bold text-amber-600">{simResult.newly_deficient_applications}</div>
              <span className="text-[11px] text-ink-3">Institutions requiring transition grace period</span>
            </Card>
          </div>

          {/* Detailed Impact Breakdown Table */}
          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-ink">Institutional Impact Distribution</h3>
              <span className="text-xs text-ink-3">
                Showing {simResult.impacts?.length ?? 0} applications evaluated against proposed criteria
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-edge text-xs font-semibold uppercase text-ink-3">
                    <th className="pb-3">Application / Institution</th>
                    <th className="pb-3">Category</th>
                    <th className="pb-3">State</th>
                    <th className="pb-3">Baseline</th>
                    <th className="pb-3">Simulated</th>
                    <th className="pb-3">Impact Determination</th>
                    <th className="pb-3">New Deficiencies</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge">
                  {simResult.impacts?.map((imp: any) => (
                    <tr key={imp.application_id} className="hover:bg-canvas-subtle/50 transition-colors">
                      <td className="py-3">
                        <div className="font-medium text-ink">{imp.institution_name}</div>
                        <div className="text-xs font-mono text-ink-3">{imp.application_id} • {imp.aicte_id}</div>
                      </td>
                      <td className="py-3 text-xs text-ink-2">{imp.category}</td>
                      <td className="py-3 text-xs text-ink-2">{imp.state}</td>
                      <td className="py-3 font-mono text-xs text-ink">{imp.baseline_compliance_score}%</td>
                      <td className="py-3 font-mono text-xs text-ink">{imp.simulated_compliance_score}%</td>
                      <td className="py-3">
                        {imp.status_change === "new_deficiency" ? (
                          <Badge tone="mismatch" size="sm">New Deficiency</Badge>
                        ) : imp.status_change === "improved" ? (
                          <Badge tone="verified" size="sm">Improved</Badge>
                        ) : (
                          <Badge tone="neutral" size="sm">Unaffected</Badge>
                        )}
                      </td>
                      <td className="py-3 text-xs text-ink-2">
                        {imp.new_violations?.length > 0 ? (
                          <span className="font-semibold text-amber-600">
                            {imp.new_violations.length} new clause failure(s)
                          </span>
                        ) : (
                          <span className="text-ink-3">Compliant</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* Initial Guidance Card */}
      {!simResult && !simMutation.isPending && (
        <Card className="p-8 text-center space-y-3 bg-canvas-subtle/50">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-solid/10 text-brand-solid">
            <Sliders size={24} />
          </div>
          <h3 className="text-base font-semibold text-ink">Ready to Execute Regulatory Simulation</h3>
          <p className="mx-auto max-w-lg text-sm text-ink-3">
            Adjust the policy levers above or select draft handbook clauses, then click &quot;Run Sector Simulation&quot; to test compliance changes across the institutional dataset.
          </p>
        </Card>
      )}
    </div>
  );
}
