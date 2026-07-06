import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { certify, getRequest, getSessionResults, idFromUrl } from "../api/client";
import type { SessionObject, SessionResults, RequestObject } from "../api/types";
import { StepHead, Button, Field, Notice, Json } from "../ui";

export function Certify({ session, loginToken }: { session: SessionObject; loginToken: string }) {
  const id = idFromUrl(session.url);
  const [moduleUrl, setModuleUrl] = useState("/acvp/v1/modules/1");
  const [oeUrl, setOeUrl] = useState("/acvp/v1/oes/1");

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
            <Field label="Module URL"><input className="input" value={moduleUrl} onChange={(e) => setModuleUrl(e.target.value)} /></Field>
            <Field label="Operating environment URL"><input className="input" value={oeUrl} onChange={(e) => setOeUrl(e.target.value)} /></Field>

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
                <dl className="kvs">
                  <dt>request</dt><dd>{requestUrl}</dd>
                  <dt>approvedUrl</dt><dd>{validation}</dd>
                </dl>
              </>
            )}
            {req.data && <Json value={req.data} />}
          </div>
        </div>
      </div>
    </div>
  );
}
