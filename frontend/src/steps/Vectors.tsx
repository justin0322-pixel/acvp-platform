import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getVectorSet, getExpected, idFromUrl } from "../api/client";
import { isRetry, isExpired } from "../api/types";
import type { SessionObject, VectorSetResponse, Prompt } from "../api/types";
import { StepHead, Button, Json, Notice } from "../ui";

function VectorSetCard({ url, session }: { url: string; session: SessionObject }) {
  const vsId = idFromUrl(url);
  const q = useQuery({
    queryKey: ["vs", url],
    queryFn: () => getVectorSet(url, session.accessToken),
    // Poll while the server is still generating (it replies with a retry signal).
    refetchInterval: (query) => {
      const d = query.state.data as VectorSetResponse | undefined;
      if (d && isRetry(d)) {
        return d.retry ? d.retry * 1000 : 1500;
      }
      return false;
    },
  });

  const [showExpected, setShowExpected] = useState(false);
  const expected = useQuery({
    queryKey: ["expected", url], enabled: showExpected,
    queryFn: () => getExpected(url, session.accessToken),
  });

  const d = q.data;
  const generating = q.isLoading || (d && isRetry(d));
  const expired = d && isExpired(d);
  const ready = d && !isRetry(d) && !isExpired(d);

  const promptData = ready ? d as Prompt : null;

  return (
    <div className="card">
      <div className="card-h">
        <div>
          <h2>Vector set #{vsId}</h2>
          <div className="desc">{promptData ? `${promptData.algorithm} / ${promptData.mode}` : " "}</div>
        </div>
        <div style={{ marginLeft: "auto" }}>
          {generating && <span className="badge info">generating</span>}
          {expired && <span className="badge muted">expired</span>}
          {ready && <span className="badge ok">retrieved</span>}
        </div>
      </div>
      <div className="card-b stack">
        {q.isError && <Notice kind="err">{(q.error as Error).message}</Notice>}
        {generating && (
          <div className="notice info">
            <span className="spin dark" />
            Server is generating vectors — polling
            {d && isRetry(d) ? ` (suggested retry ${d.retry}s)` : ""}…
          </div>
        )}
        {expired && <Notice kind="err">This vector set has expired.</Notice>}
        {ready && promptData && (
          <>
            <div className="between">
              <div className="muted-text">
                {promptData.testGroups?.length ?? 0} test group(s) ·{" "}
                {promptData.testGroups?.reduce((n: number, g) => n + (g.tests?.length ?? 0), 0)} cases
              </div>
              {session.isSample && (
                <Button variant="soft" onClick={() => setShowExpected((v) => !v)}>
                  {showExpected ? "Hide expected answers" : "Download expected answers"}
                </Button>
              )}
            </div>
            <Json value={d} />
            {showExpected && (
              <>
                <div className="muted-text">Expected results (sample answer key):</div>
                {expected.isLoading && <div className="notice info"><span className="spin dark" />Loading…</div>}
                {expected.isError && <Notice kind="err">{(expected.error as Error).message}</Notice>}
                {expected.data && <Json value={expected.data} />}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function Vectors({ session }: { session: SessionObject }) {
  const multi = session.vectorSetUrls.length > 1;
  return (
    <div>
      <StepHead eyebrow="Step 3" title="Retrieve vectors">
        Download the vector set(s) for this session. Retrieval is asynchronous — while the server
        is still generating, it returns a retry signal and the client keeps polling. All calls here
        carry the session's own token.
      </StepHead>
      <div className={multi ? "panels" : "stack"}>
        {session.vectorSetUrls.map((url) => (
          <VectorSetCard key={url} url={url} session={session} />
        ))}
      </div>
    </div>
  );
}
