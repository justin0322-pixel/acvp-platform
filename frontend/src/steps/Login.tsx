import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { login } from "../api/client";
import { Button, Field, StepHead, Notice } from "../ui";

export function Login({ loginToken, onAuthed }: {
  loginToken: string | null; onAuthed: (t: string) => void;
}) {
  const [password, setPassword] = useState("acvp-demo");
  const m = useMutation({
    mutationFn: () => login(password),
    onSuccess: (r) => onAuthed(r.accessToken),
  });

  return (
    <div>
      <StepHead eyebrow="Step 1" title="Authenticate">
        Sign in to receive a JWT (HS256). It authorizes login-level calls; each test session
        you create later issues its own token for session-scoped operations.
      </StepHead>

      <div className="panels-wide">
        <div className="card">
          <div className="card-h"><div><h2>Sign in</h2><div className="desc">Local demo server</div></div></div>
          <div className="card-b">
            <Field label="Server password" hint="Demo credential for the local backend">
              <input
                className="input" type="password" value={password} autoFocus
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && m.mutate()}
              />
            </Field>

            {m.isError && <Notice kind="err">Sign-in failed — {(m.error as Error).message}</Notice>}
            {loginToken && !m.isError && (
              <Notice kind="ok">Authenticated. Proceed to create a test session.</Notice>
            )}

            <div className="btn-row" style={{ marginTop: 6 }}>
              <Button loading={m.isPending} onClick={() => m.mutate()}>
                {loginToken ? "Re-authenticate" : "Sign in"}
              </Button>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-h"><div><h2>How auth works here</h2></div></div>
          <div className="card-b">
            <ol className="muted-text" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
              <li>Login returns a JWT tied to your user.</li>
              <li>Creating a test session issues a <b>separate token for that session</b>.</li>
              <li>Every session-scoped call must carry <b>that session's</b> token.</li>
              <li>Cross-session access is rejected with <span className="mono">403</span>.</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
