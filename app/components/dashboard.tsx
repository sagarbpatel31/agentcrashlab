"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Beaker,
  Check,
  CheckCheck,
  ChevronDown,
  CircleHelp,
  Code2,
  FileCode2,
  FlaskConical,
  GitBranch,
  History,
  Layers3,
  Loader2,
  Play,
  Plus,
  Radio,
  RotateCcw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Terminal,
  TriangleAlert,
  X,
} from "lucide-react";
import type {
  Agent,
  Bootstrap,
  Job,
  Repair,
  Run,
  Scenario,
  TraceEvent,
} from "@/lib/types";

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/lab/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The operation failed");
  return result;
}
const pretty = (value: unknown) => JSON.stringify(value, null, 2);
const label = (value: string) => value.replaceAll("_", " ");
const sourceLabel = (run: Run) =>
  run.source_kind === "candidate"
    ? run.mode === "offline"
      ? "Candidate · model stub"
      : `Candidate · ${run.model}`
    : run.reference
      ? "Reference fixture"
      : run.mode === "offline"
        ? "Scripted fixture"
        : run.model || "Live agent";
function Status({ status }: { status: string }) {
  return (
    <span className={`status ${status}`}>
      <span />
      {status === "pass"
        ? "Passed"
        : status === "fail"
          ? "Failed"
          : label(status)}
    </span>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Bootstrap | null>(null);
  const [agentId, setAgentId] = useState("workspace");
  const [agentInfo, setAgentInfo] = useState<{
    manifest: Agent;
    sources: Record<string, string>;
    scenarios: Scenario[];
  } | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [mode, setMode] = useState("offline");
  const [runner, setRunner] = useState("modal");
  const [provider, setProvider] = useState("meta");
  const [model, setModel] = useState("muse-spark-1.3");
  const [tab, setTab] = useState("laboratory");
  const [evidenceTab, setEvidenceTab] = useState("timeline");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [showScenarios, setShowScenarios] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const [activeJob, setActiveJob] = useState<string | null>(null);
  const [selectedRepair, setSelectedRepair] = useState<Repair | null>(null);
  const [importSource, setImportSource] = useState<string | null>(null);
  const completedJob = useRef<string | null>(null);
  const investigatorAbort = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await api<Bootstrap>("bootstrap"));
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not connect to the experiment engine",
      );
    }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(
      () => void refresh(),
      activeJob || busy ? 1500 : 5000,
    );
    return () => clearInterval(timer);
  }, [refresh, activeJob, busy]);
  useEffect(() => {
    let current = true;
    api<{
      manifest: Agent;
      sources: Record<string, string>;
      scenarios: Scenario[];
    }>(`agents/${agentId}`)
      .then((info) => {
        if (current) {
          setAgentInfo(info);
          setScenarios(info.scenarios);
        }
      })
      .catch((e) => setError(e.message));
    setSelectedId(null);
    setSelectedRepair(null);
    setSelectedRun(null);
    return () => {
      current = false;
    };
  }, [agentId]);
  useEffect(() => {
    if (!selectedId) return;
    let current = true;
    api<Run>(`runs/${selectedId}`)
      .then((run) => {
        if (current) setSelectedRun(run);
      })
      .catch((e) => setError(e.message));
    return () => {
      current = false;
    };
  }, [selectedId, data?.runs]);
  useEffect(() => {
    if (!data || !activeJob) return;
    const job = data.jobs.find((j) => j.id === activeJob);
    if (!job || job.status === "running" || completedJob.current === job.id)
      return;
    completedJob.current = job.id;
    setActiveJob(null);
    if (job.error) setError(job.error);
    const results = data.runs.filter((r) => job.run_ids.includes(r.id));
    const candidate = results.find((r) => r.status === "fail") || results[0];
    if (candidate) setSelectedId(candidate.id);
    if (job.kind === "reduction" && job.result?.scenario) {
      setScenarios([job.result.scenario]);
      setNotice(`Reduced experiment ready. ${job.result.minimality}`);
    }
    if (job.kind === "verification" && selectedRepair) {
      const repaired = data.repairs.find((r) => r.id === selectedRepair.id);
      if (repaired) setSelectedRepair(repaired);
    }
  }, [data, activeJob, selectedRepair]);

  const agent = data?.agents.find((a) => a.id === agentId);
  const runs = data?.runs.filter((r) => r.agent_id === agentId) || [];
  const latestCampaign = data?.jobs.find(
    (job) =>
      job.agent_id === agentId && ["campaign", "reference"].includes(job.kind),
  );
  const campaignRuns = latestCampaign
    ? latestCampaign.run_ids
        .map((id) => runs.find((r) => r.id === id))
        .filter((r): r is Run => Boolean(r))
    : runs.filter((r) => r.source_kind !== "candidate").slice(0, 8);
  const repairs = data?.repairs.filter((r) => r.agent_id === agentId) || [];
  const running =
    Boolean(activeJob) ||
    Boolean(data?.jobs.some((j) => j.status === "running"));
  const configured = Boolean(
    data?.providers.find((p) => p.id === provider)?.configured,
  );
  const disabled = Boolean(busy) || running;
  const failures =
    data?.metrics?.[agentId]?.failures ??
    runs.filter((r) => r.status === "fail").length;
  const completed =
    data?.metrics?.[agentId]?.executed ??
    runs.filter((r) => r.status !== "running").length;
  const activated =
    data?.metrics?.[agentId]?.activated ??
    runs.reduce((sum, run) => sum + (run.fault_coverage?.activated || 0), 0);

  async function perform(name: string, operation: () => Promise<void>) {
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await operation();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setBusy("");
    }
  }
  async function runCampaign(reference = false) {
    await perform("campaign", async () => {
      const job = await api<Job>("campaigns", {
        agent_id: agentId,
        scenarios,
        mode: reference ? "offline" : mode,
        runner: reference || mode === "offline" ? "fixture" : runner,
        provider,
        model,
        reference,
      });
      setActiveJob(job.id);
      setSelectedRepair(null);
      setTab("laboratory");
    });
  }
  async function investigate(action: "design" | "repair") {
    await perform(action, async () => {
      const controller = new AbortController();
      investigatorAbort.current = controller;
      const response = await fetch("/api/investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          action,
          agent_id: agentId,
          run_id: selectedRun?.id,
          provider,
          model,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      if (action === "design") {
        setScenarios(result.scenarios);
        setShowScenarios(true);
        setNotice(
          `Experiments designed by ${provider}/${model}. ${result.summary}`,
        );
      } else {
        setSelectedRepair(result);
        setEvidenceTab("repair");
      }
      investigatorAbort.current = null;
    });
  }
  function changeProvider(value: string) {
    setProvider(value);
    setModel(data?.providers.find((p) => p.id === value)?.model || "");
  }
  async function cancel() {
    if (investigatorAbort.current) {
      investigatorAbort.current.abort();
      investigatorAbort.current = null;
      return;
    }
    const job = activeJob || data?.jobs.find((j) => j.status === "running")?.id;
    if (job)
      await perform("cancel", async () => {
        await api(`jobs/${job}/cancel`, {});
      });
  }
  const exportUrl = (format: string, repair = false) =>
    `/api/lab/export/${repair ? "repair" : "run"}/${repair ? selectedRepair?.id : selectedRun?.id}?format=${format}`;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="AgentCrashLab home">
          <div className="brand-icon">
            <FlaskConical size={22} />
          </div>
          <span>
            agentcrashlab<span className="brand-dot">.</span>
          </span>
        </a>
        <div className="workspace-switch">
          <div className="avatar">S</div>
          <div>
            <strong>Personal workspace</strong>
            <small>Local environment</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {[
            { id: "laboratory", title: "Laboratory", icon: Beaker },
            { id: "history", title: "Run history", icon: History },
            { id: "repairs", title: "Repairs", icon: GitBranch },
            { id: "settings", title: "Connections", icon: Settings2 },
          ].map(({ id, title, icon: Icon }) => (
            <button
              key={id}
              className={tab === id ? "nav-item active" : "nav-item"}
              onClick={() => setTab(id)}
            >
              <Icon size={17} />
              <span>{title}</span>
              {id === "repairs" && repairs.length > 0 ? (
                <span className="nav-count">{repairs.length}</span>
              ) : null}
              {id === "laboratory" ? <span className="active-dot" /> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-lab">
          <span className="eyebrow">
            <Radio size={13} /> BUILT TO BREAK THINGS
          </span>
          <h3>
            Confidence comes
            <br />
            from evidence.
          </h3>
          <p>Test the paths your happy-path tests never reach.</p>
          <button
            onClick={() => {
              setTab("laboratory");
              setShowScenarios(true);
            }}
          >
            Explore experiments <ArrowUpRight size={15} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <a
            href="https://github.com/meta-models/meta-model-cookbook"
            target="_blank"
            rel="noreferrer"
          >
            <CircleHelp size={16} /> Model cookbook <ArrowUpRight size={13} />
          </a>
          <div className="local-status">
            <span />
            All data stored locally<small>v0.1.0</small>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="breadcrumb">Workspace</span>
            <span className="slash">/</span>
            <strong>
              {tab === "laboratory"
                ? "Laboratory"
                : tab === "settings"
                  ? "Connections"
                  : tab === "history"
                    ? "Run history"
                    : "Repairs"}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="local-pill">
              <span />
              Local lab
            </span>
            <a
              href="https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details"
              target="_blank"
              rel="noreferrer"
            >
              Hackathon guide <ArrowUpRight size={13} />
            </a>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow green">
                <span className="tiny-cross">✳</span> AGENT RELIABILITY, UNDER
                THE MICROSCOPE
              </div>
              <h1>
                {tab === "laboratory" ? (
                  <>
                    Find the failure. <span>Prove the fix.</span>
                  </>
                ) : tab === "settings" ? (
                  "Connect your intelligence."
                ) : tab === "history" ? (
                  "Every experiment. Every outcome."
                ) : (
                  "Repairs backed by evidence."
                )}
              </h1>
              <p>
                {tab === "laboratory"
                  ? "Break your agents on purpose. Turn the unexpected into a regression test."
                  : tab === "settings"
                    ? "Direct provider connections. Your credits, your models, your machine."
                    : "Recorded outcomes from actual executions in your local laboratory."}
              </p>
            </div>
            <div className="heading-marker">
              <Activity size={25} />
              <span>
                OBSERVE
                <br />
                CHALLENGE
                <br />
                <b>VERIFY</b>
              </span>
            </div>
          </div>
          {error ? (
            <div className="message error-message" role="alert">
              <TriangleAlert size={17} />
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          ) : null}
          {notice ? (
            <div className="message notice-message" role="status">
              <Check size={17} />
              <span>{notice}</span>
              <button
                onClick={() => setNotice("")}
                aria-label="Dismiss notification"
              >
                <X size={16} />
              </button>
            </div>
          ) : null}
          {tab === "settings" ? (
            <Connections data={data} />
          ) : (
            <>
              <section className="metrics" aria-label="Laboratory metrics">
                {[
                  {
                    label: "Experiments executed",
                    value: completed,
                    icon: Layers3,
                    detail: "Recorded in this lab",
                  },
                  {
                    label: "Failures reproduced",
                    value: failures,
                    icon: TriangleAlert,
                    detail: "Assertion violations",
                    danger: true,
                  },
                  {
                    label: "Faults activated",
                    value: activated,
                    icon: Activity,
                    detail: "Observed injection coverage",
                  },
                  {
                    label: "Verified repairs",
                    value: repairs.filter((r) => r.status === "verified")
                      .length,
                    icon: ShieldCheck,
                    detail: "Passed the verification matrix",
                  },
                ].map(({ label: title, value, icon: Icon, detail, danger }) => (
                  <div className="metric" key={title}>
                    <div className="metric-label">
                      {title}
                      <Icon size={16} />
                    </div>
                    <div
                      className={`metric-value ${danger && value ? "danger-text" : ""}`}
                    >
                      {String(value).padStart(2, "0")}
                      <span>{detail}</span>
                    </div>
                  </div>
                ))}
              </section>
              {tab === "repairs" ? (
                <section className="panel">
                  <PanelHeader
                    title="Candidate repairs"
                    subtitle="Generated candidates remain unverified until isolated execution passes."
                    icon={<GitBranch size={17} />}
                  />
                  <div className="repair-list">
                    {repairs.length ? (
                      repairs.map((r) => (
                        <button
                          key={r.id}
                          className="repair-list-item"
                          onClick={() => {
                            setSelectedRepair(r);
                            setSelectedId(r.run_id);
                            setEvidenceTab("repair");
                            setTab("laboratory");
                          }}
                        >
                          <FileCode2 size={20} />
                          <span>
                            <strong>{r.explanation.slice(0, 100)}</strong>
                            <small>{r.provenance}</small>
                          </span>
                          <Status status={r.status} />
                          <ArrowRight size={17} />
                        </button>
                      ))
                    ) : (
                      <Empty
                        title="A failure is the starting point."
                        text="Select a failed experiment, then generate or import a candidate repair."
                      />
                    )}
                  </div>
                </section>
              ) : (
                <>
                  {tab === "laboratory" ? (
                    <div className="lab-grid">
                      <section className="panel configuration">
                        <PanelHeader
                          title="Experiment setup"
                          subtitle="Choose what to put under pressure."
                          icon={<Settings2 size={17} />}
                        />
                        <div className="config-body">
                          <label className="field-label" htmlFor="agent-select">
                            TARGET AGENT<span>01</span>
                          </label>
                          <div className="agent-select">
                            <div className="agent-glyph">
                              <Layers3 size={21} />
                            </div>
                            <select
                              id="agent-select"
                              aria-label="Target agent"
                              value={agentId}
                              onChange={(e) => setAgentId(e.target.value)}
                              disabled={disabled}
                            >
                              {(data?.agents || []).map((a) => (
                                <option key={a.id} value={a.id}>
                                  {a.name}
                                </option>
                              ))}
                            </select>
                          </div>
                          <p className="agent-description">
                            {agent?.description ||
                              "Connecting to the experiment engine…"}
                          </p>
                          <button
                            className="text-button source-toggle"
                            onClick={() => setShowSource(!showSource)}
                          >
                            <Code2 size={13} />
                            Inspect agent source
                            <ArrowUpRight size={12} />
                          </button>
                          <div className="field-divider" />
                          <label className="field-label">
                            EXECUTION MODE<span>02</span>
                          </label>
                          <div
                            className="segmented"
                            role="group"
                            aria-label="Execution mode"
                          >
                            <button
                              className={mode === "offline" ? "selected" : ""}
                              onClick={() => setMode("offline")}
                              disabled={disabled}
                            >
                              <Terminal size={14} />
                              Offline fixtures
                            </button>
                            <button
                              className={mode === "live" ? "selected" : ""}
                              onClick={() => setMode("live")}
                              disabled={disabled}
                            >
                              <Sparkles size={14} />
                              Live model
                            </button>
                          </div>
                          <p className="helper">
                            {mode === "offline"
                              ? "Scripted acceptance fixtures. No model calls or credits used."
                              : "Real inference. Tested agent code runs in an isolated environment."}
                          </p>
                          <div className="provider-row">
                            <div>
                              <label htmlFor="provider-select">
                                Inference provider
                              </label>
                              <select
                                id="provider-select"
                                value={provider}
                                onChange={(e) => changeProvider(e.target.value)}
                              >
                                <option value="meta">Meta Model API</option>
                                <option value="baseten">Baseten</option>
                                <option value="fireworks">Fireworks</option>
                              </select>
                            </div>
                            <div>
                              <label htmlFor="runner-select">
                                Isolation runner
                              </label>
                              <select
                                id="runner-select"
                                value={runner}
                                onChange={(e) => setRunner(e.target.value)}
                              >
                                <option value="modal">Modal Sandbox</option>
                                <option value="docker">Local Docker</option>
                              </select>
                            </div>
                          </div>
                          <label className="model-label" htmlFor="model-input">
                            Model ID
                          </label>
                          <input
                            id="model-input"
                            value={model}
                            onChange={(e) => setModel(e.target.value)}
                            list="models"
                            placeholder="Enter an explicit model ID"
                          />
                          <datalist id="models">
                            {provider === "meta" ? (
                              <>
                                <option value="muse-spark-1.3" />
                                <option value="muse-wonder-1.0" />
                              </>
                            ) : null}
                          </datalist>
                          <div className="field-divider" />
                          <div className="experiments-label">
                            <label className="field-label">
                              FAILURE EXPERIMENTS<span>03</span>
                            </label>
                            <span className="count-pill">
                              {scenarios.length}
                            </span>
                          </div>
                          <div className="fault-chips">
                            {["Lost response", "Rate limit", "Stale read"].map(
                              (s) => (
                                <span key={s}>
                                  <span />
                                  {s}
                                </span>
                              ),
                            )}
                          </div>
                          <button
                            className="outline-button wide"
                            onClick={() => setShowScenarios(!showScenarios)}
                          >
                            <FileCode2 size={14} />
                            {showScenarios
                              ? "Hide experiments"
                              : "Review experiments"}
                            <ChevronDown size={14} />
                          </button>
                          <button
                            className="text-button design-button"
                            disabled={!configured || disabled || !model}
                            onClick={() => void investigate("design")}
                          >
                            {busy === "design" ? (
                              <Loader2 className="spin" size={14} />
                            ) : (
                              <Sparkles size={14} />
                            )}
                            Design from agent code
                          </button>
                          {!configured ? (
                            <p className="connection-hint">
                              Live design unlocks when a provider is connected.
                            </p>
                          ) : null}
                          <button
                            className="primary-button run-button"
                            disabled={
                              disabled ||
                              !scenarios.length ||
                              (mode === "live" && (!configured || !model))
                            }
                            onClick={() => void runCampaign()}
                          >
                            {running || busy === "campaign" ? (
                              <Loader2 className="spin" size={16} />
                            ) : (
                              <Play size={16} fill="currentColor" />
                            )}
                            {running ? "Campaign running" : "Run campaign"}
                            <span>↵</span>
                          </button>
                          {running || busy === "design" || busy === "repair" ? (
                            <button
                              className="text-button cancel-button"
                              onClick={() => void cancel()}
                            >
                              <Square size={12} />
                              Cancel operation
                            </button>
                          ) : null}
                          <div className="setup-footer">
                            <ShieldCheck size={12} />
                            {mode === "offline"
                              ? "Included trusted fixtures only"
                              : "Credentials stay outside the tested agent"}
                          </div>
                        </div>
                      </section>
                      <div className="results-column">
                        <section className="panel campaign-panel">
                          <PanelHeader
                            title="Campaign results"
                            subtitle={
                              running
                                ? "Experiments are running. Evidence updates automatically."
                                : "A healthy control, then the paths that usually go untested."
                            }
                            icon={<Activity size={17} />}
                            action={
                              <span className="subtle-tag">
                                {mode === "offline"
                                  ? "OFFLINE FIXTURES"
                                  : "LIVE INFERENCE"}
                              </span>
                            }
                          />
                          <RunTable
                            runs={campaignRuns}
                            selectedId={selectedId}
                            onSelect={(r) => {
                              setSelectedId(r.id);
                              setSelectedRepair(null);
                              setEvidenceTab("timeline");
                            }}
                          />
                          <div className="table-footer">
                            <span>
                              <span className="legend-dot" />
                              All outcomes come from executed experiments
                            </span>
                            <button
                              className="text-button"
                              onClick={() => setTab("history")}
                            >
                              View history
                              <ArrowRight size={13} />
                            </button>
                          </div>
                        </section>
                        <div className="insight-card">
                          <div className="insight-icon">
                            <GitBranch size={21} />
                          </div>
                          <div>
                            <span className="eyebrow">
                              THE FAILURE THAT LOOKS LIKE SUCCESS
                            </span>
                            <h3>A timeout doesn’t mean nothing happened.</h3>
                            <p>
                              The write may have committed. Watch the agent’s
                              view and the service’s state diverge.
                            </p>
                          </div>
                          <div className="mini-flow">
                            <span>write</span>
                            <i />
                            <span className="mini-fault">timeout</span>
                            <i />
                            <span>retry</span>
                            <i />
                            <span className="mini-duplicate">×2</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <section className="panel">
                      <PanelHeader
                        title="Run history"
                        subtitle="Select a run to inspect its complete evidence."
                        icon={<History size={17} />}
                      />
                      <RunTable
                        runs={runs}
                        selectedId={selectedId}
                        onSelect={(r) => {
                          setSelectedId(r.id);
                          setTab("laboratory");
                        }}
                      />
                    </section>
                  )}
                  {showSource && agentInfo ? (
                    <section className="panel source-panel">
                      <PanelHeader
                        title="Agent source"
                        subtitle="The investigator reads these files and the declared tool contracts."
                        icon={<Code2 size={17} />}
                        action={
                          <button
                            className="icon-button"
                            onClick={() => setShowSource(false)}
                            aria-label="Close source"
                          >
                            <X size={15} />
                          </button>
                        }
                      />
                      {Object.entries(agentInfo.sources).map(
                        ([name, source]) => (
                          <div key={name}>
                            <div className="code-filename">{name}</div>
                            <pre>{source}</pre>
                          </div>
                        ),
                      )}
                    </section>
                  ) : null}
                  {showScenarios ? (
                    <section className="panel scenario-panel">
                      <PanelHeader
                        title="Review failure experiments"
                        subtitle="Edit the specification before running. The engine validates every fault against tool contracts."
                        icon={<FileCode2 size={17} />}
                      />
                      <ScenarioEditor
                        key={pretty(scenarios)}
                        scenarios={scenarios}
                        onApply={(value) => {
                          setScenarios(value);
                          setNotice("Experiment specification updated.");
                        }}
                        onError={setError}
                      />
                    </section>
                  ) : null}
                  <section className="panel evidence-panel">
                    <div className="evidence-header">
                      <div className="section-heading">
                        <div className="section-icon">
                          <GitBranch size={17} />
                        </div>
                        <div>
                          <h2>Evidence, not assumptions.</h2>
                          <p>
                            {selectedRun
                              ? selectedRun.scenario.name
                              : "Select an experiment to see what really happened."}
                          </p>
                        </div>
                      </div>
                      <div
                        className="evidence-tabs"
                        role="tablist"
                        aria-label="Evidence view"
                      >
                        {["timeline", "assertions", "repair"].map((t) => (
                          <button
                            key={t}
                            role="tab"
                            aria-selected={evidenceTab === t}
                            className={evidenceTab === t ? "selected" : ""}
                            onClick={() => setEvidenceTab(t)}
                          >
                            {t === "repair" ? <GitBranch size={13} /> : null}
                            {t[0].toUpperCase() + t.slice(1)}
                          </button>
                        ))}
                      </div>
                      {selectedRun ? (
                        <a
                          className="outline-button small"
                          href={exportUrl("zip")}
                          download
                        >
                          <ArrowDownToLine size={14} />
                          Export evidence
                        </a>
                      ) : null}
                    </div>
                    {!selectedRun ? (
                      <Empty
                        title="Your next failure is a useful discovery."
                        text="Run a campaign and select an experiment. Every request, committed effect, and observation will appear here."
                      />
                    ) : (
                      <>
                        <div className="run-meta">
                          <Status status={selectedRun.status} />
                          <span>
                            {selectedRun.mode === "offline"
                              ? "Offline fixture"
                              : `${selectedRun.provider} / ${selectedRun.model}`}
                          </span>
                          <span>
                            {selectedRun.source_kind === "candidate"
                              ? "Candidate source"
                              : selectedRun.reference
                                ? "Handwritten reference controller"
                                : selectedRun.mode === "offline"
                                  ? "Scripted fixture controller"
                                  : "Original agent"}
                          </span>
                          <span>{selectedRun.elapsed_ms || 0} ms</span>
                          <span className="mono">
                            {selectedRun.id.slice(0, 8)}
                          </span>
                        </div>
                        <div className="usage-strip">
                          <span>
                            {selectedRun.usage.model_calls} provider calls
                          </span>
                          <span>
                            {selectedRun.mode === "offline"
                              ? "No live inference"
                              : `${selectedRun.usage.input_tokens.toLocaleString()} input / ${selectedRun.usage.output_tokens.toLocaleString()} output tokens reported`}
                          </span>
                          <span>
                            {selectedRun.usage.cost_usd === null
                              ? "Cost not reported"
                              : `$${selectedRun.usage.cost_usd.toFixed(4)}`}
                          </span>
                          <span>Runner: {selectedRun.runner}</span>
                        </div>
                        {selectedRun.first_failure ? (
                          <div className="failure-banner">
                            <TriangleAlert size={18} />
                            <div>
                              <strong>
                                {label(selectedRun.first_failure.id)}
                              </strong>
                              <p>{selectedRun.first_failure.detail}</p>
                            </div>
                            <span>ASSERTION VIOLATED</span>
                          </div>
                        ) : null}
                        {selectedRun.error ? (
                          <div className="inline-error">
                            {selectedRun.error}
                          </div>
                        ) : null}
                        {evidenceTab === "timeline" ? (
                          <>
                            <Timeline run={selectedRun} />
                            <div className="evidence-actions">
                              <button
                                className="outline-button"
                                disabled={disabled}
                                onClick={() =>
                                  void perform("replay", async () => {
                                    const result = await api<{
                                      verified: boolean;
                                      detail: string;
                                    }>(`runs/${selectedRun.id}/replay`, {});
                                    setNotice(
                                      `${result.verified ? "Replay verified" : "Replay mismatch"}. ${result.detail}`,
                                    );
                                  })
                                }
                              >
                                <RotateCcw size={14} />
                                Replay recorded actions
                              </button>
                              <button
                                className="outline-button"
                                disabled={
                                  disabled || selectedRun.status !== "fail"
                                }
                                onClick={() =>
                                  void perform("reduce", async () => {
                                    const job = await api<Job>(
                                      `runs/${selectedRun.id}/reduce`,
                                      {},
                                    );
                                    setActiveJob(job.id);
                                  })
                                }
                              >
                                Reduce failure
                                <ArrowRight size={14} />
                              </button>
                              <button
                                className="text-button"
                                disabled={
                                  disabled || selectedRun.mode !== "offline"
                                }
                                onClick={() => void runCampaign(true)}
                              >
                                Compare handwritten reference
                                <ArrowUpRight size={13} />
                              </button>
                            </div>
                          </>
                        ) : evidenceTab === "assertions" ? (
                          <div className="assertion-list">
                            {selectedRun.assertions.map((a) => (
                              <div
                                key={a.id}
                                className={
                                  a.passed
                                    ? "assertion passed"
                                    : "assertion failed"
                                }
                              >
                                {a.passed ? (
                                  <Check size={17} />
                                ) : (
                                  <X size={17} />
                                )}
                                <div>
                                  <strong>{label(a.id)}</strong>
                                  <p>{a.detail}</p>
                                </div>
                                <Status status={a.passed ? "pass" : "fail"} />
                              </div>
                            ))}
                            <div className="coverage-note">
                              Fault coverage:{" "}
                              {selectedRun.fault_coverage?.activated || 0} /{" "}
                              {selectedRun.fault_coverage?.planned || 0} planned
                              faults activated. A missing required fault makes a
                              run inconclusive.
                            </div>
                          </div>
                        ) : (
                          <div className="repair-panel">
                            <div className="repair-intro">
                              <div>
                                <h3>
                                  From counterexample to candidate repair.
                                </h3>
                                <p>
                                  Generate a patch from the frozen failure
                                  evidence, then verify it in isolation.
                                </p>
                              </div>
                              <button
                                className="primary-button"
                                disabled={
                                  disabled ||
                                  !configured ||
                                  selectedRun.status !== "fail" ||
                                  repairs.filter(
                                    (item) => item.run_id === selectedRun.id,
                                  ).length >= 3
                                }
                                onClick={() => void investigate("repair")}
                              >
                                {busy === "repair" ? (
                                  <Loader2 className="spin" size={15} />
                                ) : (
                                  <Sparkles size={15} />
                                )}
                                Generate candidate
                              </button>
                            </div>
                            {!configured ? (
                              <div className="quiet-note">
                                Connect an inference provider to generate a
                                repair. You can also import a candidate source
                                file for isolated testing.
                              </div>
                            ) : null}
                            <button
                              className="text-button"
                              disabled={selectedRun.status !== "fail"}
                              onClick={() =>
                                setImportSource(
                                  importSource === null
                                    ? agentInfo?.sources["agent.py"] || ""
                                    : null,
                                )
                              }
                            >
                              <Plus size={14} />
                              Import candidate source
                            </button>
                            {importSource !== null ? (
                              <div className="import-candidate">
                                <label htmlFor="candidate-source">
                                  Replacement agent.py
                                </label>
                                <textarea
                                  id="candidate-source"
                                  value={importSource}
                                  onChange={(e) =>
                                    setImportSource(e.target.value)
                                  }
                                  spellCheck={false}
                                />
                                <button
                                  className="outline-button"
                                  onClick={() =>
                                    void perform("import", async () => {
                                      setSelectedRepair(
                                        await api<Repair>("repairs", {
                                          run_id: selectedRun.id,
                                          files: { "agent.py": importSource },
                                          explanation:
                                            "Developer-supplied candidate source",
                                          provenance: "developer supplied",
                                        }),
                                      );
                                      setImportSource(null);
                                    })
                                  }
                                >
                                  Save candidate for verification
                                </button>
                              </div>
                            ) : null}
                            {selectedRepair ? (
                              <div className="patch-result">
                                <div className="patch-title">
                                  <FileCode2 size={16} />
                                  <strong>candidate.patch</strong>
                                  <Status status={selectedRepair.status} />
                                </div>
                                <p>{selectedRepair.explanation}</p>
                                <small>{selectedRepair.provenance}</small>
                                <pre className="diff">
                                  {selectedRepair.patch
                                    .split("\n")
                                    .map((line, i) => (
                                      <span
                                        key={i}
                                        className={
                                          line.startsWith("+")
                                            ? "diff-add"
                                            : line.startsWith("-")
                                              ? "diff-remove"
                                              : ""
                                        }
                                      >
                                        {line || " "}
                                        {"\n"}
                                      </span>
                                    ))}
                                </pre>
                                <div className="verification-actions">
                                  <button
                                    className="primary-button"
                                    disabled={disabled}
                                    onClick={() =>
                                      void perform("verify", async () => {
                                        const job = await api<Job>(
                                          `repairs/${selectedRepair.id}/verify`,
                                          { runner },
                                        );
                                        setActiveJob(job.id);
                                      })
                                    }
                                  >
                                    <ShieldCheck size={15} />
                                    Verify in{" "}
                                    {runner === "modal" ? "Modal" : "Docker"}
                                  </button>
                                  <a
                                    className="outline-button"
                                    href={exportUrl("zip", true)}
                                    download
                                  >
                                    <ArrowDownToLine size={14} />
                                    Export repair bundle
                                  </a>
                                </div>
                                {selectedRepair.verification_runs.length > 0 ? (
                                  <div className="verification-matrix">
                                    {selectedRepair.verification_runs.map(
                                      (id) => {
                                        const r = data?.runs.find(
                                          (item) => item.id === id,
                                        );
                                        return (
                                          <div key={id}>
                                            <span>
                                              {r?.scenario.name ||
                                                id.slice(0, 8)}
                                            </span>
                                            <Status
                                              status={r?.status || "running"}
                                            />
                                          </div>
                                        );
                                      },
                                    )}
                                  </div>
                                ) : null}
                                <p className="quiet-note">
                                  Verification covers this test matrix.{" "}
                                  {selectedRepair.verification_mode ===
                                  "offline"
                                    ? "Model responses were deterministic fixtures; no live reliability claim is made."
                                    : "It does not establish that all possible failures are prevented."}
                                </p>
                              </div>
                            ) : (
                              <div className="repair-empty">
                                <GitBranch size={26} />
                                <p>
                                  A candidate patch will appear here.
                                  <br />
                                  Your original agent files stay unchanged.
                                </p>
                              </div>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </section>
                </>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              <FlaskConical size={13} />
              AgentCrashLab <span className="footer-separator">/</span>Make
              failure reproducible.
            </span>
            <span>
              Built with Meta models <span className="footer-separator">·</span>
              Evidence stays local
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function PanelHeader({
  title,
  subtitle,
  icon,
  action,
}: {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel-header">
      <div className="section-heading">
        <div className="section-icon">{icon}</div>
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>
      {action}
    </div>
  );
}
function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty-state">
      <div className="empty-visual">
        <div className="empty-orbit" />
        <FlaskConical size={27} />
        <span className="orbit-plus">+</span>
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function RunTable({
  runs,
  selectedId,
  onSelect,
}: {
  runs: Run[];
  selectedId: string | null;
  onSelect: (run: Run) => void;
}) {
  if (!runs.length)
    return (
      <Empty
        title="Ready for the unexpected."
        text="Your first campaign starts with a healthy control, then introduces targeted failures."
      />
    );
  return (
    <div className="run-table-wrap">
      <table className="run-table">
        <thead>
          <tr>
            <th>EXPERIMENT</th>
            <th>OUTCOME</th>
            <th>FAULTS</th>
            <th>TIME</th>
            <th>
              <span className="sr-only">Inspect</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              className={selectedId === run.id ? "selected" : ""}
            >
              <td>
                <button onClick={() => onSelect(run)}>
                  <span className="row-glyph">
                    {run.scenario.faults.length ? (
                      <Activity size={15} />
                    ) : (
                      <ShieldCheck size={15} />
                    )}
                  </span>
                  <span>
                    {run.scenario.name}
                    <small>{sourceLabel(run)}</small>
                  </span>
                </button>
              </td>
              <td>
                <Status status={run.status} />
              </td>
              <td className="mono">
                {run.fault_coverage?.activated || 0}
                <span className="muted">
                  /{run.fault_coverage?.planned ?? run.scenario.faults.length}
                </span>
              </td>
              <td className="mono muted">
                {run.elapsed_ms ?? "—"}
                <small> ms</small>
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Inspect ${run.scenario.name}`}
                  onClick={() => onSelect(run)}
                >
                  <ArrowUpRight size={15} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Timeline({ run }: { run: Run }) {
  const requests =
    run.events?.filter((event) => event.kind === "request") || [];
  if (!requests.length)
    return (
      <Empty
        title="Waiting for tool evidence."
        text="Tool requests appear here as the agent executes."
      />
    );
  return (
    <div className="timeline">
      <div className="timeline-labels">
        <span>STEP / TOOL CALL</span>
        <span>WHAT THE AGENT SAW</span>
        <span>WHAT ACTUALLY HAPPENED</span>
      </div>
      {requests.map((request, index) => {
        const events =
          run.events?.filter((e) => e.call_id === request.call_id) || [];
        const observation = events.find((e) => e.kind === "observation");
        const effect = events.find((e) => e.kind === "effect");
        const fault = events.find((e) => e.kind === "fault");
        const deduped = events.some((e) => e.kind === "deduplicated");
        const diverged =
          Boolean(observation?.error && effect) || Boolean(observation?.stale);
        return (
          <div
            className={`timeline-row ${diverged ? "diverged" : ""}`}
            key={request.seq}
          >
            <div className="timeline-step">
              <span className="step-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <strong>{request.tool}</strong>
                <small>
                  {request.elapsed_ms} ms
                  {fault ? ` · ${label(fault.fault_kind || "fault")}` : ""}
                </small>
                <code>{pretty(request.arguments)}</code>
              </div>
            </div>
            <div
              className={`observation-cell ${observation?.error ? "observation-error" : ""}`}
            >
              {observation?.error ? (
                <>
                  <span className="cell-label">
                    <TriangleAlert size={12} />
                    {label(observation.error.code)}
                  </span>
                  <p>{observation.error.message}</p>
                </>
              ) : (
                <>
                  <span className="cell-label">
                    <Check size={12} />
                    {observation?.stale
                      ? "Stale response"
                      : "Response received"}
                  </span>
                  <pre>{pretty(observation?.result)}</pre>
                </>
              )}
            </div>
            <div className="effect-cell">
              <span className="cell-label">
                {effect ? (
                  <>
                    <CheckCheck size={13} />
                    Write committed
                  </>
                ) : deduped ? (
                  <>
                    <ShieldCheck size={13} />
                    Duplicate prevented
                  </>
                ) : (
                  "No new write"
                )}
              </span>
              {effect ? (
                <pre>{pretty(effect.result)}</pre>
              ) : (
                <p>
                  {deduped
                    ? "Returned the original operation’s result."
                    : observation?.stale
                      ? "The service returned a historical snapshot."
                      : "Authoritative state unchanged."}
                </p>
              )}
              {diverged ? (
                <span className="divergence-label">OBSERVATION ≠ REALITY</span>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
function ScenarioEditor({
  scenarios,
  onApply,
  onError,
}: {
  scenarios: Scenario[];
  onApply: (value: Scenario[]) => void;
  onError: (error: string) => void;
}) {
  const [draft, setDraft] = useState(pretty(scenarios));
  return (
    <div className="scenario-editor">
      <label className="sr-only" htmlFor="scenario-json">
        Experiment JSON
      </label>
      <textarea
        id="scenario-json"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        spellCheck={false}
      />
      <div>
        <p>
          Expected outcomes come from the agent manifest and cannot be changed
          here.
        </p>
        <button
          className="outline-button"
          onClick={() => {
            try {
              const parsed = JSON.parse(draft);
              if (!Array.isArray(parsed) || !parsed.length)
                throw new Error("Provide a nonempty array of experiments");
              onApply(parsed);
            } catch (e) {
              onError(e instanceof Error ? e.message : "Invalid JSON");
            }
          }}
        >
          Apply specification
          <Check size={14} />
        </button>
      </div>
    </div>
  );
}
function Connections({ data }: { data: Bootstrap | null }) {
  return (
    <>
      <section className="connections-grid">
        {(data?.providers || []).map((p) => (
          <div className="panel connection-card" key={p.id}>
            <div className="connection-top">
              <Sparkles size={22} />
              <Status status={p.configured ? "connected" : "not configured"} />
            </div>
            <h2>
              {p.id === "meta"
                ? "Meta Model API"
                : p.id === "baseten"
                  ? "Baseten"
                  : "Fireworks"}
            </h2>
            <p>
              {p.id === "meta"
                ? "Investigation, experiment design, and candidate repairs."
                : "Meta open-weight inference for comparative experiments."}
            </p>
            <code>{p.model || "Set an explicit model ID"}</code>
          </div>
        ))}
      </section>
      <section className="panel setup-guide">
        <h2>Connect a provider</h2>
        <p>
          Create <code>.env.local</code> from <code>.env.example</code>, add
          your credentials locally, and restart the app. Keys are read by the
          server and never sent to the browser or tested agent.
        </p>
        <pre>
          MODEL_API_KEY=your_key{"\n"}META_MODEL=muse-spark-1.3{"\n\n"}
          BASETEN_API_KEY=your_key{"\n"}
          BASETEN_MODEL=meta-models/muse-spark-open-1026{"\n\n"}
          FIREWORKS_API_KEY=your_key{"\n"}FIREWORKS_MODEL=your_provider_model_id
        </pre>
        <h3>Isolated execution</h3>
        <p>
          Install Modal support with <code>uv sync --extra modal</code> and
          authenticate with <code>uv run modal token new</code>. For Docker,
          start your local Docker service and pull <code>python:3.13-slim</code>
          .
        </p>
        <div className="quiet-note">
          A missing provider or runner produces a setup error. It never becomes
          a simulated success.
        </div>
      </section>
    </>
  );
}
