import { useCallback, useEffect, useRef, useState } from "react";

import {
  apiBase,
  createEmotionThread,
  createThread,
  invokeRun,
  streamPlanRun,
  streamEmotionChat,
  type EmotionReport,
  type EmotionStreamEvent,
  type GraphValues,
  type PlanStreamEvent,
  type RunBody,
} from "./api";
import { MarkdownMessage } from "./MarkdownMessage";
import { TripOutputCard } from "./TripOutputCard";

type Theme = "dark" | "light";
type View = "home" | "emotion" | "date";

type ChatRow =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; text: string }
  | {
      id: string;
      role: "trip_output";
      weather?: string;
      travelLeg?: string;
      activities?: string;
      restaurants?: string;
      hotels?: string;
      agenda?: string;
    };

type PlanFields = {
  weather?: string;
  travelLeg?: string;
  activities?: string;
  restaurants?: string;
  hotels?: string;
  agenda?: string;
};

function pickStr(v: unknown): string | undefined {
  if (typeof v !== "string") return undefined;
  const t = v.trim();
  return t || undefined;
}

function interruptText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "prompt" in value) {
    const prompt = (value as { prompt?: unknown }).prompt;
    if (typeof prompt === "string") return prompt;
  }
  return JSON.stringify(value, null, 2);
}

function fieldsFromValues(values: GraphValues | undefined): PlanFields {
  const vals = values ?? {};
  return {
    weather: pickStr(vals.weather_summary),
    travelLeg: pickStr(vals.travel_leg_summary),
    activities: pickStr(vals.activity_recommendations),
    restaurants: pickStr(vals.restaurant_recommendations),
    hotels: pickStr(vals.hotel_recommendations),
    agenda: pickStr(vals.agenda),
  };
}

