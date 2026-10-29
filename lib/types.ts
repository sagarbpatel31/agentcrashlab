export type Fault = { kind: string; tool: string; occurrence: number };
export type Scenario = {
  name: string;
  description?: string;
  faults: Fault[];
  seed?: number;
  task_overrides?: Record<string, unknown>;
};
export type Agent = {
  id: string;
  name: string;
  domain: string;
  description: string;
  entrypoint: string;
  editable_files: string[];
  expected_outcomes: string[];
  tools: { name: string; effect: string; contract?: string }[];
};
export type TraceEvent = {
  seq: number;
  kind: string;
  elapsed_ms: number;
  call_id?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  state?: Record<string, unknown>;
  error?: { code: string; message: string };
  fault_kind?: string;
  stale?: boolean;
};
export type Run = {
  id: string;
  agent_id: string;
  scenario: Scenario;
  status: string;
  mode: string;
  runner: string;
  provider: string | null;
  model: string | null;
  elapsed_ms?: number;
  started_at: string;
  reference: boolean;
  source_kind?: string;
  first_failure?: { id: string; detail: string };
  assertions: { id: string; detail: string; passed: boolean }[];
  fault_coverage?: { planned: number; activated: number };
  usage: {
    model_calls: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number | null;
  };
  state?: Record<string, unknown>;
  error?: string;
  events?: TraceEvent[];
  cleanup?: string;
};
export type Repair = {
  id: string;
  run_id: string;
  agent_id: string;
  patch: string;
  files: Record<string, string>;
  explanation: string;
  provenance: string;
  status: string;
  verification_runs: string[];
  verification_mode?: string;
};
export type Job = {
  id: string;
  status: string;
  kind: string;
  agent_id?: string;
  run_ids: string[];
  error?: string;
  result?: { scenario?: Scenario; minimality?: string; trials?: string[] };
};
export type Bootstrap = {
  metrics?: Record<
    string,
    { executed: number; failures: number; activated: number; verified: number }
  >;
  agents: Agent[];
  providers: { id: string; model: string; configured: boolean }[];
  runs: Run[];
  jobs: Job[];
  repairs: Repair[];
  runners: { docker_installed: boolean; modal_installed: boolean };
};
