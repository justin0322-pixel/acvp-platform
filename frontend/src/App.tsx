import { useState } from "react";
import { backendLabel, idFromUrl } from "./api/client";
import type { SessionObject } from "./api/types";
import { Login } from "./steps/Login";
import { Configure } from "./steps/Configure";
import { Vectors } from "./steps/Vectors";
import { Submit } from "./steps/Submit";
import { Results } from "./steps/Results";
import { Certify } from "./steps/Certify";

const STEPS = [
  { key: "login", label: "Authenticate", hint: "Obtain a JWT" },
  { key: "configure", label: "Create test session", hint: "Register an algorithm" },
  { key: "vectors", label: "Retrieve vectors", hint: "Download the exam" },
  { key: "submit", label: "Submit answers", hint: "Upload responses" },
  { key: "results", label: "Results", hint: "Per-set disposition" },
  { key: "certify", label: "Certify", hint: "Request validation" },
];

function StatStrip({ loginToken, session }: { loginToken: string | null; session: SessionObject | null }) {
  return (
    <div className="statstrip">
      <div className={`stat ${loginToken ? "" : ""}`}>
        <div className="lab">Authentication</div>
        <div className="val sm">{loginToken ? "Signed in" : "Signed out"}</div>
        <div className="meta">{loginToken ? "JWT · HS256" : "Sign in to begin"}</div>
      </div>
      <div className="stat accent">
        <div className="lab">Test session</div>
        <div className="val">{session ? `#${idFromUrl(session.url)}` : "—"}</div>
        <div className="meta">{session ? `created ${session.createdOn.slice(0, 10)}` : "not created"}</div>
      </div>
      <div className="stat">
        <div className="lab">Session type</div>
        <div className="val sm">{session ? (session.isSample ? "Sample" : "Production") : "—"}</div>
        <div className="meta">{session ? (session.isSample ? "answer key available" : "certifiable") : "—"}</div>
      </div>
      <div className="stat">
        <div className="lab">Vector sets</div>
        <div className="val">{session ? session.vectorSetUrls.length : "—"}</div>
        <div className="meta">{session ? "generated per mode" : "—"}</div>
      </div>
    </div>
  );
}

export default function App() {
  const [step, setStep] = useState(0);
  const [loginToken, setLoginToken] = useState<string | null>(null);
  const [session, setSession] = useState<SessionObject | null>(null);

  const unlocked = (i: number) => (i === 0 ? true : i === 1 ? !!loginToken : !!session);
  const done = (i: number) => (i === 0 ? !!loginToken : i === 1 ? !!session : false);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">A</div>
          <div>
            <h1>ACVP Validation Console</h1>
            <div className="sub">Post-quantum crypto · FIPS 203 (ML-KEM) & FIPS 204 (ML-DSA)</div>
          </div>
        </div>
        <div className="spacer" />
        {session ? (
          <span className="session-tag">● session #{idFromUrl(session.url)} · token active</span>
        ) : (
          <span className="pill-backend">{backendLabel}</span>
        )}
      </header>

      <div className="shell">
        <nav className="rail">
          <div className="rail-title">Workflow</div>
          <ol className="steps">
            {STEPS.map((s, i) => (
              <li
                key={s.key}
                className={`step ${step === i ? "active" : ""} ${done(i) ? "done" : ""} ${unlocked(i) ? "" : "locked"}`}
                onClick={() => unlocked(i) && setStep(i)}
              >
                <span className="dot">{done(i) ? "✓" : i + 1}</span>
                <div>
                  <div className="s-label">{s.label}</div>
                  <div className="s-hint">{s.hint}</div>
                </div>
              </li>
            ))}
          </ol>
        </nav>

        <main className="content">
          <StatStrip loginToken={loginToken} session={session} />

          {step === 0 && (
            <Login loginToken={loginToken} onAuthed={(t) => { setLoginToken(t); setStep(1); }} />
          )}
          {step === 1 && loginToken && (
            <Configure loginToken={loginToken} existing={session}
              onCreated={(s) => { setSession(s); setStep(2); }} />
          )}
          {step === 2 && session && <Vectors session={session} />}
          {step === 3 && session && <Submit session={session} onNext={() => setStep(4)} />}
          {step === 4 && session && <Results session={session} onNext={() => setStep(5)} />}
          {step === 5 && session && loginToken && <Certify session={session} loginToken={loginToken} />}
        </main>
      </div>
    </div>
  );
}
