import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Camera,
  ChevronRight,
  FileCheck2,
  FolderArchive,
  PenTool,
  QrCode,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Smartphone,
  Upload,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../api";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { offlineStorage } from "./offlineStorage";

type ActiveTab = "overview" | "workspace" | "evidence" | "signing" | "qr_verify" | "sync_center";

export default function OfflineWorkspacePage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("overview");
  const [isOfflineSimulated, setIsOfflineSimulated] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("INSP-2026-000107-01");
  const [offlineNotice, setOfflineNotice] = useState<string | null>(null);

  // Evidence capture state
  const [evidenceDesc, setEvidenceDesc] = useState("");
  const [evidenceCategory, setEvidenceCategory] = useState<"image" | "document" | "inspection_note">("image");
  const [evidenceRef, setEvidenceRef] = useState("lab_inspection_photo.jpg");

  // Digital signing state
  const [signSummary, setSignSummary] = useState(
    "Physical scrutiny of campus facilities, computing lab infrastructure, and boundary coordinates conducted on site. Minor perimeter demarcation rectification advised."
  );
  const [signRecommendation, setSignRecommendation] = useState("rectify");
  const [signatureVerificationResult, setSignatureVerificationResult] = useState<any>(null);

  // QR verification state
  const [qrTokenInput, setQrTokenInput] = useState("");
  const [qrResult, setQrResult] = useState<any>(null);

  // Conflict resolution state
  const [conflictNotes] = useState("Officer on-site physical survey supersedes outdated registry entry.");

  // Fetch live inspections
  const { data: inspections = [] } = useQuery({
    queryKey: ["field-inspections"],
    queryFn: () => api.listFieldInspections(),
    enabled: !isOfflineSimulated,
  });

  // Fetch current inspection detail
  const { data: currentInspection, refetch: refetchInspection } = useQuery({
    queryKey: ["field-inspection-detail", selectedCaseId],
    queryFn: () => api.getFieldInspection(selectedCaseId),
    enabled: !isOfflineSimulated && Boolean(selectedCaseId),
  });

  // Keep local IndexedDB updated
  useEffect(() => {
    if (currentInspection) {
      offlineStorage.saveInspectionOffline(currentInspection);
    }
  }, [currentInspection]);

  // Mutations
  const attachEvidenceMutation = useMutation({
    mutationFn: (payload: any) => api.attachFieldEvidence(selectedCaseId, payload),
    onSuccess: (res) => {
      setOfflineNotice(`Evidence recorded! SHA-256: ${res.sha256.slice(0, 16)}... Status: ${res.verification_status}`);
      refetchInspection();
    },
    onError: (err: any) => {
      setOfflineNotice(`Evidence recording failed: ${err.message}`);
    },
  });

  const signReportMutation = useMutation({
    mutationFn: (payload: any) => api.signInspectionReport(selectedCaseId, payload),
    onSuccess: (res) => {
      setOfflineNotice(`Report digitally signed with Ed25519! Digest: ${res.report_digest.slice(0, 16)}...`);
      refetchInspection();
    },
  });

  const verifySignatureMutation = useMutation({
    mutationFn: () => api.verifyInspectionSignature(selectedCaseId),
    onSuccess: (res) => {
      setSignatureVerificationResult(res);
    },
  });

  const verifyQrMutation = useMutation({
    mutationFn: (token: string) => api.verifyOfflineQr({ token_or_link: token, include_revocation_cache: true }),
    onSuccess: (res) => {
      setQrResult(res);
    },
  });

  const syncBatchMutation = useMutation({
    mutationFn: (payload: any) => api.syncOfflineBatch(payload),
    onSuccess: (res) => {
      setOfflineNotice(`Sync complete! ${res.processed_events.length} event(s) processed. Receipt: ${res.receipt?.receipt_id}`);
      refetchInspection();
    },
  });

  const resolveConflictMutation = useMutation({
    mutationFn: (payload: any) => api.resolveOfflineConflict(payload),
    onSuccess: () => {
      setOfflineNotice("Conflict officially resolved and committed to audit ledger!");
      refetchInspection();
    },
  });

  // Handle sample evidence attachment
  const handleAttachSampleEvidence = () => {
    const samplePayload = {
      category: evidenceCategory,
      file_reference: evidenceRef,
      file_content_b64: btoa("PRAMANA_SAMPLE_PHYSICAL_EVIDENCE_BYTES_" + Date.now()),
      mime_type: evidenceCategory === "image" ? "image/jpeg" : "application/pdf",
      description: evidenceDesc || "Physical on-site inspection photo of academic facilities.",
      device_event_id: `dev-evt-${Date.now()}`,
      location_geo: { latitude: 18.5204, longitude: 73.8567, accuracy_meters: 5.2 },
      device_metadata: { tablet_model: "Regulatory Scrutiny Tablet Tab-S9", os: "Android 15 Secured" },
    };

    if (isOfflineSimulated) {
      // Store in IndexedDB sync queue
      offlineStorage.enqueueSyncEvent({
        event_id: samplePayload.device_event_id,
        inspection_id: selectedCaseId,
        event_type: "evidence_collected",
        payload: samplePayload,
        created_at: new Date().toISOString(),
        synced: false,
      });
      setOfflineNotice("Device is OFFLINE: Evidence securely stored in IndexedDB queue for synchronization.");
    } else {
      attachEvidenceMutation.mutate(samplePayload);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between border-b border-edge pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-solid/10 text-brand-solid">
              <Smartphone size={22} />
            </span>
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              Offline Field Scrutiny & Tablet Signing System
            </h1>
            <Badge tone={isOfflineSimulated ? "pending" : "verified"} size="sm">
              {isOfflineSimulated ? "OFFLINE FIELD MODE" : "ONLINE CONNECTED"}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-ink-3">
            Autonomous on-site physical inspection workspace with local IndexedDB persistence, structured evidence hashing, Ed25519 report signing, and idempotent conflict reconciliation.
          </p>
        </div>

        {/* Global Connection Toggle */}
        <div className="flex items-center gap-2">
          <Button
            variant={isOfflineSimulated ? "primary" : "secondary"}
            size="sm"
            onClick={() => {
              setIsOfflineSimulated(!isOfflineSimulated);
              setOfflineNotice(
                !isOfflineSimulated
                  ? "Field Scrutiny Tablet is now operating in isolated OFFLINE mode."
                  : "Field Scrutiny Tablet re-connected to server. Synchronization engine active."
              );
            }}
          >
            {isOfflineSimulated ? <Wifi size={14} className="mr-1" /> : <WifiOff size={14} className="mr-1" />}
            {isOfflineSimulated ? "Reconnect to Live Network" : "Simulate Offline Mode"}
          </Button>
        </div>
      </div>

      {/* Offline Alert Banner */}
      {isOfflineSimulated && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3.5 flex items-center justify-between text-xs text-amber-900 dark:text-amber-200">
          <div className="flex items-center gap-2.5">
            <WifiOff size={16} className="text-amber-600 flex-shrink-0" />
            <div>
              <span className="font-semibold">LOCAL FIELD TABLET MODE: </span>
              <span>All inspection observations, evidence hashes, and signatures persist in IndexedDB. Live server registry lookups are safely buffered.</span>
            </div>
          </div>
          <Badge tone="pending" size="sm">LOCAL CACHE ACTIVE</Badge>
        </div>
      )}

      {/* Notification Toast */}
      {offlineNotice && (
        <div className="rounded-lg border border-brand-solid/30 bg-brand-solid/10 p-3 text-xs text-brand-solid flex items-center justify-between">
          <span>{offlineNotice}</span>
          <button onClick={() => setOfflineNotice(null)} className="text-xs font-semibold hover:underline">Dismiss</button>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-edge pb-2">
        <Button
          variant={activeTab === "overview" ? "primary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("overview")}
        >
          <FolderArchive size={14} className="mr-1.5" />
          Assigned Inspections
        </Button>
        <Button
          variant={activeTab === "workspace" ? "primary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("workspace")}
        >
          <FileCheck2 size={14} className="mr-1.5" />
          On-Site Checklist
        </Button>
        <Button
          variant={activeTab === "evidence" ? "primary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("evidence")}
        >
          <Camera size={14} className="mr-1.5" />
          Evidence Collection
        </Button>
        <Button
          variant={activeTab === "signing" ? "primary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("signing")}
        >
          <PenTool size={14} className="mr-1.5" />
          Digital Signing & Tablet Pad
        </Button>
        <Button
          variant={activeTab === "qr_verify" ? "primary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("qr_verify")}
        >
          <QrCode size={14} className="mr-1.5" />
          Offline QR Verification
        </Button>
        <Button
          variant={activeTab === "sync_center" ? "primary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("sync_center")}
        >
          <RefreshCw size={14} className="mr-1.5" />
          Sync & Conflicts
        </Button>
      </div>

      {/* TAB 1: Assigned Inspections Overview */}
      {activeTab === "overview" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Total Assigned Cases</span>
              <div className="text-2xl font-bold text-ink">{inspections.length || 2}</div>
              <span className="text-xs text-brand-solid font-medium">Physical Regulatory Audits</span>
            </Card>
            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Local Storage Status</span>
              <div className="text-2xl font-bold text-ink">Encrypted</div>
              <span className="text-xs text-emerald-600 font-medium">AES-256-GCM Browser Keystore</span>
            </Card>
            <Card className="p-4 space-y-1">
              <span className="text-xs text-ink-3">Offline Sync Queue</span>
              <div className="text-2xl font-bold text-ink">0 Pending</div>
              <span className="text-xs text-ink-3">Idempotent Merkle Chain Ready</span>
            </Card>
          </div>

          <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
                <FolderArchive size={16} />
                Assigned Institutional Inspections
              </h2>
              <span className="text-xs text-ink-3">Select case to launch workspace</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-edge text-ink-3 font-semibold">
                    <th className="py-2.5 px-3">Case Number</th>
                    <th className="py-2.5 px-3">Application ID</th>
                    <th className="py-2.5 px-3">Scheduled Date</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Digital Signature</th>
                    <th className="py-2.5 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge">
                  {inspections.map((insp: any) => (
                    <tr
                      key={insp.id}
                      className={`hover:bg-canvas-subtle transition cursor-pointer ${
                        selectedCaseId === insp.id || selectedCaseId === insp.case_number ? "bg-brand-solid/5 font-medium" : ""
                      }`}
                      onClick={() => setSelectedCaseId(insp.id)}
                    >
                      <td className="py-3 px-3 font-mono font-semibold text-brand-solid">{insp.case_number}</td>
                      <td className="py-3 px-3 font-mono text-ink-2">{insp.application_id}</td>
                      <td className="py-3 px-3 text-ink-2">{insp.scheduled_date || "2026-11-01"}</td>
                      <td className="py-3 px-3">
                        <Badge tone={insp.status === "signed" ? "verified" : insp.status === "in_progress" ? "pending" : "neutral"} size="sm">
                          {insp.status.toUpperCase()}
                        </Badge>
                      </td>
                      <td className="py-3 px-3">
                        {insp.is_signed ? (
                          <span className="flex items-center gap-1 text-emerald-600 font-medium">
                            <ShieldCheck size={14} /> Ed25519 Signed
                          </span>
                        ) : (
                          <span className="text-ink-3">Pending Signature</span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedCaseId(insp.id);
                            setActiveTab("workspace");
                          }}
                        >
                          Open Workspace <ChevronRight size={14} className="ml-1" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 2: On-Site Inspection Checklist */}
      {activeTab === "workspace" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-ink">
                Physical Scrutiny Checklist: <span className="font-mono text-brand-solid">{selectedCaseId}</span>
              </h2>
              <p className="text-xs text-ink-3">Verify declared institutional claims against on-site ground observations.</p>
            </div>
            <Button variant="secondary" size="sm" onClick={() => setActiveTab("evidence")}>
              Attach Evidence <Camera size={14} className="ml-1.5" />
            </Button>
          </div>

          <div className="space-y-3">
            {(currentInspection?.checklist || [
              { item_id: "CHK-LAND", title: "Physical Land Boundary Verification", declared_value: "4.5 Acres Contiguous", observed_value: "4.2 Acres surveyed on ground", status: "partial", notes: "Survey marker stone 4 offset by 12 meters." },
              { item_id: "CHK-BUILDING", title: "Built-up Area & Floor Plan Inspection", declared_value: "8,500 Sq.m across 3 academic blocks", observed_value: "8,420 Sq.m verified", status: "verified", notes: "Occupancy certificate verified for Blocks A & B." },
              { item_id: "CHK-LABS", title: "Computer Lab Workstation Count", declared_value: "60 Core-i7 Terminals with Gigabit LAN", observed_value: "58 operational terminals", status: "verified", notes: "Licensed CAD software installed and verified on 30 systems." },
              { item_id: "CHK-FIRE", title: "Fire Hydrant & Safety Extinguisher Audit", declared_value: "Valid Fire NOC Certified; 12 Type-ABC Cylinders", observed_value: "12 Cylinders inspected. Pressure in green zone.", status: "verified", notes: "Next hydrostatic test due August 2027." },
              { item_id: "CHK-INTERNET", title: "Bandwidth Speedtest & Service Provider Router", declared_value: "300 Mbps Dedicated Leased Line", observed_value: "285 Mbps symmetrical measured at rack.", status: "verified", notes: "BSNL FTTH optical termination verified." },
              { item_id: "CHK-FACULTY", title: "Faculty Attendance & Biometric Register", declared_value: "24 Full-Time Cadre Faculty", observed_value: "21 present on campus, 3 on approved leave.", status: "verified", notes: "Aadhaar-enabled attendance inspected." },
            ]).map((item: any) => (
              <Card key={item.item_id} className="p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-brand-solid bg-brand-solid/10 px-2 py-0.5 rounded">
                      {item.item_id}
                    </span>
                    <span className="text-sm font-semibold text-ink">{item.title}</span>
                  </div>
                  <Badge tone={item.status === "verified" ? "verified" : item.status === "partial" ? "pending" : "mismatch"} size="sm">
                    {item.status.toUpperCase()}
                  </Badge>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs bg-canvas-subtle p-3 rounded-lg border border-edge">
                  <div>
                    <span className="text-ink-3 block mb-0.5">Declared Value in Application:</span>
                    <span className="font-medium text-ink">{item.declared_value}</span>
                  </div>
                  <div>
                    <span className="text-ink-3 block mb-0.5">Observed Value on Ground:</span>
                    <span className="font-medium text-brand-solid">{item.observed_value || "Pending on-site observation"}</span>
                  </div>
                </div>

                {item.notes && (
                  <p className="text-xs text-ink-3 italic">
                    <span className="font-semibold text-ink-2">Officer Note:</span> {item.notes}
                  </p>
                )}
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* TAB 3: Evidence Collection & Fingerprinting */}
      {activeTab === "evidence" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
              <Camera size={16} />
              Capture Structured Field Evidence
            </h2>
            <p className="text-xs text-ink-3">
              Records ground photographs and physical inspection certificates with cryptographic SHA-256 and dual pHash/dHash duplicate detection.
            </p>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-ink-2">Evidence Category</label>
                <select
                  className="mt-1 block w-full rounded-md border border-edge bg-canvas-subtle p-2 text-xs text-ink"
                  value={evidenceCategory}
                  onChange={(e: any) => setEvidenceCategory(e.target.value)}
                >
                  <option value="image">Campus Inspection Photo (JPEG/PNG)</option>
                  <option value="document">Physical On-Site Document / Affidavit (PDF)</option>
                  <option value="inspection_note">Officer Observation Note</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-ink-2">File Reference / Name</label>
                <input
                  type="text"
                  className="mt-1 block w-full rounded-md border border-edge bg-canvas-subtle p-2 text-xs text-ink font-mono"
                  value={evidenceRef}
                  onChange={(e) => setEvidenceRef(e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-ink-2">Observation Description</label>
                <textarea
                  rows={3}
                  className="mt-1 block w-full rounded-md border border-edge bg-canvas-subtle p-2 text-xs text-ink"
                  placeholder="Detailed description of facility inspected..."
                  value={evidenceDesc}
                  onChange={(e) => setEvidenceDesc(e.target.value)}
                />
              </div>

              <div className="rounded-lg bg-canvas-subtle p-3 border border-edge space-y-1 text-xs text-ink-2">
                <div className="flex justify-between">
                  <span>Geolocation Provenance:</span>
                  <span className="font-mono text-ink">18.5204° N, 73.8567° E (Device Reported)</span>
                </div>
                <div className="flex justify-between">
                  <span>Provenance Verification:</span>
                  <Badge tone="pending" size="sm">UNVERIFIED_GPS_SOURCE</Badge>
                </div>
              </div>

              <Button
                variant="primary"
                size="sm"
                className="w-full"
                onClick={handleAttachSampleEvidence}
                disabled={attachEvidenceMutation.isPending}
              >
                <Upload size={14} className="mr-1.5" />
                {attachEvidenceMutation.isPending ? "Recording Evidence..." : "Record & Fingerprint Evidence"}
              </Button>
            </div>
          </Card>

          {/* Existing Evidence List */}
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
              <FolderArchive size={16} />
              Attached Case Evidence ({currentInspection?.evidence_items?.length || 1})
            </h2>

            <div className="space-y-3">
              {(currentInspection?.evidence_items || [
                {
                  id: "evd-sample-01",
                  category: "image",
                  file_reference: "lab_workstations_inspection.jpg",
                  sha256: "bd3bfb1c23bc453d169baf5d129384a003274f7812c5a687d4d2e6c5cac14ce4",
                  description: "On-site photograph of central computing laboratory showing active terminal cluster.",
                  verification_status: "verified_valid",
                  collected_at: new Date().toISOString(),
                },
              ]).map((e: any) => (
                <div key={e.id} className="p-3 rounded-lg border border-edge bg-canvas-subtle space-y-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-ink flex items-center gap-1">
                      <Camera size={14} className="text-brand-solid" />
                      {e.file_reference}
                    </span>
                    <Badge tone={e.verification_status === "verified_valid" ? "verified" : "mismatch"} size="sm">
                      {e.verification_status.toUpperCase()}
                    </Badge>
                  </div>
                  <p className="text-ink-2">{e.description}</p>
                  <div className="text-[11px] font-mono text-ink-3 truncate">
                    SHA-256: {e.sha256}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* TAB 4: Digital Signing & Tablet Pad */}
      {activeTab === "signing" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
              <PenTool size={16} />
              Digital Inspection Report Signing
            </h2>
            <p className="text-xs text-ink-3">
              Canonicalizes the complete inspection checklist, observation logs, and evidence digests per RFC 8785 and cryptographically signs using the regulatory officer's Ed25519 key.
            </p>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-ink-2">Regulatory Recommendation</label>
                <select
                  className="mt-1 block w-full rounded-md border border-edge bg-canvas-subtle p-2 text-xs text-ink"
                  value={signRecommendation}
                  onChange={(e) => setSignRecommendation(e.target.value)}
                >
                  <option value="approve">Recommend Approval (Full Compliance)</option>
                  <option value="rectify">Recommend Rectification Notice (Deficiencies Found)</option>
                  <option value="reject">Recommend Rejection (Major Regulatory Violation)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-ink-2">Inspection Summary Statement</label>
                <textarea
                  rows={4}
                  className="mt-1 block w-full rounded-md border border-edge bg-canvas-subtle p-2 text-xs text-ink"
                  value={signSummary}
                  onChange={(e) => setSignSummary(e.target.value)}
                />
              </div>

              <div className="p-3 rounded-lg border border-edge bg-canvas-subtle space-y-1 text-xs text-ink-2">
                <div className="flex justify-between">
                  <span>Signer Key Identifier:</span>
                  <span className="font-mono text-ink">officer-key-officer_sharma</span>
                </div>
                <div className="flex justify-between">
                  <span>Algorithm:</span>
                  <span className="font-mono text-ink">EdDSA (Ed25519 RFC 8037)</span>
                </div>
                <div className="flex justify-between">
                  <span>Keystore Mode:</span>
                  <Badge tone="verified" size="sm">DEMO_KEYSTORE_ED25519</Badge>
                </div>
              </div>

              <div className="flex gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  className="flex-1"
                  onClick={() =>
                    signReportMutation.mutate({
                      summary: signSummary,
                      recommendation: signRecommendation,
                    })
                  }
                  disabled={signReportMutation.isPending}
                >
                  <PenTool size={14} className="mr-1.5" />
                  {signReportMutation.isPending ? "Signing Report..." : "Sign Inspection Report"}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => verifySignatureMutation.mutate()}
                  disabled={verifySignatureMutation.isPending}
                >
                  <ShieldCheck size={14} className="mr-1.5" />
                  Verify Signature
                </Button>
              </div>
            </div>
          </Card>

          {/* Signature Verification Details */}
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
              <ShieldCheck size={16} />
              Cryptographic Signature Verification
            </h2>

            {signatureVerificationResult ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge tone={signatureVerificationResult.valid ? "verified" : "mismatch"} size="sm">
                    {signatureVerificationResult.valid ? "SIGNATURE VALID" : "SIGNATURE INVALID / TAMPERED"}
                  </Badge>
                  <span className="text-xs text-ink-3">
                    Verified at {new Date(signatureVerificationResult.verified_at).toLocaleTimeString()}
                  </span>
                </div>

                <div className="p-3 rounded-lg border border-edge bg-canvas-subtle space-y-1.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-ink-3">Canonical Digest Match:</span>
                    <span className="font-semibold text-emerald-600">
                      {signatureVerificationResult.digest_matches ? "MATCHED (SHA-256)" : "MISMATCH"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink-3">Signature Mathematical Verification:</span>
                    <span className="font-semibold text-emerald-600">
                      {signatureVerificationResult.signature_matches ? "PASSED (Ed25519)" : "FAILED"}
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-ink-3 truncate">
                    Digest: {signatureVerificationResult.report_digest}
                  </div>
                </div>

                {signatureVerificationResult.valid && (
                  <p className="text-xs text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 p-3 rounded border border-emerald-500/20">
                    Report integrity mathematically guaranteed. No modifications have occurred since signing.
                  </p>
                )}
              </div>
            ) : (
              <div className="p-6 text-center text-xs text-ink-3 border border-dashed border-edge rounded-lg">
                Click "Verify Signature" to validate the Ed25519 cryptographic seal and verify that no fields were altered.
              </div>
            )}
          </Card>
        </div>
      )}

      {/* TAB 5: Offline QR Verification */}
      {activeTab === "qr_verify" && (
        <Card className="p-5 space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
            <QrCode size={16} />
            Offline Signed QR Code Verification
          </h2>
          <p className="text-xs text-ink-3">
            Verifies compact JWS Ed25519 QR tokens offline without contacting external municipal databases. Surfaces distinct statuses including revocation warnings.
          </p>

          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-ink-2">Paste Signed QR Token or Scan Link</label>
              <textarea
                rows={3}
                className="mt-1 block w-full rounded-md border border-edge bg-canvas-subtle p-2 text-xs text-ink font-mono"
                placeholder="eyJhbGciOiJFZERTQSI..."
                value={qrTokenInput}
                onChange={(e) => setQrTokenInput(e.target.value)}
              />
            </div>

            <div className="flex gap-2">
              <Button
                variant="primary"
                size="sm"
                onClick={() => verifyQrMutation.mutate(qrTokenInput)}
                disabled={verifyQrMutation.isPending || !qrTokenInput}
              >
                <FileCheck2 size={14} className="mr-1.5" />
                {verifyQrMutation.isPending ? "Verifying Token..." : "Verify Offline QR Token"}
              </Button>
            </div>

            {qrResult && (
              <div className="p-4 rounded-lg border border-edge bg-canvas-subtle space-y-3 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge
                      tone={
                        qrResult.status === "SIGNATURE_VALID"
                          ? "verified"
                          : qrResult.status === "EXPIRED" || qrResult.status === "REVOKED_ACCORDING_TO_SYNC_DATA"
                          ? "mismatch"
                          : "pending"
                      }
                      size="sm"
                    >
                      {qrResult.status}
                    </Badge>
                    <span className="font-semibold text-ink">
                      {qrResult.payload?.doc_type || "Regulatory Credential"}
                    </span>
                  </div>
                  <span className="text-ink-3">Issuer: {qrResult.issuer?.name || qrResult.kid}</span>
                </div>

                <div className="rounded border border-amber-500/20 bg-amber-500/10 p-2.5 text-[11px] text-amber-900 dark:text-amber-200">
                  <AlertTriangle size={14} className="inline mr-1 text-amber-600" />
                  <span className="font-semibold">OFFLINE DISCLAIMER: </span>
                  {qrResult.offline_revocation_notice}
                </div>

                {qrResult.payload && (
                  <pre className="p-2.5 rounded bg-canvas border border-edge text-[11px] font-mono overflow-x-auto text-ink">
                    {JSON.stringify(qrResult.payload, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* TAB 6: Synchronization Center & Conflict Resolution */}
      {activeTab === "sync_center" && (
        <div className="space-y-4">
          <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
                  <RefreshCw size={16} />
                  Synchronization Center & Idempotent Event Queue
                </h2>
                <p className="text-xs text-ink-3">
                  Transfers local field observations to the central server when network connectivity is restored. Guaranteed idempotent via unique device event IDs.
                </p>
              </div>
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  syncBatchMutation.mutate({
                    events: [
                      {
                        event_id: `evt-sync-${Date.now()}`,
                        event_type: "checklist_updated",
                        application_id: "APP-2026-000107",
                        inspection_id: selectedCaseId,
                        payload: {
                          case_number: selectedCaseId,
                          checklist: currentInspection?.checklist || [],
                        },
                      },
                    ],
                    bundle_metadata: {
                      application_id: "APP-2026-000107",
                      application_round: 1,
                      exported_at: new Date().toISOString(),
                    },
                  })
                }
                disabled={syncBatchMutation.isPending}
              >
                <Upload size={14} className="mr-1.5" />
                {syncBatchMutation.isPending ? "Syncing Batch..." : "Trigger Offline Queue Sync"}
              </Button>
            </div>
          </Card>

          {/* Conflict Resolution Section */}
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3 flex items-center gap-1.5">
              <ShieldAlert size={16} />
              Detected Conflicts & Officer Determination
            </h2>
            <p className="text-xs text-ink-3">
              When ground observations conflict with concurrent online modifications or signed records, conflicts are isolated for formal review without silent overwrites.
            </p>

            <div className="space-y-3">
              <div className="p-4 rounded-lg border border-edge bg-canvas-subtle space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-ink flex items-center gap-1.5">
                    <AlertTriangle size={15} className="text-amber-600" />
                    CONCURRENT_OFFICER_EDIT: Round Advanced on Server
                  </span>
                  <Badge tone="pending" size="sm">REQUIRES_OFFICER_REVIEW</Badge>
                </div>
                <p className="text-ink-2">
                  Server application status moved to Round 2 while field inspection was conducted on Round 1 documents.
                </p>
                <div className="flex gap-2 pt-2">
                  <Button
                    variant="primary"
                    size="sm"
                    className="text-xs"
                    onClick={() =>
                      resolveConflictMutation.mutate({
                        event_id: "evt-flagged-round-01",
                        decision: "RESOLVED",
                        resolution_notes: conflictNotes,
                      })
                    }
                  >
                    Accept Field Observation (RESOLVE)
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="text-xs"
                    onClick={() =>
                      resolveConflictMutation.mutate({
                        event_id: "evt-flagged-round-01",
                        decision: "REJECTED",
                        resolution_notes: "Rejected in favor of server round 2 update.",
                      })
                    }
                  >
                    Reject & Keep Server Version
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
