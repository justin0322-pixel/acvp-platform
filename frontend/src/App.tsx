import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { listAlgorithms, login } from "./api/client";

// Minimal demo: log in (get JWT), then list supported algorithms via TanStack Query.
// Extend into the full select -> generate -> download -> upload -> results flow.
export default function App() {
  const [password, setPassword] = useState("acvp-demo");
  const [token, setToken] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: () => login(password),
    onSuccess: (r) => setToken(r.accessToken),
  });

  const algorithms = useQuery({
    queryKey: ["algorithms", token],
    queryFn: () => listAlgorithms(token!),
    enabled: !!token,
  });

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 640, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>ACVP client</h1>

      <section style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
        />
        <button onClick={() => loginMutation.mutate()} disabled={loginMutation.isPending}>
          {loginMutation.isPending ? "Logging in…" : "Log in"}
        </button>
      </section>
      {loginMutation.isError && <p style={{ color: "crimson" }}>Login failed.</p>}
      {token && <p>Authenticated.</p>}

      {token && (
        <section>
          <h2>Supported algorithms</h2>
          {algorithms.isLoading && <p>Loading…</p>}
          <ul>
            {algorithms.data?.algorithms.map((a) => (
              <li key={`${a.algorithm}-${a.mode}`}>
                {a.algorithm} / {a.mode} / {a.revision}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