const LOGO = {
  dark: "/branding/logo-light.png",
  light: "/branding/logo-dark.png",
} as const;

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function DatePlannerPage({ onBack }: { onBack: () => void }) {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof localStorage === "undefined") return "dark";
    return (localStorage.getItem("date-assistant-theme") as Theme) || "dark";
  });
  const [streamingEnabled, setStreamingEnabled] = useState<boolean>(() => {
    if (typeof localStorage === "undefined") return true;
    return localStorage.getItem("date-assistant-streaming") !== "false";
  });
  const [threadId, setThreadId] = useState<string | null>(null);
  const [rows, setRows] = useState<ChatRow[]>([]);
  const [nodes, setNodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [awaitingResume, setAwaitingResume] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("date-assistant-theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("date-assistant-streaming", String(streamingEnabled));
  }, [streamingEnabled]);

  const appendAssistant = useCallback((text: string) => {
    setRows((r) => {
      const last = r.at(-1);
      if (last?.role === "assistant" && last.text === text) return r;
      return [...r, { id: uid(), role: "assistant", text }];
    });
  }, []);

  const appendUser = useCallback((text: string) => {
    setRows((r) => [...r, { id: uid(), role: "user", text }]);
  }, []);

  const mergePlanCard = useCallback((fields: PlanFields) => {
    if (
      !fields.weather &&
      !fields.travelLeg &&
      !fields.activities &&
      !fields.restaurants &&
      !fields.hotels &&
      !fields.agenda
    ) {
      return;
    }
    setRows((current) => {
      const next = [...current];
      const index = next.findIndex((row) => row.role === "trip_output");
      if (index === -1) {
        return [
          ...next,
          {
            id: uid(),
            role: "trip_output",
            weather: fields.weather,
            travelLeg: fields.travelLeg,
            activities: fields.activities,
            restaurants: fields.restaurants,
            hotels: fields.hotels,
            agenda: fields.agenda,
          },
        ];
      }

      const row = next[index];
      if (row.role !== "trip_output") return current;
      next[index] = {
        ...row,
        weather: fields.weather ?? row.weather,
        travelLeg: fields.travelLeg ?? row.travelLeg,
        activities: fields.activities ?? row.activities,
        restaurants: fields.restaurants ?? row.restaurants,
        hotels: fields.hotels ?? row.hotels,
        agenda: fields.agenda ?? row.agenda,
      };
      return next;
    });
  }, []);

  const applyFinalValues = useCallback(
    (values: GraphValues | undefined) => {
      mergePlanCard(fieldsFromValues(values));
      const finalMessage = pickStr(values?.final_message);
      if (finalMessage) appendAssistant(finalMessage);
    },
    [appendAssistant, mergePlanCard],
  );

  const runGraph = useCallback(
    async (body: RunBody) => {
      setBusy(true);
      setError(null);
      setNodes([]);
      setAwaitingResume(false);
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      try {
        if (streamingEnabled) {
          const { interrupted } = await streamPlanRun(
            body,
            (ev: PlanStreamEvent) => {
              if (ev.type === "node") {
                setNodes((n) => (n.includes(ev.name) ? n : [...n, ev.name]));
              } else if (ev.type === "final") {
                applyFinalValues(ev.values);
              } else if (ev.type === "interrupt") {
                applyFinalValues(ev.values);
                appendAssistant(interruptText(ev.value));
              } else if (ev.type === "error") {
                setError(ev.message);
              }
            },
            abortRef.current.signal,
          );
          setAwaitingResume(interrupted);
        } else {
          const result = await invokeRun(body, abortRef.current.signal);
          setNodes(result.nodes ?? []);
          applyFinalValues(result.values);
          if (result.interrupted) {
            appendAssistant(interruptText(result.interruptValue));
          }
          setAwaitingResume(result.interrupted);
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          setAwaitingResume(false);
          return;
        }
        setError(e instanceof Error ? e.message : String(e));
        setAwaitingResume(false);
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [appendAssistant, applyFinalValues, streamingEnabled],
  );

  const startNewTrip = useCallback(async () => {
    setError(null);
    setRows([]);
    setNodes([]);
    setAwaitingResume(false);
    setInput("");
    setBusy(true);
    try {
      const { threadId: tid } = await createThread();
      setThreadId(tid);
      await runGraph({ threadId: tid, input: {} });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [runGraph]);

  const sendUser = useCallback(async () => {
    const text = input.trim();
    if (!text || !threadId || busy) return;
    appendUser(text);
    setInput("");
    await runGraph({ threadId, command: { resume: text } });
  }, [appendUser, input, threadId, busy, runGraph]);

  const isDark = theme === "dark";

  return (
    <div
      className={
        isDark
          ? "flex h-screen bg-black text-zinc-100"
          : "flex h-screen bg-zinc-50 text-zinc-900"
      }
    >
      <aside
        className={
          isDark
            ? "flex w-64 shrink-0 flex-col border-r border-zinc-800 bg-[#0b0b0b]"
            : "flex w-64 shrink-0 flex-col border-r border-zinc-200 bg-white"
        }
      >
        <div className="flex items-center gap-2 border-b border-zinc-800/50 p-4 dark:border-zinc-800">
          <img
            src={isDark ? LOGO.dark : LOGO.light}
            alt=""
            className="h-8 w-8 object-contain"
          />
          <span className="font-semibold tracking-tight">约会助手</span>
        </div>

        <div className="flex flex-1 flex-col gap-3 p-3">
          <button
            type="button"
            onClick={onBack}
            className={
              isDark
                ? "rounded-lg border border-zinc-800 px-3 py-2 text-left text-sm text-zinc-300 hover:bg-zinc-900"
                : "rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-100"
            }
          >
            返回入口
          </button>
          <button
            type="button"
            onClick={startNewTrip}
            disabled={busy}
            className="rounded-lg bg-blue-600 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-blue-500 disabled:opacity-40"
          >
            新建约会
          </button>

          <label
            className={
              isDark
                ? "flex items-center justify-between rounded-lg border border-zinc-800 px-3 py-2 text-xs text-zinc-300"
                : "flex items-center justify-between rounded-lg border border-zinc-200 px-3 py-2 text-xs text-zinc-700"
            }
          >
            <span>流式响应</span>
            <button
              type="button"
              role="switch"
              aria-checked={streamingEnabled}
              onClick={() => setStreamingEnabled((v) => !v)}
              className={
                streamingEnabled
                  ? "relative h-5 w-9 rounded-full bg-blue-600 transition"
                  : isDark
                    ? "relative h-5 w-9 rounded-full bg-zinc-700 transition"
                    : "relative h-5 w-9 rounded-full bg-zinc-300 transition"
              }
            >
              <span
                className={
                  streamingEnabled
                    ? "absolute right-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition"
                    : "absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition"
                }
              />
            </button>
          </label>

          <p className={isDark ? "px-1 text-xs text-zinc-500" : "px-1 text-xs text-zinc-500"}>
            从空白对话开始，先收集约会地点、日期和时长，再逐步补全出发地、
            出行方式、外住与偏好。
          </p>
          {threadId ? (
            <p
              className={
                isDark
                  ? "mt-2 break-all px-1 font-mono text-[10px] text-zinc-600"
                  : "mt-2 break-all px-1 font-mono text-[10px] text-zinc-400"
              }
            >
              thread: {threadId.slice(0, 8)}...
            </p>
          ) : null}
        </div>

        <div
          className={
            isDark
              ? "mt-auto space-y-1 border-t border-zinc-800 p-3 text-xs text-zinc-500"
              : "mt-auto space-y-1 border-t border-zinc-200 p-3 text-xs text-zinc-500"
          }
        >
          <button
            type="button"
            onClick={() => setTheme(isDark ? "light" : "dark")}
            className={
              isDark
                ? "w-full rounded-md px-2 py-1.5 text-left hover:bg-zinc-800"
                : "w-full rounded-md px-2 py-1.5 text-left hover:bg-zinc-100"
            }
          >
            {isDark ? "浅色模式" : "深色模式"}
          </button>
          <a
            href="https://docs.langchain.com/langgraph-platform"
            target="_blank"
            rel="noreferrer"
            className="block rounded-md px-2 py-1.5 text-blue-500 hover:underline"
          >
            LangGraph 文档
          </a>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header
          className={
            isDark
              ? "flex items-center justify-between border-b border-zinc-800 px-6 py-3"
              : "flex items-center justify-between border-b border-zinc-200 px-6 py-3"
          }
        >
          <h1 className="text-sm font-medium text-zinc-400">
            使用 human-in-the-loop 生成中文约会方案
          </h1>
        </header>

        <div className={`scroll-dark flex-1 overflow-y-auto px-4 py-6 md:px-8 ${isDark ? "" : ""}`}>
          <div className="mx-auto max-w-3xl space-y-6">
            {rows.length === 0 && !busy ? (
              <div
                className={
                  isDark
                    ? "rounded-xl border border-zinc-800 bg-[#121212] p-8 text-center text-zinc-400"
                    : "rounded-xl border border-zinc-200 bg-white p-8 text-center text-zinc-600"
                }
              >
                <p className={isDark ? "mb-4 text-lg text-zinc-200" : "mb-4 text-lg text-zinc-800"}>
                  准备好了就开始
                </p>
                <p className="mb-6 text-sm">
                  连接本地 FastAPI + LangGraph 服务，并从仓库根目录的{" "}
                  <code className="text-blue-400">.env</code> 读取{" "}
                  <code className="text-blue-400">DASHSCOPE_API_KEY</code>。
                </p>
                <button
                  type="button"
                  onClick={startNewTrip}
                  className="rounded-full bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40"
                >
                  开始约会
                </button>
              </div>
            ) : null}

            {rows.map((row) =>
              row.role === "trip_output" ? (
                <article key={row.id} className="mr-8 flex justify-start">
                  <TripOutputCard
                    isDark={isDark}
                    weather={row.weather}
                    travelLeg={row.travelLeg}
                    activities={row.activities}
                    restaurants={row.restaurants}
                    hotels={row.hotels}
                    agenda={row.agenda}
                  />
                </article>
              ) : (
                <article
                  key={row.id}
                  className={
                    row.role === "user" ? "ml-8 flex justify-end" : "mr-8 flex justify-start"
                  }
                >
                  <div
                    className={
                      row.role === "user"
                        ? isDark
                          ? "max-w-[90%] rounded-2xl rounded-br-md bg-blue-600 px-4 py-3 text-sm text-white"
                          : "max-w-[90%] rounded-2xl rounded-br-md bg-blue-600 px-4 py-3 text-sm text-white"
                        : isDark
                          ? "max-w-[95%] rounded-xl border border-zinc-800 bg-[#121212] px-4 py-4 text-sm text-zinc-200"
                          : "max-w-[95%] rounded-xl border border-zinc-200 bg-white px-4 py-4 text-sm text-zinc-800"
                    }
                  >
                    {row.role === "user" ? (
                      row.text
                    ) : (
                      <MarkdownMessage isDark={isDark}>{row.text}</MarkdownMessage>
                    )}
                  </div>
                </article>
              ),
            )}

            {busy && nodes.length > 0 ? (
              <p className={isDark ? "text-center text-xs text-zinc-500" : "text-center text-xs text-zinc-500"}>
                运行中: {nodes.slice(-4).join(" → ")}
                {nodes.length > 4 ? "…" : ""}
              </p>
            ) : null}

            {error ? (
              <p
                className={
                  isDark
                    ? "rounded-lg border border-red-900/50 bg-red-950/40 px-4 py-3 text-sm text-red-300"
                    : "rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
                }
              >
                {error}
              </p>
            ) : null}
          </div>
        </div>

        <div
          className={
            isDark
              ? "border-t border-zinc-800 bg-black px-4 py-4 md:px-8"
              : "border-t border-zinc-200 bg-zinc-50 px-4 py-4 md:px-8"
          }
        >
          <div className="mx-auto max-w-3xl">
            <div
              className={
                isDark
                  ? "flex items-center gap-2 rounded-full border border-zinc-700 bg-[#0b0b0b] px-4 py-2 shadow-lg shadow-black/20 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/30"
                  : "flex items-center gap-2 rounded-full border border-zinc-300 bg-white px-4 py-2 shadow-md focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/30"
              }
            >
              <span className="text-zinc-500">+</span>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendUser();
                  }
                }}
                disabled={!threadId || !awaitingResume || busy}
                placeholder={
                  !threadId
                    ? "先点“新建约会”或“开始约会”"
                    : !awaitingResume
                      ? "等待助手提问后再输入"
                      : "回复助手的问题"
                }
                className={
                  isDark
                    ? "min-h-10 flex-1 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600 disabled:opacity-50"
                    : "min-h-10 flex-1 bg-transparent text-sm text-zinc-900 outline-none placeholder:text-zinc-400 disabled:opacity-50"
                }
              />
              <button
                type="button"
                onClick={() => void sendUser()}
                disabled={!threadId || !awaitingResume || busy || !input.trim()}
                className="rounded-full bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-40"
              >
                发送
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

type EmotionRow =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; text: string; report?: EmotionReport };

function HomePage({ onSelect }: { onSelect: (view: View) => void }) {
  return (
    <div className="min-h-screen bg-[#f5f0e8] text-stone-950">
      <main className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-10">
        <div className="mb-10 max-w-2xl">
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.24em] text-stone-500">
            Relationship Assistant
          </p>
          <h1 className="text-4xl font-semibold tracking-tight text-stone-950 md:text-6xl">
            选择你现在需要的帮助
          </h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-stone-600">
            一个入口进入基于书籍内容的情感咨询，另一个入口继续使用约会行程规划。
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <button
            type="button"
            onClick={() => onSelect("emotion")}
            className="group min-h-56 rounded-lg border border-stone-300 bg-white p-6 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-stone-900 hover:shadow-xl"
          >
            <span className="mb-10 block text-sm font-medium text-stone-500">01</span>
            <span className="block text-2xl font-semibold text-stone-950">情感咨询</span>
            <span className="mt-4 block text-sm leading-6 text-stone-600">
              基于书籍向量索引回答情感问题，并在回答正文中标注引用来源。
            </span>
            <span className="mt-8 inline-block text-sm font-semibold text-stone-950 group-hover:underline">
              进入咨询
            </span>
          </button>

          <button
            type="button"
            onClick={() => onSelect("date")}
            className="group min-h-56 rounded-lg border border-stone-900 bg-stone-950 p-6 text-left text-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-xl"
          >
            <span className="mb-10 block text-sm font-medium text-stone-400">02</span>
            <span className="block text-2xl font-semibold">约会行程规划</span>
            <span className="mt-4 block text-sm leading-6 text-stone-300">
              继续使用当前约会助手，收集日期、地点、出行和偏好后生成约会方案。
            </span>
            <span className="mt-8 inline-block text-sm font-semibold group-hover:underline">
              进入规划
            </span>
          </button>
        </div>
      </main>
    </div>
  );
}

