import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { createSession, idFromUrl } from "../api/client";
import { FAMILIES, buildCapability } from "../lib/catalog";
import { Button, Field, StepHead, Notice, Json } from "../ui";
import type { SessionObject } from "../api/types";

export function Configure({ loginToken, existing, history = [], onLoadSession, onCreated }: {
  loginToken: string;
  existing: SessionObject | null;
  history?: SessionObject[];
  onLoadSession: (s: SessionObject) => void;
  onCreated: (s: SessionObject) => void;
}) {
  const [famId, setFamId] = useState(FAMILIES[0].id);
  const fam = FAMILIES.find((f) => f.id === famId)!;
  const [modes, setModes] = useState<string[]>([fam.modes[0]]);
  const [params, setParams] = useState<string[]>([fam.paramSets[0]]);
  const [isSample, setIsSample] = useState(true);

  const pickFamily = (id: string) => {
    const f = FAMILIES.find((x) => x.id === id)!;
    setFamId(id); setModes([f.modes[0]]); setParams([f.paramSets[0]]);
  };
  const toggle = (arr: string[], set: (v: string[]) => void, v: string) =>
    set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const m = useMutation({
    mutationFn: () => {
      const algorithms = modes.map((mode) => buildCapability(fam.algorithm, mode, fam.id, params));
      return createSession(loginToken, algorithms, isSample);
    },
    onSuccess: onCreated,
  });

  const canCreate = modes.length > 0 && params.length > 0;

  return (
    <div>
      <StepHead eyebrow="Step 2" title="Create a test session">
        Declare which algorithm, modes and parameter sets to test. The server generates a vector
        set per mode and returns a session-specific access token.
      </StepHead>

      <div className="panels-wide">
      <div className="card">
        <div className="card-h"><div><h2>Registration</h2><div className="desc">Declare capabilities</div></div></div>
        <div className="card-b stack">
          <Field label="FIPS family">
            <select className="input" value={famId} onChange={(e) => pickFamily(e.target.value)}>
              {FAMILIES.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </Field>

          <Field label="Modes" hint="One vector set is created per selected mode">
            <div className="chips">
              {fam.modes.map((mode) => (
                <button key={mode} type="button"
                  className={`chip ${modes.includes(mode) ? "on" : ""}`}
                  onClick={() => toggle(modes, setModes, mode)}>{mode}</button>
              ))}
            </div>
          </Field>

          <Field label="Parameter sets">
            <div className="chips">
              {fam.paramSets.map((p) => (
                <button key={p} type="button"
                  className={`chip ${params.includes(p) ? "on" : ""}`}
                  onClick={() => toggle(params, setParams, p)}>{p}</button>
              ))}
            </div>
          </Field>

          <Field label="Session type" hint="Sample sessions can download the expected answer key; they are not certifiable">
            <div className="seg">
              <button className={isSample ? "on" : ""} onClick={() => setIsSample(true)}>Sample</button>
              <button className={!isSample ? "on" : ""} onClick={() => setIsSample(false)}>Production</button>
            </div>
          </Field>

          {m.isError && <Notice kind="err">Could not create session — {(m.error as Error).message}</Notice>}

          <div className="btn-row">
            <Button loading={m.isPending} disabled={!canCreate} onClick={() => m.mutate()}>
              {existing ? "Create another session" : "Create test session"}
            </Button>
          </div>
        </div>
      </div>

      {existing ? (
        <div className="card">
          <div className="card-h">
            <div>
              <h2>Session #{idFromUrl(existing.url)} created</h2>
              <div className="desc">Its access token is now used for every session-scoped call.</div>
            </div>
            <div style={{ marginLeft: "auto" }}>
              <span className={`badge ${existing.isSample ? "info" : "muted"}`}>
                {existing.isSample ? "sample" : "production"}
              </span>
            </div>
          </div>
          <div className="card-b stack">
            <dl className="kvs">
              <dt>createdOn</dt><dd>{existing.createdOn}</dd>
              <dt>expiresOn</dt><dd>{existing.expiresOn}</dd>
              <dt>vectorSets</dt><dd>{existing.vectorSetUrls.length}</dd>
              <dt>accessToken</dt><dd className="truncate">{existing.accessToken.slice(0, 42)}…</dd>
            </dl>
            <Json value={existing} />
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card-h"><div><h2>Session details</h2></div></div>
          <div className="card-b">
            <div className="muted-text">
              Configure the registration on the left and create a session. Its object — including
              the per-session access token and vector-set URLs — will appear here.
            </div>
          </div>
        </div>
      )}

      {history.length > 0 && (
        <div className="card">
          <div className="card-h">
            <div>
              <h2>Session History</h2>
              <div className="desc">Created in the current tab session</div>
            </div>
          </div>
          <div className="card-b stack" style={{ maxHeight: "320px", overflowY: "auto" }}>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {history.map((h) => {
                const sId = idFromUrl(h.url);
                const isCurrent = existing && idFromUrl(existing.url) === sId;
                return (
                  <li key={h.url} style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 0",
                    borderBottom: "1px solid #2d3047"
                  }}>
                    <div>
                      <span className="mono" style={{ fontWeight: "bold", color: "#e1e3f0" }}>#{sId}</span>
                      <span className="badge muted" style={{ marginLeft: 8 }}>
                        {h.isSample ? "sample" : "production"}
                      </span>
                      <div style={{ fontSize: "11px", color: "#6c729c", marginTop: 2 }}>
                        Created: {h.createdOn.slice(11, 19)}
                      </div>
                    </div>
                    <div>
                      {isCurrent ? (
                        <span className="badge ok">active</span>
                      ) : (
                        <Button variant="soft" onClick={() => onLoadSession(h)} style={{ padding: "4px 8px", fontSize: "12px", minHeight: 0 }}>
                          Resume
                        </Button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
