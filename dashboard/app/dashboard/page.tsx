"use client";

import { motion } from "framer-motion";
import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Zap, DollarSign, Zap as ZapIcon, Target, BarChart3,
  RefreshCw, Copy, Check, ArrowRight, AlertCircle, Loader2
} from "lucide-react";
import Link from "next/link";

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

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtUSD(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="p-1.5 rounded hover:bg-white/10 transition-colors"
    >
      {copied
        ? <Check size={13} className="text-[#00d4aa]" />
        : <Copy size={13} className="text-slate-400" />}
    </button>
  );
}

// ── No-key state ──────────────────────────────────────────────────────────────

function NoKeyState() {
  const [inputKey, setInputKey] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputKey.trim()) return;
    localStorage.setItem("ao_key", inputKey.trim());
    window.location.href = `/dashboard?key=${encodeURIComponent(inputKey.trim())}`;
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] bg-grid text-white flex items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="card p-8 w-full max-w-sm text-center"
      >
        <div className="w-12 h-12 rounded-full bg-[rgba(0,212,170,0.1)] border border-[rgba(0,212,170,0.2)] flex items-center justify-center mx-auto mb-5">
          <Zap size={22} className="text-[#00d4aa]" />
        </div>
        <h2 className="text-xl font-bold mb-2">Enter your API key</h2>
        <p className="text-sm text-slate-400 mb-6">Paste your ao-xxxx key to view your savings dashboard.</p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            value={inputKey}
            onChange={(e) => setInputKey(e.target.value)}
            placeholder="ao-xxxxxxxxxxxxxxxx"
            className="w-full bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] hover:border-[rgba(0,212,170,0.2)] focus:border-[rgba(0,212,170,0.4)] rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none transition-colors font-mono"
          />
          <button type="submit" className="button-primary w-full py-2.5">
            View dashboard →
          </button>
        </form>
        <div className="mt-4">
          <Link href="/onboarding" className="text-xs text-[#00d4aa] hover:underline">
            Don&apos;t have a key? Get one free →
          </Link>
        </div>
      </motion.div>
    </div>
  );
}

// ── Metric card ───────────────────────────────────────────────────────────────

function MetricCard({
  emoji,
  label,
  value,
  sub,
  accent = false,
  delay = 0,
}: {
  emoji: string;
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className={`card p-5 ${accent ? "border-[rgba(0,212,170,0.2)]" : ""}`}
    >
      <div className="text-2xl mb-2">{emoji}</div>
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-2xl font-black tracking-tight ${accent ? "text-[#00d4aa]" : "text-white"}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </motion.div>
  );
}

// ── Code snippet ──────────────────────────────────────────────────────────────

const MINI_SNIPPET = (k: string) =>
`from openai import OpenAI
client = OpenAI(
    api_key="${k.slice(0, 10)}...",
    base_url="https://agentoptima.ai/v1"
)`;

// ── Dashboard content ─────────────────────────────────────────────────────────