function EmotionCounselingPage({ onBack }: { onBack: () => void }) {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [rows, setRows] = useState<EmotionRow[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const appendAssistantDelta = useCallback((text: string) => {
    if (!text) return;
    setRows((current) => {
      const next = [...current];
      const last = next.at(-1);
      if (last?.role === "assistant") {
        next[next.length - 1] = { ...last, text: `${last.text}${text}` };
        return next;
      }
      return [...next, { id: uid(), role: "assistant", text }];
    });
  }, []);

  const attachReport = useCallback((report: EmotionReport) => {
    setRows((current) => {
      const next = [...current];
      for (let i = next.length - 1; i >= 0; i -= 1) {
        const row = next[i];
        if (row.role === "assistant") {
          next[i] = { ...row, report };
          break;
        }
      }
      return next;
    });
  }, []);

  const startNewThread = useCallback(async () => {
    setBusy(true);
    setError(null);
    setRows([]);
    try {
      const created = await createEmotionThread();
      setThreadId(created.threadId);
      setRows([
        {
          id: uid(),
          role: "assistant",
          text: "你可以直接描述现在困扰你的情感问题。我会基于已建立索引的书籍内容回答，并在结尾给出引用来源。",
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || !threadId || busy) return;
    setRows((current) => [...current, { id: uid(), role: "user", text }]);
    setInput("");
    setBusy(true);
    setError(null);
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      await streamEmotionChat(
        { threadId, message: text },
        (ev: EmotionStreamEvent) => {
          if (ev.type === "delta") {
            appendAssistantDelta(ev.text);
          } else if (ev.type === "report") {
            // 后端返回的 downloadUrl 是相对路径（如 /api/emotion/reports/xxx），
            // 需要拼上后端 base URL 才能正确下载，否则浏览器会拼到前端端口上。
            attachReport({
              reportId: ev.reportId,
              downloadUrl: `${apiBase}${ev.downloadUrl}`,
              filename: ev.filename,
            });
          } else if (ev.type === "error") {
            setError(ev.message);
          }
        },
        abortRef.current.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [appendAssistantDelta, attachReport, busy, input, threadId]);

  return (
    <div className="flex h-screen bg-[#10100f] text-stone-100">
      <aside className="flex w-72 shrink-0 flex-col border-r border-stone-800 bg-[#171614]">
        <div className="border-b border-stone-800 p-4">
          <button
            type="button"
            onClick={onBack}
            className="mb-4 rounded-md border border-stone-700 px-3 py-2 text-sm text-stone-300 hover:bg-stone-800"
          >
            返回入口
          </button>
          <h1 className="text-lg font-semibold">情感咨询</h1>
          <p className="mt-2 text-xs leading-5 text-stone-400">
            基于书籍索引回答，不做医学诊断。遇到紧急风险请优先联系现实中的紧急帮助。
          </p>
        </div>

        <div className="flex flex-1 flex-col gap-3 p-4">
          <button
            type="button"
            onClick={startNewThread}
            disabled={busy}
            className="rounded-lg bg-emerald-600 px-3 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
          >
            新建咨询
          </button>
          {threadId ? (
            <p className="break-all font-mono text-[10px] text-stone-500">
              thread: {threadId.slice(0, 8)}...
            </p>
          ) : null}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="scroll-dark flex-1 overflow-y-auto px-4 py-6 md:px-8">
          <div className="mx-auto max-w-3xl space-y-5">
            {rows.length === 0 && !busy ? (
              <div className="rounded-lg border border-stone-800 bg-[#171614] p-8 text-center">
                <p className="mb-4 text-xl font-semibold">开始一次基于书籍的对话</p>
                <button
                  type="button"
                  onClick={startNewThread}
                  className="rounded-full bg-emerald-600 px-6 py-2 text-sm font-medium text-white hover:bg-emerald-500"
                >
                  新建咨询
                </button>
              </div>
            ) : null}

            {rows.map((row) => (
              <article
                key={row.id}
                className={row.role === "user" ? "ml-8 flex justify-end" : "mr-8 flex justify-start"}
              >
                <div
                  className={
                    row.role === "user"
                      ? "max-w-[90%] rounded-2xl rounded-br-md bg-emerald-700 px-4 py-3 text-sm text-white"
                      : "max-w-[95%] rounded-lg border border-stone-800 bg-[#171614] px-4 py-4 text-sm text-stone-100"
                  }
                >
                  {row.role === "user" ? row.text : <MarkdownMessage isDark>{row.text}</MarkdownMessage>}
                  {row.role === "assistant" && row.report ? (
                    <div className="mt-4 border-t border-stone-800 pt-3">
                      <a
                        href={row.report.downloadUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center rounded-md bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-500"
                      >
                        下载恋爱报告
                      </a>
                      <p className="mt-2 break-all text-xs text-stone-500">{row.report.filename}</p>
                    </div>
                  ) : null}
                </div>
              </article>
            ))}

            {busy ? <p className="text-center text-xs text-stone-500">咨询回复生成中...</p> : null}
            {error ? (
              <p className="rounded-lg border border-red-900/50 bg-red-950/40 px-4 py-3 text-sm text-red-300">
                {error}
              </p>
            ) : null}
          </div>
        </div>

        <div className="border-t border-stone-800 bg-[#10100f] px-4 py-4 md:px-8">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-center gap-2 rounded-full border border-stone-700 bg-[#171614] px-4 py-2 focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-500/30">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendMessage();
                  }
                }}
                disabled={!threadId || busy}
                placeholder={!threadId ? "先新建咨询" : "描述你的情感问题"}
                className="min-h-10 flex-1 bg-transparent text-sm text-stone-100 outline-none placeholder:text-stone-600 disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => void sendMessage()}
                disabled={!threadId || busy || !input.trim()}
                className="rounded-full bg-emerald-600 px-4 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
              >
                发送
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("home");

  if (view === "date") {
    return <DatePlannerPage onBack={() => setView("home")} />;
  }
  if (view === "emotion") {
    return <EmotionCounselingPage onBack={() => setView("home")} />;
  }
  return <HomePage onSelect={setView} />;
}
