"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState, useCallback } from "react";
import {
  Zap, DollarSign, BarChart3, Github,
  Copy, Check, ChevronDown, TrendingUp,
  Shield, RefreshCw, ArrowRight, Sparkles,
} from "lucide-react";

const AO_BASE = "https://agentoptima.ai";

// ── Types ─────────────────────────────────────────────────────────────────────

interface KeyStatus {
  label: string;
  plan: string;
  budget_limit_usd: number;
  budget_remaining_usd: number;
  spent_total_cents: number;
  last_30_days: {
    spent_cents: number;
    saved_cents: number;
    saved_usd: number;
    cache_hit_count: number;
    cache_saved_cents: number;
    routing_saved_cents: number;
  };
  enabled: boolean;
}

interface StatusData {
  tasks_logged: number;
  tasks_success: number;
  models_tracked: number;
  version: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtUSD(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function shortModel(m: string): string {
  return m.split("/").pop() || m;
}

// ── Code snippet tabs ─────────────────────────────────────────────────────────

const SNIPPETS: Record<string, (key: string) => string> = {
  Python: (k) =>
`from openai import OpenAI

client = OpenAI(
    api_key="${k}",
    base_url="https://agentoptima.ai/v1"
)

response = client.chat.completions.create(
    model="auto",   # ← AgentOptima picks cheapest model
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)`,

  JavaScript: (k) =>
`import OpenAI from 'openai';

const client = new OpenAI({
  apiKey: '${k}',
  baseURL: 'https://agentoptima.ai/v1'
});

const response = await client.chat.completions.create({
  model: 'auto',   // ← AgentOptima picks cheapest model
  messages: [{ role: 'user', content: 'Hello!' }]
});
console.log(response.choices[0].message.content);`,

  curl: (k) =>
`curl https://agentoptima.ai/v1/chat/completions \\
  -H "Authorization: Bearer ${k}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
};

// ── Components ────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy} className="p-1.5 rounded hover:bg-white/10 transition-colors">
      {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} className="text-slate-400" />}
    </button>
  );
}

function StatCard({
  label, value, sub, color = "text-white", delay = 0,
}: {
  label: string; value: string; sub?: string; color?: string; delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className="card p-5"
    >
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </motion.div>
  );
}

// ── Landing (no key) ──────────────────────────────────────────────────────────

function LandingPage({ onKey }: { onKey: (k: string) => void }) {
  const [inputKey, setInputKey] = useState("");
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [label, setLabel] = useState("my-app");
  const [budget, setBudget] = useState(500);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"Python" | "JavaScript" | "curl">("Python");
  const [status, setStatus] = useState<StatusData | null>(null);

  useEffect(() => {
    fetch(`${AO_BASE}/api/v1/status`)
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {});
  }, []);

  const createKey = async () => {
    setCreating(true);
    setError("");
    try {
      const r = await fetch(`${AO_BASE}/api/v1/keys/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, budget_limit_cents: budget }),
      });
      const d = await r.json();
      if (d.key) {
        setNewKey(d.key);
      } else {
        setError("Failed to create key. Try again.");
      }
    } catch {
      setError("Network error. Try again.");
    } finally {
      setCreating(false);
    }
  };

  const demoSnippet = SNIPPETS[tab](newKey || "ao-your-key-here");

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      {/* Nav */}
      <nav className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap size={20} className="text-primary" />
          <span className="font-bold text-lg">AgentOptima</span>
        </div>
        <div className="flex items-center gap-4">
          <a href="https://github.com/arisauraaudit/agentoptima" target="_blank" rel="noopener noreferrer"
            className="text-slate-400 hover:text-white transition-colors">
            <Github size={18} />
          </a>
          <button
            onClick={() => inputKey && onKey(inputKey)}
            className="text-sm text-slate-300 hover:text-white transition-colors px-3 py-1.5 border border-slate-700 rounded-lg hover:border-slate-500"
          >
            Sign in with key
          </button>
        </div>
      </nav>

      {/* Hero */}
      <div className="max-w-4xl mx-auto px-6 pt-20 pb-12 text-center">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-primary/30 bg-primary/5 text-primary text-xs mb-6">
            <Sparkles size={12} />
            One line. Every AI model. Automatic cost optimization.
          </div>
          <h1 className="text-5xl font-bold mb-4 leading-tight">
            Stop overpaying<br />
            <span className="gradient-text">for AI.</span>
          </h1>
          <p className="text-slate-400 text-lg mb-8 max-w-xl mx-auto">
            AgentOptima sits between your app and every AI provider.
            It automatically routes to the cheapest capable model and
            caches repeated work — zero code changes required.
          </p>
        </motion.div>

        {/* Live stats bar */}
        {status && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
            className="flex items-center justify-center gap-6 text-sm text-slate-400 mb-10"
          >
            <span>
              <span className="text-white font-mono">{status.tasks_logged.toLocaleString()}</span> tasks routed
            </span>
            <span className="text-slate-700">·</span>
            <span>
              <span className="text-white font-mono">{status.models_tracked}</span> models tracked
            </span>
            <span className="text-slate-700">·</span>
            <span>
              <span className="text-green-400 font-mono">v{status.version}</span> live
            </span>
          </motion.div>
        )}

        {/* Key creation / login */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="card p-6 max-w-lg mx-auto mb-10"
        >
          {newKey ? (
            <div className="text-left">
              <div className="text-green-400 text-sm font-medium mb-3 flex items-center gap-2">
                <Check size={14} /> Your API key is ready
              </div>
              <div className="flex items-center gap-2 bg-slate-900 rounded-lg p-3 mb-4">
                <code className="text-primary text-sm flex-1 truncate">{newKey}</code>
                <CopyButton text={newKey} />
              </div>
              <p className="text-xs text-slate-500 mb-4">Save this key — we can&apos;t show it again.</p>
              <button
                onClick={() => onKey(newKey)}
                className="button-primary w-full py-2.5 rounded-lg text-sm font-medium flex items-center justify-center gap-2"
              >
                Open dashboard <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            <div className="text-left space-y-3">
              <div>
                <label className="text-xs text-slate-400 mb-1 block">Label</label>
                <input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="my-app"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary transition-colors"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">
                  Budget limit — <span className="text-white">${(budget / 100).toFixed(2)}</span>
                </label>
                <input
                  type="range" min={50} max={10000} step={50}
                  value={budget} onChange={(e) => setBudget(Number(e.target.value))}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-xs text-slate-600 mt-1">
                  <span>$0.50</span><span>$100</span>
                </div>
              </div>
              {error && <p className="text-red-400 text-xs">{error}</p>}
              <button
                onClick={createKey}
                disabled={creating}
                className="button-primary w-full py-2.5 rounded-lg text-sm font-medium disabled:opacity-50"
              >
                {creating ? "Creating…" : "Get your free API key →"}
              </button>
              <div className="text-center">
                <span className="text-xs text-slate-600">Already have a key? </span>
                <button
                  className="text-xs text-primary hover:underline"
                  onClick={() => {
                    const k = prompt("Paste your ao-xxxx key:");
                    if (k) onKey(k);
                  }}
                >
                  Sign in
                </button>
              </div>
            </div>
          )}
        </motion.div>

        {/* Code snippet */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
          className="card overflow-hidden max-w-2xl mx-auto mb-16"
        >
          <div className="flex items-center gap-1 px-4 pt-3 border-b border-slate-800">
            {(["Python", "JavaScript", "curl"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-2 text-xs font-medium rounded-t transition-colors ${
                  tab === t ? "text-white border-b-2 border-primary" : "text-slate-500 hover:text-slate-300"
                }`}
              >
                {t}
              </button>
            ))}
            <div className="ml-auto pb-1">
              <CopyButton text={demoSnippet} />
            </div>
          </div>
          <pre className="text-xs text-slate-300 p-4 overflow-x-auto text-left leading-relaxed">
            <code>{demoSnippet}</code>
          </pre>
        </motion.div>

        {/* Feature grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl mx-auto">
          {[
            {
              icon: <Zap size={18} className="text-primary" />,
              title: "Smart Routing",
              desc: "Automatically picks the cheapest model that can handle your task. Simple prompts → cheap models. Complex work → quality models.",
            },
            {
              icon: <DollarSign size={18} className="text-green-400" />,
              title: "Semantic Cache",
              desc: "Same question twice costs zero the second time. Identical prompts return instantly from cache — no API call, no bill.",
            },
            {
              icon: <Shield size={18} className="text-yellow-400" />,
              title: "Hard Budget Limits",
              desc: "Set a spending cap. When you hit it, all calls stop. No surprise bills. Update your limit anytime from the dashboard.",
            },
          ].map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 + i * 0.1 }}
              className="card p-5 text-left"
            >
              <div className="mb-3">{f.icon}</div>
              <div className="font-semibold mb-1 text-sm">{f.title}</div>
              <div className="text-xs text-slate-400 leading-relaxed">{f.desc}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Dashboard (with key) ──────────────────────────────────────────────────────

function Dashboard({ apiKey, onSignOut }: { apiKey: string; onSignOut: () => void }) {
  const [status, setStatus] = useState<KeyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"Python" | "JavaScript" | "curl">("Python");
  const [refreshing, setRefreshing] = useState(false);

  const fetchStatus = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await fetch(`${AO_BASE}/api/v1/keys/status`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      if (!r.ok) { setError("Invalid key or key not found."); return; }
      const d = await r.json();
      setStatus(d);
      setError("");
    } catch {
      setError("Could not load dashboard. Check your connection.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [apiKey]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const snippet = SNIPPETS[tab](apiKey);

  const savedUSD   = status ? (status.last_30_days.saved_cents / 100) : 0;
  const spentUSD   = status ? (status.last_30_days.spent_cents / 100) : 0;
  const cacheHits  = status?.last_30_days.cache_hit_count ?? 0;
  const budgetPct  = status
    ? Math.min(100, (status.spent_total_cents / 100 / status.budget_limit_usd) * 100)
    : 0;
  const multiplier = spentUSD > 0 ? ((savedUSD + spentUSD) / spentUSD).toFixed(1) : "∞";

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--background)" }}>
        <div className="animate-pulse text-slate-400">Loading dashboard…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--background)" }}>
        <div className="card p-8 max-w-sm text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <button onClick={onSignOut} className="button-primary px-6 py-2 rounded-lg text-sm">
            Use a different key
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      {/* Nav */}
      <nav className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap size={20} className="text-primary" />
          <span className="font-bold text-lg">AgentOptima</span>
          {status?.plan && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary capitalize ml-1">
              {status.plan}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchStatus}
            disabled={refreshing}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
          </button>
          <button onClick={onSignOut} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
            Sign out
          </button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Greeting */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
          <h2 className="text-2xl font-bold mb-1">
            {status?.label ? `${status.label}` : "Your dashboard"}
          </h2>
          <p className="text-slate-400 text-sm">Last 30 days</p>
        </motion.div>

        {/* Hero savings number */}
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4 }}
          className="card p-8 mb-6 text-center relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-green-500/5 pointer-events-none" />
          <div className="text-slate-400 text-sm mb-2">Total saved</div>
          <div className="text-6xl font-bold gradient-text mb-2">
            ${savedUSD.toFixed(2)}
          </div>
          <div className="text-slate-400 text-sm">
            You spent <span className="text-white">${spentUSD.toFixed(4)}</span> and saved{" "}
            <span className="text-green-400">{multiplier}x</span> vs using GPT-4o directly
          </div>
        </motion.div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <StatCard
            label="Spent (30d)"
            value={`$${spentUSD.toFixed(4)}`}
            sub="actual cost"
            delay={0.05}
          />
          <StatCard
            label="Cache hits"
            value={cacheHits.toLocaleString()}
            sub="free responses"
            color="text-primary"
            delay={0.1}
          />
          <StatCard
            label="Routing saved"
            value={fmtUSD(status?.last_30_days.routing_saved_cents ?? 0)}
            sub="vs GPT-4o baseline"
            color="text-green-400"
            delay={0.15}
          />
          <StatCard
            label="Cache saved"
            value={fmtUSD(status?.last_30_days.cache_saved_cents ?? 0)}
            sub="from cache hits"
            color="text-yellow-400"
            delay={0.2}
          />
        </div>

        {/* Budget bar */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="card p-5 mb-6"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium">Budget</span>
            <span className="text-xs text-slate-400">
              ${(status!.spent_total_cents / 100).toFixed(4)} of ${status!.budget_limit_usd.toFixed(2)} used
            </span>
          </div>
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${budgetPct}%` }}
              transition={{ duration: 0.8, ease: "easeOut" }}
              className={`h-full rounded-full ${
                budgetPct > 80 ? "bg-red-500" : budgetPct > 60 ? "bg-yellow-400" : "bg-gradient-to-r from-primary to-green-400"
              }`}
            />
          </div>
          <div className="flex justify-between text-xs text-slate-500 mt-2">
            <span>{budgetPct.toFixed(1)}% used</span>
            <span>${status!.budget_remaining_usd.toFixed(2)} remaining</span>
          </div>
        </motion.div>

        {/* Your API key + code snippets */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card overflow-hidden mb-6"
        >
          <div className="p-5 border-b border-slate-800">
            <div className="text-sm font-medium mb-3">Your API key</div>
            <div className="flex items-center gap-2 bg-slate-900 rounded-lg px-3 py-2">
              <code className="text-primary text-sm flex-1 truncate">{apiKey}</code>
              <CopyButton text={apiKey} />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-1 px-4 pt-3 border-b border-slate-800">
              {(["Python", "JavaScript", "curl"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-3 py-2 text-xs font-medium transition-colors ${
                    tab === t
                      ? "text-white border-b-2 border-primary"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {t}
                </button>
              ))}
              <div className="ml-auto pb-1">
                <CopyButton text={snippet} />
              </div>
            </div>
            <pre className="text-xs text-slate-300 p-4 overflow-x-auto leading-relaxed">
              <code>{snippet}</code>
            </pre>
          </div>
        </motion.div>

        {/* How it works */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="card p-5"
        >
          <div className="text-sm font-medium mb-4">How your requests are routed</div>
          <div className="space-y-3">
            {[
              { label: "Simple prompts", desc: "→ gpt-4o-mini · fast + ultra-cheap", color: "bg-green-500" },
              { label: "Complex tasks", desc: "→ best model from 416K real benchmarks", color: "bg-primary" },
              { label: "Strategy / security", desc: "→ quality model always · no compromise", color: "bg-yellow-400" },
              { label: "Repeated prompts", desc: "→ cache · instant · $0.00 cost", color: "bg-purple-400" },
            ].map((r) => (
              <div key={r.label} className="flex items-center gap-3">
                <div className={`w-2 h-2 rounded-full ${r.color} flex-shrink-0`} />
                <span className="text-sm text-white w-36 flex-shrink-0">{r.label}</span>
                <span className="text-xs text-slate-400">{r.desc}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}

// ── Root ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const [apiKey, setApiKey] = useState<string>("");

  useEffect(() => {
    const stored = localStorage.getItem("ao_key");
    if (stored) setApiKey(stored);
  }, []);

  const handleKey = (k: string) => {
    setApiKey(k);
    localStorage.setItem("ao_key", k);
  };

  const handleSignOut = () => {
    setApiKey("");
    localStorage.removeItem("ao_key");
  };

  return (
    <AnimatePresence mode="wait">
      {apiKey ? (
        <motion.div key="dashboard" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <Dashboard apiKey={apiKey} onSignOut={handleSignOut} />
        </motion.div>
      ) : (
        <motion.div key="landing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <LandingPage onKey={handleKey} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
