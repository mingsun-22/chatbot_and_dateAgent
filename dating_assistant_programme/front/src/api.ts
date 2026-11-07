const configuredApiBase = import.meta.env.VITE_API_BASE_URL;
if (!configuredApiBase) {
  throw new Error("VITE_API_BASE_URL is required");
}
// 去掉末尾斜杠，供内部和外部统一拼接路径使用
export const apiBase = configuredApiBase.replace(/\/+$/, "");

export type GraphValues = Record<string, unknown>;

export type RunBody = {
  threadId: string;
  input?: Record<string, unknown> | null;
  command?: { resume?: unknown };
};

export type PlanStreamEvent =
  | { type: "node"; name: string }
  | { type: "interrupt"; value: unknown; values?: GraphValues; interrupted: true }
  | { type: "final"; values: GraphValues; interrupted: false }
  | { type: "error"; message: string };

export type InvokeRunResponse = {
  interrupted: boolean;
  interruptValue?: unknown;
  nodes?: string[];
  values?: GraphValues;
  error?: string;
};

export type EmotionReport = {
  reportId: string;
  downloadUrl: string;
  filename: string;
};

export type EmotionStreamEvent =
  | { type: "ready" }
  | { type: "delta"; text: string }
  | ({ type: "report" } & EmotionReport)
  | { type: "done" }
  | { type: "error"; message: string };

export async function createThread(): Promise<{ threadId: string }> {
  const r = await fetch(`${apiBase}/api/date/threads`, { method: "POST" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error ?? `HTTP ${r.status}`);
  return data;
}

export async function fetchThreadState(
  threadId: string,
): Promise<{ values: GraphValues }> {
  const r = await fetch(`${apiBase}/api/date/threads/${encodeURIComponent(threadId)}/state`);
  const data = await r.json();
  if (!r.ok) throw new Error(data.error ?? `HTTP ${r.status}`);
  return data;
}

async function postRun(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const r = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `Run failed: ${r.status}`);
  }
  return r;
}

async function parseSse<T extends { type: string }>(
  response: Response,
  onEvent: (ev: T) => void,
): Promise<{ interrupted: boolean }> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let interrupted = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const block of parts) {
      const line = block.trim();
      if (!line.startsWith("data:")) continue;
      const json = line.slice(5).trim();
      try {
        const ev = JSON.parse(json) as T;
        onEvent(ev);
        if (ev.type === "interrupt") interrupted = true;
      } catch {
        /* ignore malformed SSE blocks */
      }
    }
  }

  return { interrupted };
}

/** POST /api/date/runs/stream-plan: node events plus final graph state. */
export async function streamPlanRun(
  body: RunBody,
  onEvent: (ev: PlanStreamEvent) => void,
  signal?: AbortSignal,
): Promise<{ interrupted: boolean }> {
  const r = await postRun("/api/date/runs/stream-plan", body, signal);
  return parseSse<PlanStreamEvent>(r, onEvent);
}

/** POST /api/date/runs/invoke: non-streaming graph run. */
export async function invokeRun(body: RunBody, signal?: AbortSignal): Promise<InvokeRunResponse> {
  const r = await postRun("/api/date/runs/invoke", body, signal);
  const data = (await r.json()) as InvokeRunResponse;
  if (data.error) throw new Error(data.error);
  return data;
}

export async function buildEmotionIndexes(
  bookName?: string,
): Promise<{ result: Record<string, unknown> }> {
  const r = await postRun("/api/emotion/indexes/build", bookName ? { book_name: bookName } : {});
  return r.json();
}

export async function createEmotionThread(): Promise<{ threadId: string }> {
  const r = await fetch(`${apiBase}/api/emotion/threads`, { method: "POST" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error ?? `HTTP ${r.status}`);
  return data;
}

export async function streamEmotionChat(
  body: { threadId: string; message: string },
  onEvent: (ev: EmotionStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(`${apiBase}/api/emotion/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `Emotion chat failed: ${r.status}`);
  }
  await parseSse<EmotionStreamEvent>(r, onEvent);
}
