import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { certify, getRequest, getSessionResults, idFromUrl } from "../api/client";
import type { SessionObject, SessionResults, RequestObject } from "../api/types";
import { StepHead, Button, Field, Notice, Json } from "../ui";

const MODULES = [
  { url: "/acvp/v1/modules/1", name: "System.Security.Cryptography.MLKem (FIPS 203) - v1.0" },
  { url: "/acvp/v1/modules/2", name: "QuantumShield ML-DSA (.NET 10) - v2.1" },
  { url: "/acvp/v1/modules/3", name: "PostQuantum Crypto-Suite - v10.0" }
];

const OES = [
  { url: "/acvp/v1/oes/1", name: "Windows 11 (x64) AMD Ryzen 9" },
  { url: "/acvp/v1/oes/2", name: "Ubuntu 24.04 LTS (x86_64) Intel Xeon" },
  { url: "/acvp/v1/oes/3", name: "macOS Sequoia 15.0 (ARM64) Apple M3" }
];

export function Certify({ session, loginToken }: { session: SessionObject; loginToken: string }) {
  const id = idFromUrl(session.url);
  const [moduleUrl, setModuleUrl] = useState(MODULES[0].url);
  const [oeUrl, setOeUrl] = useState(OES[0].url);

  const summary = useQuery({
    queryKey: ["session-results", id],
    queryFn: () => getSessionResults(id, session.accessToken),
    refetchInterval: 2000,
  });
  const s = summary.data as SessionResults | undefined;
  const canCertify = !session.isSample && !!s?.passed;

  const certifyM = useMutation({
    mutationFn: () => certify(id, { moduleUrl, oeUrl }, session.accessToken),
  });
  const requestUrl = certifyM.data?.url;

  // The request resource is user-level → poll it with the login token.
  const req = useQuery({
    queryKey: ["request", requestUrl],
    enabled: !!requestUrl,
    queryFn: () => getRequest(requestUrl!, loginToken),
    refetchInterval: (query) => {
      const d = query.state.data as RequestObject | undefined;
      return d && (d.status === "processing" || d.status === "initial") ? 1200 : false;
    },
  });
  const validation = req.data?.status === "approved" ? req.data.approvedUrl : undefined;

  const handleExportMarkdown = () => {
    if (!validation) return;
    const md = `# ACVP Validation Certificate - Session #${id}

Generated At: ${new Date().toLocaleString()}
Session ID: #${id}
Module: ${MODULES.find((m) => m.url === moduleUrl)?.name ?? moduleUrl}
Operating Environment: ${OES.find((oe) => oe.url === oeUrl)?.name ?? oeUrl}
Status: ✅ APPROVED / CERTIFIED
Approved Resource URL: ${validation}
Request Tracker URL: ${requestUrl}

---
*Certified by ACVP Validation Console*`;
    
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `acvp-certificate-session-${id}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <StepHead eyebrow="Step 6" title="Certify the session">
        Submit the passed session for validation. The server checks the precondition (publishable &
        passed), then returns a request you poll until a validation certificate is issued.
      </StepHead>

      {session.isSample && (
        <Notice kind="info">This is a <b>sample</b> session — sample runs are not publishable, so certification is disabled. Create a Production session to certify.</Notice>
      )}

      <div className="panels-wide" style={{ marginTop: session.isSample ? 16 : 0 }}>
        <div className="card">
          <div className="card-h"><div><h2>Certification request</h2>
            <div className="desc">Bind the module & operating environment</div></div></div>
          <div className="card-b stack">
            <Field label="Cryptographic Module" hint={`Binds module at: ${moduleUrl}`}>
              <select className="input" value={moduleUrl} onChange={(e) => setModuleUrl(e.target.value)}>
                {MODULES.map((m) => (
                  <option key={m.url} value={m.url}>
                    {m.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Operating Environment" hint={`Binds environment at: ${oeUrl}`}>
              <select className="input" value={oeUrl} onChange={(e) => setOeUrl(e.target.value)}>
                {OES.map((oe) => (
                  <option key={oe.url} value={oe.url}>
                    {oe.name}
                  </option>
                ))}
              </select>
            </Field>

            {!session.isSample && !s?.passed && (
              <Notice kind="info">Waiting for the session to pass — complete the submit &amp; results steps first.</Notice>
            )}
            {certifyM.isError && <Notice kind="err">{(certifyM.error as Error).message}</Notice>}

            <div className="btn-row">
              <Button loading={certifyM.isPending} disabled={!canCertify} onClick={() => certifyM.mutate()}>
                Submit for validation
              </Button>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-h"><div><h2>Validation status</h2></div>
            <div style={{ marginLeft: "auto" }}>
              {validation ? <span className="badge ok">approved</span>
                : requestUrl ? <span className="badge info">processing</span>
                : <span className="badge muted">not started</span>}
            </div>
          </div>
          <div className="card-b stack">
            {!requestUrl && <div className="muted-text">Submit a certification request to see its progress here.</div>}
            {requestUrl && !validation && <div className="notice info"><span className="spin dark" />Polling request {requestUrl}…</div>}
            {validation && (
              <>
                <Notice kind="ok">Certified. Validation certificate issued.</Notice>
                <dl className="kvs" style={{ marginBottom: 12 }}>
                  <dt>request</dt><dd>{requestUrl}</dd>
                  <dt>approvedUrl</dt><dd>{validation}</dd>
                </dl>
                <div className="btn-row" style={{ marginTop: 8 }}>
                  <Button variant="soft" onClick={handleExportMarkdown} style={{ padding: "6px 12px", fontSize: "12px", minHeight: 0 }}>
                    Download Certificate Report
                  </Button>
                </div>
              </>
            )}
            {req.data && <Json value={req.data} />}
          </div>
        </div>
      </div>
    </div>
  );
}