function DashboardContent({ apiKey }: { apiKey: string }) {
  const [status, setStatus] = useState<KeyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const fetchStatus = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const r = await fetch(`${AO_BASE}/api/v1/keys/status`, {
        headers: { Authorization: `Bearer ${apiKey}` },
        cache: "no-store",
      });
      if (!r.ok) {
        setError("Invalid or expired key.");
        return;
      }
      const d: KeyStatus = await r.json();
      setStatus(d);
      setError("");
    } catch {
      setError("Could not reach AgentOptima. Check your connection.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [apiKey]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(() => fetchStatus(true), 30_000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleSignOut = () => {
    localStorage.removeItem("ao_key");
    window.location.href = "/dashboard";
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] text-white flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-400">
          <Loader2 size={20} className="animate-spin" />
          Loading your dashboard…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] text-white flex items-center justify-center px-6">
        <div className="card p-8 max-w-sm text-center">
          <AlertCircle size={32} className="text-red-400 mx-auto mb-3" />
          <p className="text-red-400 mb-2 font-medium">Error loading dashboard</p>
          <p className="text-slate-400 text-sm mb-5">{error}</p>
          <div className="flex gap-3">
            <button
              onClick={() => fetchStatus()}
              className="flex-1 py-2 text-sm border border-[rgba(255,255,255,0.1)] rounded-lg hover:border-[rgba(0,212,170,0.2)] text-slate-300 transition-all"
            >
              Retry
            </button>
            <button
              onClick={handleSignOut}
              className="flex-1 button-primary py-2 text-sm"
            >
              Change key
            </button>
          </div>
        </div>
      </div>
    );
  }

  const saved30d = status ? status.last_30_days.saved_usd : 0;
  const spent30d = status ? status.last_30_days.spent_cents / 100 : 0;
  const cacheHits = status?.last_30_days.cache_hit_count ?? 0;
  const cacheSaved = status ? status.last_30_days.cache_saved_cents / 100 : 0;
  const routingSaved = status ? status.last_30_days.routing_saved_cents / 100 : 0;
  const budgetRemaining = status?.budget_remaining_usd ?? 0;
  // Estimate total requests: spent + saved / avg cost per request
  // rough: each request costs ~0.001 on average
  const estimatedRequests = status
    ? Math.max(1, Math.round((status.last_30_days.spent_cents + (status.last_30_days.saved_cents || 0)) / 0.1))
    : 0;

  const shortKey = apiKey.slice(0, 8) + "…";

  return (
    <div className="min-h-screen bg-[#0a0a0f] bg-grid text-white">
      {/* Nav */}
      <nav className="border-b border-[rgba(0,212,170,0.1)] px-6 py-4 flex items-center justify-between sticky top-0 z-50 bg-[#0a0a0f]/80 backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <Zap size={18} className="text-[#00d4aa]" />
          <span className="font-bold text-base tracking-tight">AgentOptima</span>
          {status?.label && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-[rgba(0,212,170,0.08)] text-[#00d4aa] border border-[rgba(0,212,170,0.15)] ml-1">
              {status.label}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchStatus(true)}
            className="text-slate-400 hover:text-white transition-colors"
            title="Refresh"
          >
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
          </button>
          <Link href="/docs" className="text-sm text-slate-500 hover:text-slate-300 transition-colors hidden sm:block">
            Docs
          </Link>
          <button
            onClick={handleSignOut}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            Sign out
          </button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Greeting */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-3xl font-black tracking-tight mb-1">
            Here&apos;s what AgentOptima saved you.
          </h1>
          <p className="text-slate-500 text-sm">Last 30 days · auto-refreshes every 30s</p>
        </motion.div>

        {/* 4 metric cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
          <MetricCard
            emoji="💰"
            label="Saved this month"
            value={fmtUSD(saved30d)}
            sub="vs GPT-4o baseline"
            accent
            delay={0}
          />
          <MetricCard
            emoji="⚡"
            label="Cache hits"
            value={cacheHits.toLocaleString()}
            sub="free responses"
            delay={0.06}
          />
          <MetricCard
            emoji="🎯"
            label="Requests routed"
            value={estimatedRequests > 0 ? estimatedRequests.toLocaleString() : "—"}
            sub="est. this month"
            delay={0.12}
          />
          <MetricCard
            emoji="🔋"
            label="Free tier remaining"
            value={`${Math.max(0, 1000 - estimatedRequests).toLocaleString()} / 1,000`}
            sub="requests"
            delay={0.18}
          />
        </div>

        {/* Free tier note */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.22 }}
          className="text-xs text-slate-500 mb-6"
        >
          Free tier: 1,000 requests/month. Upgrade for unlimited.
        </motion.p>

        {/* Savings breakdown */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.22 }}
          className="card p-5 mb-5"
        >
          <div className="text-sm font-semibold mb-4">Savings breakdown</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-[rgba(0,212,170,0.08)] flex items-center justify-center flex-shrink-0">
                <BarChart3 size={14} className="text-[#00d4aa]" />
              </div>
              <div>
                <div className="text-xs text-slate-400 mb-0.5">From smart routing</div>
                <div className="text-lg font-bold text-white">
                  {fmtUSD(routingSaved)}
                </div>
                <div className="text-xs text-slate-500">cheaper models, same quality</div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-[rgba(0,212,170,0.08)] flex items-center justify-center flex-shrink-0">
                <ZapIcon size={14} className="text-[#00d4aa]" />
              </div>
              <div>
                <div className="text-xs text-slate-400 mb-0.5">From cache hits</div>
                <div className="text-lg font-bold text-white">
                  {fmtUSD(cacheSaved)}
                </div>
                <div className="text-xs text-slate-500">repeated prompts cost $0</div>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-[rgba(255,255,255,0.05)] flex items-center justify-between text-xs text-slate-500">
            <span>Spent this month</span>
            <span className="text-white font-medium">${spent30d.toFixed(4)}</span>
          </div>
        </motion.div>

        {/* API key + integration reminder */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.28 }}
          className="card p-5 mb-5"
        >
          <div className="text-sm font-semibold mb-4">Your API key</div>
          <div className="flex items-center gap-2 bg-[rgba(0,212,170,0.04)] border border-[rgba(0,212,170,0.12)] rounded-lg px-4 py-2.5 mb-4">
            <code className="text-[#00d4aa] text-sm flex-1 font-mono">{shortKey}</code>
            <CopyButton text={apiKey} />
          </div>

          <div className="text-xs text-slate-500 mb-3">
            Using this key? Change one line:
          </div>
          <div className="card p-3 font-mono text-xs text-slate-300 leading-relaxed overflow-x-auto">
            <pre>{MINI_SNIPPET(apiKey)}</pre>
          </div>
        </motion.div>

        {/* Quick links */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.32 }}
          className="flex flex-col sm:flex-row gap-3"
        >
          <Link
            href="/docs"
            className="flex-1 py-3 text-center text-sm text-slate-400 border border-[rgba(255,255,255,0.08)] rounded-lg hover:border-[rgba(0,212,170,0.2)] hover:text-white transition-all"
          >
            Read the docs →
          </Link>
          <Link
            href="/onboarding"
            className="flex-1 py-3 text-center text-sm text-slate-400 border border-[rgba(255,255,255,0.08)] rounded-lg hover:border-[rgba(0,212,170,0.2)] hover:text-white transition-all"
          >
            Create another key →
          </Link>
        </motion.div>
      </div>
    </div>
  );
}

// ── Wrapper (handles URL key param + localStorage) ────────────────────────────

function DashboardWrapper() {
  const searchParams = useSearchParams();
  const [resolvedKey, setResolvedKey] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const paramKey = searchParams.get("key");
    if (paramKey) {
      localStorage.setItem("ao_key", paramKey);
      setResolvedKey(paramKey);
    } else {
      const stored = localStorage.getItem("ao_key");
      setResolvedKey(stored);
    }
    setChecked(true);
  }, [searchParams]);

  if (!checked) return null;
  if (!resolvedKey) return <NoKeyState />;
  return <DashboardContent apiKey={resolvedKey} />;
}

// ── Root ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#0a0a0f] text-white flex items-center justify-center">
          <Loader2 size={20} className="animate-spin text-slate-400" />
        </div>
      }
    >
      <DashboardWrapper />
    </Suspense>
  );
}
