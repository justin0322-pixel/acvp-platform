import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getVectorSet, getResults, submitResults, idFromUrl } from "../api/client";
import { isRetry, isExpired } from "../api/types";
import type { SessionObject, VectorSetResponse, Prompt, VectorResults } from "../api/types";
import { StepHead, Button, Notice, StatusBadge } from "../ui";
import { buildResponse } from "../lib/flow";

function SubmitCard({ url, session }: { url: string; session: SessionObject }) {
  const qc = useQueryClient();
  const prompt = useQuery({
    queryKey: ["vs", url],
    queryFn: () => getVectorSet(url, session.accessToken),
    refetchInterval: (q) => {
      const d = q.state.data as VectorSetResponse | undefined;
      return d && isRetry(d) ? 1500 : false;
    },
  });
  const results = useQuery({
    queryKey: ["results", url],
    queryFn: () => getResults(url, session.accessToken),
  });

  const m = useMutation({
    mutationFn: () => submitResults(url, buildResponse(prompt.data as Prompt), session.accessToken),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["results", url] }),
  });

  const d = prompt.data;
  const ready = d && !isRetry(d) && !isExpired(d);
  const disposition = (results.data as VectorResults | undefined)?.results.disposition;
  const submitted = !!disposition && disposition !== "unreceived";
  const cases = ready ? (d as any).testGroups?.reduce((n: number, g: any) => n + (g.tests?.length ?? 0), 0) : 0;

  return (
    <div className="card">
      <div className="card-h">
        <div><h2>Vector set #{idFromUrl(url)}</h2>
          <div className="desc">{ready ? `${cases} test cases` : "waiting for vectors"}</div></div>
        <div style={{ marginLeft: "auto" }}>
          <StatusBadge status={(disposition as any) ?? "pending"} />
        </div>
      </div>
      <div className="card-b stack">
        {!ready && <div className="notice info"><span className="spin dark" />Vectors not retrieved yet…</div>}
        {m.isError && <Notice kind="err">{(m.error as Error).message}</Notice>}
        {submitted && !m.isError && (
          <Notice kind="ok">Responses submitted — the server is validating. See the Results step for the disposition.</Notice>
        )}
        <div className="btn-row">
          <Button loading={m.isPending} disabled={!ready || submitted} onClick={() => m.mutate()}>
            {submitted ? "Submitted" : "Submit responses"}
          </Button>
          {ready && !submitted && (
            <span className="muted-text" style={{ alignSelf: "center" }}>
              Sends every tcId from the prompt (a real DUT fills in the answers).
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function Submit({ session, onNext }: { session: SessionObject; onNext: () => void }) {
  const multi = session.vectorSetUrls.length > 1;
  return (
    <div>
      <StepHead eyebrow="Step 4" title="Submit answers">
        Upload the computed responses for each vector set. Submission returns an empty 200 — no
        score — per the spec; the disposition is pulled separately in the next step.
      </StepHead>
      <div className={multi ? "panels" : "stack"}>
        {session.vectorSetUrls.map((url) => <SubmitCard key={url} url={url} session={session} />)}
      </div>
      <div className="btn-row" style={{ marginTop: 20 }}>
        <Button variant="ghost" onClick={onNext}>Continue to results →</Button>
      </div>
    </div>
  );
}
