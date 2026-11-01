import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  RefreshCw,
  RotateCw,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { api, qk } from "../../api";
import { fmtDateTime } from "../../lib/format";
import type { Tone } from "../../lib/labels";
import {
  Button,
  Callout,
  DataTable,
  Dialog,
  Digest,
  EmptyState,
  Page,
  PageHeader,
  Panel,
  Skeleton,
  Stat,
  StatGroup,
  StatusBadge,
  Tabs,
  Toolbar,
  useToast,
  type Column,
  type TabItem,
} from "../../ui2";
import type { CertValidationResponse, KmsKey } from "./types";

const TRUST_TABS: TabItem[] = [
  { id: "keys", label: "KMS Keys & Lifecycle" },
  { id: "hsm", label: "HSM Hardware Security" },
  { id: "certificates", label: "X.509 Certificates" },
  { id: "crl", label: "CRL & Revocation" },
  { id: "anchors", label: "Trust Store" },
  { id: "incidents", label: "Security Incidents" },
];

export default function TrustDashboardPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState("keys");

  // Queries
  const keysQuery = useQuery({ queryKey: qk.trustKeys, queryFn: () => api.trustKeys() });
  const hsmQuery = useQuery({ queryKey: qk.hsmHealth, queryFn: () => api.hsmHealth() });
  const certsQuery = useQuery({ queryKey: qk.certificates, queryFn: () => api.certificates() });
  const crlQuery = useQuery({ queryKey: qk.crlList, queryFn: () => api.crlList() });
  const [anchorEnv, setAnchorEnv] = useState<"development" | "test" | "production">("development");
  const anchorsQuery = useQuery({
    queryKey: qk.trustAnchors(anchorEnv),
    queryFn: () => api.trustAnchors(anchorEnv),
  });
  const incidentsQuery = useQuery({ queryKey: qk.trustIncidents, queryFn: () => api.trustIncidents() });

  // Dialog States
  const [rotateKeyTarget, setRotateKeyTarget] = useState<KmsKey | null>(null);
  const [rotateReason, setRotateReason] = useState("Scheduled rotation");
  const [revokeKeyTarget, setRevokeKeyTarget] = useState<KmsKey | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [incidentDialogOpen, setIncidentDialogOpen] = useState(false);
  const [incidentKeyId, setIncidentKeyId] = useState("");
  const [incidentDesc, setIncidentDesc] = useState("");
  const [validateCertPem, setValidateCertPem] = useState("");
  const [validationResult, setValidationResult] = useState<CertValidationResponse | null>(null);

  // Mutations
  const rotateMutation = useMutation({
    mutationFn: (vars: { keyId: string; reason: string }) =>
      api.rotateTrustKey(vars.keyId, { rotation_reason: vars.reason }),
    onSuccess: (data) => {
      toast.success(
        "Key Rotated Successfully",
        `Old: ${data.old_key_id} -> New: ${data.new_key_id} (v${data.new_version})`,
      );
      setRotateKeyTarget(null);
      void qc.invalidateQueries({ queryKey: qk.trustKeys });
    },
    onError: (err: any) => {
      toast.error("Rotation Failed", err.message);
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (vars: { keyId: string; reason: string }) =>
      api.revokeTrustKey(vars.keyId, { reason: vars.reason }),
    onSuccess: (data) => {
      toast.info("Key Revoked", `Key ${data.key_id} has been transitioned to REVOKED`);
      setRevokeKeyTarget(null);
      void qc.invalidateQueries({ queryKey: qk.trustKeys });
    },
    onError: (err: any) => {
      toast.error("Revocation Failed", err.message);
    },
  });

  const raiseIncidentMutation = useMutation({
    mutationFn: (vars: { keyId?: string; desc: string }) =>
      api.raiseIncident({
        incident_type: "KEY_COMPROMISE",
        description: vars.desc,
        affected_key_id: vars.keyId || undefined,
        severity: "CRITICAL",
      }),
    onSuccess: () => {
      toast.error(
        "Incident Raised & Key Suspended",
        "Affected cryptographic key immediately transitioned to COMPROMISED",
      );
      setIncidentDialogOpen(false);
      setIncidentDesc("");
      void qc.invalidateQueries({ queryKey: qk.trustIncidents });
      void qc.invalidateQueries({ queryKey: qk.trustKeys });
    },
    onError: (err: any) => {
      toast.error("Failed to Raise Incident", err.message);
    },
  });

  const recoverMutation = useMutation({
    mutationFn: (incidentId: string) =>
      api.recoverIncident(incidentId, {
        generate_replacement_key: true,
        resolution_notes: "Emergency recovery completed; clean replacement key generated.",
      }),
    onSuccess: (data) => {
      toast.success(
        "Emergency Recovery Complete",
        `Replacement key ${data.replacement_key_id} activated.`,
      );
      void qc.invalidateQueries({ queryKey: qk.trustIncidents });
      void qc.invalidateQueries({ queryKey: qk.trustKeys });
    },
    onError: (err: any) => {
      toast.error("Recovery Execution Failed", err.message);
    },
  });

  const validateCertMutation = useMutation({
    mutationFn: (pem: string) => api.validateCert({ certificate_pem: pem, environment: anchorEnv }),
    onSuccess: (res) => {
      setValidationResult(res);
      if (res.valid) {
        toast.success("Certificate Valid", "Cryptographic chain and signature verified");
      } else {
        toast.error(`Certificate ${res.status}`, res.error || "Validation issue detected");
      }
    },
    onError: (err: any) => {
      toast.error("Validation Error", err.message);
    },
  });

  const keys = keysQuery.data ?? [];
  const hsm = hsmQuery.data;
  const certs = certsQuery.data ?? [];
  const crls = crlQuery.data ?? [];
  const anchors = anchorsQuery.data ?? [];
  const incidents = incidentsQuery.data ?? [];

  const activeKeysCount = keys.filter((k) => k.status === "ACTIVE").length;
  const openIncidentsCount = incidents.filter((i) => i.status === "OPEN").length;

  const keyColumns: Column<KmsKey>[] = [
    {
      id: "key_id",
      header: "Key Identifier",
      cell: (row) => (
        <div>
          <div className="font-mono text-xs font-semibold text-ink">{row.key_id}</div>
          <div className="text-2xs text-ink-3">v{row.version} • {row.key_purpose}</div>
        </div>
      ),
    },
    {
      id: "algorithm",
      header: "Algorithm & Provider",
      cell: (row) => (
        <div>
          <span className="font-mono text-xs text-ink-2">{row.algorithm}</span>
          <div className="text-2xs text-ink-3">{row.provider_type}</div>
        </div>
      ),
    },
    {
      id: "status",
      header: "Status",
      cell: (row) => {
        const tone: Tone =
          row.status === "ACTIVE"
            ? "verified"
            : row.status === "RETIRED"
            ? "unchecked"
            : row.status === "COMPROMISED" || row.status === "REVOKED"
            ? "mismatch"
            : "manual";
        return <StatusBadge tone={tone}>{row.status}</StatusBadge>;
      },
    },
    {
      id: "fingerprint",
      header: "Fingerprint",
      cell: (row) => <Digest value={row.public_key_fingerprint} head={6} tail={6} />,
    },
    {
      id: "usage",
      header: "Usage Count",
      cell: (row) => <span className="font-mono text-xs tabular-nums">{row.usage_count.toLocaleString()}</span>,
    },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (row) => (
        <div className="flex items-center justify-end gap-1.5">
          {row.status === "ACTIVE" && (
            <>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setRotateKeyTarget(row)}
                title="Rotate Key to New Version"
              >
                <RotateCw className="size-3 mr-1" /> Rotate
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={() => setRevokeKeyTarget(row)}
                title="Revoke Key"
              >
                Revoke
              </Button>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Hardware Security & Trust Infrastructure"
        context="FIPS 140-3 HSM abstraction, Key Management Service (KMS), X.509 PKI, and anti-rollback revocation synchronization."
        primary={
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              setIncidentKeyId(keys[0]?.key_id || "");
              setIncidentDialogOpen(true);
            }}
          >
            <ShieldAlert className="size-4 mr-1 text-red-500" /> Raise Incident
          </Button>
        }
        secondary={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              void keysQuery.refetch();
              void hsmQuery.refetch();
              void certsQuery.refetch();
              void crlQuery.refetch();
              void anchorsQuery.refetch();
              void incidentsQuery.refetch();
            }}
          >
            <RefreshCw className="size-4 mr-1" /> Refresh
          </Button>
        }
      />

      <StatGroup>
        <Stat
          label="Active KMS Keys"
          value={activeKeysCount}
          hint={`${keys.length} total keys in keystore`}
        />
        <Stat
          label="HSM Provider Status"
          value={hsm?.active_provider ? "Emulated OpenSSL" : "Offline"}
          hint="Honest: No physical PKCS#11 attached"
        />
        <Stat
          label="Trust Anchors"
          value={anchors.length}
          hint={`Environment: ${anchorEnv}`}
        />
        <Stat
          label="Security Incidents"
          value={openIncidentsCount}
          tone={openIncidentsCount > 0 ? "danger" : "default"}
          hint={openIncidentsCount > 0 ? "Requires emergency recovery" : "All systems normal"}
        />
      </StatGroup>

      <Tabs items={TRUST_TABS} value={activeTab} onChange={setActiveTab} label="Trust Infrastructure Sections" />

      {activeTab === "keys" && (
        <div className="space-y-4">
          <Callout tone="info" title="Cryptographic Key Lifecycle & Historical Verification">
            Rotating a key increments its version (<span className="font-mono">v1 → v2</span>) and transitions the old key to{" "}
            <span className="font-semibold">RETIRED</span>. The old public key is permanently retained in the database,
            guaranteeing that historical Merkle audit checkpoints, JWS QR codes, and offline field inspection reports remain
            100% verifiable forever.
          </Callout>

          <Panel title="Managed Cryptographic Keys" description="Keys managed by KMS state machine">
            {keysQuery.isLoading ? (
              <Skeleton className="h-64" />
            ) : (
              <DataTable
                columns={keyColumns}
                rows={keys}
                rowKey={(k) => k.id}
                label="Managed Cryptographic Keys"
                empty={<EmptyState title="No Keys Found" description="Generate keys to begin cryptographic signing." />}
              />
            )}
          </Panel>
        </div>
      )}

      {activeTab === "hsm" && (
        <div className="space-y-4">
          <Callout tone="warning" title="Hardware Security Module (HSM) Honest Transparency Statement">
            In accordance with PRAMANA security architecture rules, this environment operates under{" "}
            <span className="font-bold">DEVELOPMENT_PROVIDER</span> mode utilizing OpenSSL / cryptography primitives.
            Physical HSM / PKCS#11 hardware (e.g. Nitrokey HSM, YubiHSM, or Cloud HSM) is not connected. All operations
            faithfully implement the standard HSM abstraction interface.
          </Callout>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {hsm &&
              Object.entries(hsm.providers).map(([providerKey, p]) => (
                <Panel key={providerKey} title={p.provider_name}>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-ink-3">Type:</span>
                      <span className="font-mono text-xs font-semibold">{p.provider_type}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-ink-3">Hardware-Backed:</span>
                      <span
                        className={`text-xs font-bold ${
                          p.is_hardware_backed ? "text-verified-fg" : "text-manual-fg"
                        }`}
                      >
                        {p.is_hardware_backed ? "YES (Physical Hardware)" : "NO (Software Simulation)"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-ink-3">Status:</span>
                      <StatusBadge tone={p.status === "HEALTHY" ? "verified" : "unchecked"}>
                        {p.status}
                      </StatusBadge>
                    </div>
                    <div>
                      <span className="text-xs text-ink-3 block mb-1">Status Message:</span>
                      <p className="text-xs font-mono bg-surface-2 p-2 rounded border border-line">
                        {p.status_message}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-ink-3 block mb-1">Supported Cryptographic Primitives:</span>
                      <div className="flex flex-wrap gap-1">
                        {p.algorithms_supported.map((alg) => (
                          <span
                            key={alg}
                            className="text-2xs font-mono bg-surface-2 px-2 py-0.5 rounded border border-line"
                          >
                            {alg}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </Panel>
              ))}
          </div>
        </div>
      )}

      {activeTab === "certificates" && (
        <div className="space-y-4">
          <Panel title="Interactive X.509 Certificate Chain Validator">
            <div className="space-y-3">
              <p className="text-xs text-ink-2">
                Paste any PEM-encoded X.509 certificate to validate against expiration, self-signed trust anchor status, and
                issuing CA digital signature.
              </p>
              <textarea
                value={validateCertPem}
                onChange={(e) => setValidateCertPem(e.target.value)}
                placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                rows={5}
                className="w-full font-mono text-xs p-2.5 rounded border border-line bg-surface focus:outline-none focus:ring-1 focus:ring-brand-solid"
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-ink-3">Environment: {anchorEnv}</span>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={!validateCertPem.trim() || validateCertMutation.isPending}
                  onClick={() => validateCertMutation.mutate(validateCertPem)}
                >
                  <ShieldCheck className="size-4 mr-1" /> Validate Certificate
                </Button>
              </div>

              {validationResult && (
                <div
                  className={`mt-4 p-3 rounded border text-xs ${
                    validationResult.valid
                      ? "bg-verified-bg border-verified-dot/30 text-ink"
                      : "bg-mismatch-bg border-mismatch-dot/30 text-mismatch-fg"
                  }`}
                >
                  <div className="flex items-center gap-2 font-semibold">
                    {validationResult.valid ? (
                      <CheckCircle2 className="size-4 text-verified-fg" />
                    ) : (
                      <XCircle className="size-4 text-mismatch-fg" />
                    )}
                    <span>Status: {validationResult.status}</span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-2xs font-mono">
                    <div>Subject: {validationResult.subject_dn}</div>
                    <div>Issuer: {validationResult.issuer_dn}</div>
                    <div>Serial: {validationResult.serial_number}</div>
                    <div>Days to Expiry: {validationResult.days_until_expiry}</div>
                  </div>
                  {validationResult.error && (
                    <div className="mt-2 text-2xs font-semibold">
                      Reason: {validationResult.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          </Panel>

          <Panel title="Registered X.509 Certificates in Trust Store">
            <div className="space-y-2">
              {certs.map((c) => (
                <div
                  key={c.id}
                  className="p-3 border border-line rounded flex items-center justify-between bg-surface"
                >
                  <div className="space-y-1">
                    <div className="font-semibold text-xs text-ink">{c.subject_dn}</div>
                    <div className="text-2xs text-ink-3">
                      Issuer: {c.issuer_dn} • Serial: {c.serial_number}
                    </div>
                    <div className="text-2xs text-ink-3">
                      Valid: {fmtDateTime(c.not_before)} to {fmtDateTime(c.not_after)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge tone={c.trust_status === "TRUSTED_ANCHOR" ? "verified" : "unchecked"}>
                      {c.trust_status}
                    </StatusBadge>
                    <StatusBadge tone={c.revocation_status === "GOOD" ? "verified" : "mismatch"}>
                      {c.revocation_status}
                    </StatusBadge>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      )}

      {activeTab === "crl" && (
        <div className="space-y-4">
          <Callout tone="info" title="Dynamic CRL Synchronization & Anti-Rollback Security">
            PRAMANA implements RFC 5280 CRL verification with sequence number anti-rollback protection. Replay attempts
            presenting older CRL versions (<span className="font-mono">CRLNumber ≤ Current</span>) are cryptographically
            rejected to prevent rollback attacks.
          </Callout>

          <Panel title="Synchronized Certificate Revocation Lists (CRL)">
            {crls.length === 0 ? (
              <EmptyState title="No CRLs Synchronized" description="Synchronize an X.509 CRL to populate revocation data." />
            ) : (
              <div className="space-y-2">
                {crls.map((crl) => (
                  <div
                    key={crl.id}
                    className="p-3 border border-line rounded flex items-center justify-between bg-surface"
                  >
                    <div>
                      <div className="font-semibold text-xs text-ink">
                        CRL #{crl.crl_number} — {crl.issuer_dn}
                      </div>
                      <div className="text-2xs text-ink-3">
                        Revoked Certificates: {crl.revoked_count} • Next Update: {fmtDateTime(crl.next_update)}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge tone={crl.signature_valid ? "verified" : "mismatch"}>
                        {crl.signature_valid ? "Signature Verified" : "Bad Signature"}
                      </StatusBadge>
                      <StatusBadge tone="unchecked">{crl.status}</StatusBadge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {activeTab === "anchors" && (
        <div className="space-y-4">
          <Toolbar>
            <div className="flex items-center gap-2">
              <span className="text-xs text-ink-2 font-medium">Environment:</span>
              {(["development", "test", "production"] as const).map((env) => (
                <Button
                  key={env}
                  size="sm"
                  variant={anchorEnv === env ? "primary" : "secondary"}
                  onClick={() => setAnchorEnv(env)}
                >
                  {env.toUpperCase()}
                </Button>
              ))}
            </div>
          </Toolbar>

          <Panel title={`Trust Store Anchors (${anchorEnv.toUpperCase()})`}>
            {anchors.length === 0 ? (
              <EmptyState
                title="No Trust Anchors Configured"
                description={`No root certificate authorities are registered in the ${anchorEnv} trust store.`}
              />
            ) : (
              <div className="space-y-2">
                {anchors.map((a) => (
                  <div
                    key={a.entry_id}
                    className="p-3 border border-line rounded flex items-center justify-between bg-surface"
                  >
                    <div>
                      <div className="font-semibold text-xs text-ink">{a.subject_dn}</div>
                      <div className="text-2xs text-ink-3">
                        Added by {a.added_by} on {fmtDateTime(a.added_at)} • Store Version: v{a.version}
                      </div>
                    </div>
                    <Digest value={a.fingerprint_sha256} head={8} tail={6} />
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {activeTab === "incidents" && (
        <div className="space-y-4">
          <Callout tone="warning" title="Key Compromise & Emergency Recovery Playbook">
            Raising a security incident immediately marks the affected cryptographic key as{" "}
            <span className="font-bold text-mismatch-fg">COMPROMISED</span>, permanently disabling its signing capabilities
            across the system. Executing incident recovery automatically generates a clean emergency replacement key and
            closes the incident audit trail.
          </Callout>

          <Panel title="Security Incidents & Compromise Audit Trail">
            {incidents.length === 0 ? (
              <EmptyState
                title="No Security Incidents"
                description="Zero cryptographic compromise events on record. All keys operating in nominal state."
              />
            ) : (
              <div className="space-y-3">
                {incidents.map((inc) => (
                  <div
                    key={inc.id}
                    className="p-3 border border-line rounded space-y-2 bg-surface"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <StatusBadge tone={inc.severity === "CRITICAL" ? "mismatch" : "manual"}>
                          {inc.severity}
                        </StatusBadge>
                        <span className="font-semibold text-xs text-ink">{inc.incident_type}</span>
                        <span className="text-2xs text-ink-3">ID: {inc.id.slice(0, 8)}...</span>
                      </div>
                      <StatusBadge tone={inc.status === "RESOLVED" ? "verified" : "mismatch"}>
                        {inc.status}
                      </StatusBadge>
                    </div>
                    <p className="text-xs text-ink-2">{inc.description}</p>
                    <div className="text-2xs text-ink-3">
                      Affected Key: <span className="font-mono text-ink">{inc.affected_key_id || "None"}</span> •
                      Reported by {inc.reported_by} at {fmtDateTime(inc.reported_at)}
                    </div>
                    {inc.status === "OPEN" && (
                      <div className="pt-2 flex justify-end">
                        <Button
                          size="sm"
                          variant="primary"
                          onClick={() => recoverMutation.mutate(inc.id)}
                          disabled={recoverMutation.isPending}
                        >
                          <ShieldCheck className="size-3 mr-1" /> Execute Emergency Recovery
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {/* Rotate Key Dialog */}
      {rotateKeyTarget && (
        <Dialog
          open={!!rotateKeyTarget}
          onClose={() => setRotateKeyTarget(null)}
          title={`Rotate Key: ${rotateKeyTarget.key_id}`}
        >
          <div className="space-y-4">
            <p className="text-xs text-ink-2">
              Rotating key <span className="font-mono font-bold">{rotateKeyTarget.key_id}</span> will generate version{" "}
              <span className="font-bold">v{rotateKeyTarget.version + 1}</span>. The current key will be retired but retained
              for historical signature verification.
            </p>
            <div>
              <label className="text-xs font-medium text-ink-2 block mb-1">Rotation Reason:</label>
              <input
                type="text"
                value={rotateReason}
                onChange={(e) => setRotateReason(e.target.value)}
                className="w-full text-xs p-2 rounded border border-line bg-surface"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setRotateKeyTarget(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                disabled={rotateMutation.isPending}
                onClick={() =>
                  rotateMutation.mutate({ keyId: rotateKeyTarget.key_id, reason: rotateReason })
                }
              >
                Confirm Rotation
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {/* Revoke Key Dialog */}
      {revokeKeyTarget && (
        <Dialog
          open={!!revokeKeyTarget}
          onClose={() => setRevokeKeyTarget(null)}
          title={`Revoke Key: ${revokeKeyTarget.key_id}`}
        >
          <div className="space-y-4">
            <p className="text-xs text-ink-2">
              Revoking key <span className="font-mono font-bold">{revokeKeyTarget.key_id}</span> is an irreversible security
              action. Revoked keys cannot be used to sign any further data.
            </p>
            <div>
              <label className="text-xs font-medium text-ink-2 block mb-1">Revocation Reason:</label>
              <input
                type="text"
                value={revokeReason}
                placeholder="e.g. Deprecated or decommissioned"
                onChange={(e) => setRevokeReason(e.target.value)}
                className="w-full text-xs p-2 rounded border border-line bg-surface"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setRevokeKeyTarget(null)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={!revokeReason.trim() || revokeMutation.isPending}
                onClick={() =>
                  revokeMutation.mutate({ keyId: revokeKeyTarget.key_id, reason: revokeReason })
                }
              >
                Confirm Revocation
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {/* Raise Incident Dialog */}
      {incidentDialogOpen && (
        <Dialog
          open={incidentDialogOpen}
          onClose={() => setIncidentDialogOpen(false)}
          title="Raise Cryptographic Security Incident"
        >
          <div className="space-y-4">
            <p className="text-xs text-ink-2">
              Reporting a key compromise will immediately isolate and suspend the selected key, preventing any further
              cryptographic operations.
            </p>
            <div>
              <label className="text-xs font-medium text-ink-2 block mb-1">Affected Key:</label>
              <select
                value={incidentKeyId}
                onChange={(e) => setIncidentKeyId(e.target.value)}
                className="w-full text-xs p-2 rounded border border-line bg-surface"
              >
                {keys.map((k) => (
                  <option key={k.id} value={k.key_id}>
                    {k.key_id} ({k.status})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-ink-2 block mb-1">Incident Description:</label>
              <textarea
                value={incidentDesc}
                onChange={(e) => setIncidentDesc(e.target.value)}
                placeholder="Describe nature of compromise or suspected exposure..."
                rows={3}
                className="w-full text-xs p-2 rounded border border-line bg-surface"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setIncidentDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={!incidentDesc.trim() || raiseIncidentMutation.isPending}
                onClick={() =>
                  raiseIncidentMutation.mutate({ keyId: incidentKeyId, desc: incidentDesc })
                }
              >
                Suspend Key & Raise Incident
              </Button>
            </div>
          </div>
        </Dialog>
      )}
    </Page>
  );
}
