"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import {
  Bot,
  TrendingUp,
  Zap,
  DollarSign,
  Shield,
  BarChart3,
  Github,
  Twitter,
  RefreshCw,
  CheckCircle,
  AlertCircle,
} from "lucide-react";

const AO_BASE = "https://agentoptima.ai/api/v1";

// ── Types ─────────────────────────────────────────────────────────────────────

interface StatusData {
  tasks_logged: number;
  tasks_success: number;
  models_tracked: number;
  version: string;
  last_task_at: string;
}

interface RankingRow {
  model: string;
  category: string;
  tasks_logged: number;
  success_rate: number;
  avg_duration: number;
  avg_cost_cents: number | null;
}

interface RecommendData {
  recommended_model: string;
  success_rate: number;
  avg_cost_cents: number;
  based_on_tasks: number;
  mode: string;
  task_type: string;
}

interface RegistryModel {
  model: string;
  cost: number;
  tier: string;
  speed: string;
  strength: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function shortModel(m: string): string {
  return m.split("/").pop() || m;
}

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function fmtCost(v: number | null): string {
  if (v == null) return "—";
  return `$${(v / 100).toFixed(4)}`;
}

function tierBadge(tier: string): string {
  const map: Record<string, string> = {
    ultra_cheap: "bg-green-900/50 text-green-400",
    cheap: "bg-blue-900/50 text-blue-400",
    mid: "bg-yellow-900/50 text-yellow-400",
    quality: "bg-purple-900/50 text-purple-400",
    oracle: "bg-red-900/50 text-red-400",
  };
  return map[tier] || "bg-slate-800 text-slate-400";
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Home() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [rankings, setRankings] = useState<RankingRow[]>([]);
  const [recommend, setRecommend] = useState<RecommendData | null>(null);
  const [registry, setRegistry] = useState<RegistryModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, rankRes, recRes, regRes] = await Promise.all([
        fetch(`${AO_BASE}/status`),
        fetch(`${AO_BASE}/rankings`),
        fetch(`${AO_BASE}/recommend?task_type=general&min_tasks=100`),
        fetch(`${AO_BASE}/registry`),
      ]);

      if (statusRes.ok) setStatus(await statusRes.json());
      if (rankRes.ok) {
        const d = await rankRes.json();
        // Top 8 rows by tasks_logged, unique model+category combos
        setRankings((d.models || []).slice(0, 8));
      }
      if (recRes.ok) setRecommend(await recRes.json());
      if (regRes.ok) {
        const d = await regRes.json();
        setRegistry(d.models || []);
      }
      setLastRefresh(new Date());
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "fetch error";
      setError(`API unreachable: ${message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    // Auto-refresh every 60 seconds
    const interval = setInterval(fetchAll, 60_000);
    return () => clearInterval(interval);
  }, []);

  // ── Stats derived from live data ──────────────────────────────────────────
  const totalTasks = status?.tasks_logged ?? 0;
  const successRate = status
    ? ((status.tasks_success / Math.max(status.tasks_logged, 1)) * 100).toFixed(1)
    : "—";
  const modelsTracked = status?.models_tracked ?? 0;

  // Cost saved: difference between running everything on Sonnet vs recommended routing
  // Rough estimate: tasks_logged × (Sonnet cost − avg recommended cost)
  const sonnetCost = 0.00689; // $ per task from registry
  const avgCheapCost = recommend ? recommend.avg_cost_cents / 100 : 0.00034;
  const costSavedRaw = totalTasks * Math.max(0, sonnetCost - avgCheapCost);
  const costSavedDisplay =
    costSavedRaw > 1000
      ? `$${(costSavedRaw / 1000).toFixed(1)}K`
      : `$${costSavedRaw.toFixed(0)}`;

  const statsItems = [
    {
      icon: Bot,
      label: "Tasks Tracked",
      value: totalTasks > 1000 ? `${(totalTasks / 1000).toFixed(1)}K` : String(totalTasks),
      sub: `${successRate}% success`,
    },
    {
      icon: TrendingUp,
      label: "Models Ranked",
      value: String(modelsTracked),
      sub: "live registry",
    },
    {
      icon: DollarSign,
      label: "Est. Cost Saved",
      value: costSavedDisplay,
      sub: "vs all-Sonnet",
    },
    {
      icon: Zap,
      label: "Best General Model",
      value: recommend ? shortModel(recommend.recommended_model) : "—",
      sub: recommend ? `${fmtPct(recommend.success_rate)} sr` : "loading…",
    },
  ];

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="relative overflow-hidden py-20 px-4">
        <div className="max-w-6xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary/10 text-primary rounded-full text-sm font-medium mb-6">
              <Zap className="w-4 h-4" />
              <span>Powered by real agent data</span>
            </div>

            <h1 className="text-5xl md:text-7xl font-bold mb-6">
              Agent<span className="gradient-text">Optima</span>
            </h1>

            <p className="text-xl md:text-2xl text-slate-400 mb-8 max-w-3xl mx-auto leading-relaxed">
              The self-improving intelligence network. Track AI model performance,
              cost efficiency, and rankings from real-world agent operations.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-12">
              <a
                href="https://agentoptima.ai/api/v1/registry"
                target="_blank"
                rel="noopener noreferrer"
                className="button-primary text-lg px-8 py-3"
              >
                Browse API
              </a>
              <a
                href="https://github.com/arisauraaudit/agentoptima"
                className="px-8 py-3 text-slate-300 hover:text-white transition-colors font-medium"
              >
                View on GitHub
              </a>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Live Stats */}
      <section className="py-12 px-4 border-y border-slate-800">
        <div className="max-w-6xl mx-auto">
          {error && (
            <div className="flex items-center gap-2 text-red-400 text-sm mb-6 justify-center">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            {statsItems.map((stat, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                className="text-center"
              >
                <stat.icon className="w-8 h-8 text-primary mx-auto mb-3" />
                <div className="text-3xl font-bold mb-1">
                  {loading ? (
                    <span className="text-slate-600 animate-pulse">…</span>
                  ) : (
                    stat.value
                  )}
                </div>
                <div className="text-slate-400 text-sm mb-1">{stat.label}</div>
                <div className="text-slate-500 text-xs">{stat.sub}</div>
              </motion.div>
            ))}
          </div>

          {lastRefresh && (
            <div className="flex items-center justify-center gap-2 mt-6 text-slate-600 text-xs">
              <CheckCircle className="w-3 h-3 text-green-600" />
              Live data · refreshed {lastRefresh.toLocaleTimeString()}
              <button onClick={fetchAll} className="ml-2 hover:text-slate-400 transition-colors">
                <RefreshCw className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>
      </section>

      {/* AI Recommendations — live from /api/v1/recommend */}
      <section className="py-20 px-4">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
            AI <span className="gradient-text">Recommendations</span>
          </h2>
          <p className="text-slate-400 text-center mb-12">
            Live routing decisions from AgentOptima — updated on every task
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {["general", "coding", "research", "writing", "data", "strategy"].map((taskType, i) => (
              <RecommendCard key={taskType} taskType={taskType} delay={i * 0.1} />
            ))}
          </div>
        </div>
      </section>

      {/* Routing Gate — live from /api/v1/registry */}
      <section className="py-20 px-4 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
            Routing <span className="gradient-text">Gate</span>
          </h2>
          <p className="text-slate-400 text-center mb-12">
            Full model registry — risk tiers, costs, and capabilities
          </p>

          <div className="card p-6 overflow-x-auto">
            {loading ? (
              <div className="text-slate-600 text-center py-8 animate-pulse">Loading registry…</div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Model</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Tier</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Cost/task</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Speed</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Strength</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {registry.map((row, i) => (
                    <motion.tr
                      key={i}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.05 }}
                      className="border-b border-slate-700/50 hover:bg-primary/5 transition-colors"
                    >
                      <td className="py-3 px-4 font-medium font-mono text-xs">
                        {shortModel(row.model)}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${tierBadge(row.tier)}`}>
                          {row.tier}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        ${row.cost.toFixed(3)}¢
                      </td>
                      <td className="py-3 px-4 text-slate-400">{row.speed}</td>
                      <td className="py-3 px-4 text-slate-400 max-w-xs truncate">
                        {row.strength}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </section>

      {/* Live Rankings — from /api/v1/rankings */}
      <section className="py-20 px-4">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
            Live <span className="gradient-text">Rankings</span>
          </h2>
          <p className="text-slate-400 text-center mb-12">
            Real agent performance data · top models by category
          </p>

          <div className="card p-6 overflow-x-auto">
            {loading ? (
              <div className="text-slate-600 text-center py-8 animate-pulse">Loading rankings…</div>
            ) : rankings.length === 0 ? (
              <div className="text-slate-600 text-center py-8">No ranking data yet.</div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Model</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Category</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Tasks</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Success Rate</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Avg Duration</th>
                    <th className="text-left py-3 px-4 font-medium text-slate-300">Avg Cost</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {rankings.map((row, i) => (
                    <motion.tr
                      key={i}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.06 }}
                      className="border-b border-slate-700/50 hover:bg-primary/5 transition-colors"
                    >
                      <td className="py-3 px-4 font-medium font-mono text-xs">
                        {shortModel(row.model)}
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-1 bg-primary/10 text-primary rounded text-xs">
                          {row.category}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-300">{row.tasks_logged}</td>
                      <td className="py-3 px-4 text-green-400">
                        {fmtPct(row.success_rate)}
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {row.avg_duration ? `${row.avg_duration.toFixed(1)}s` : "—"}
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {fmtCost(row.avg_cost_cents)}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="text-center mt-8">
            <a
              href={`${AO_BASE}/rankings`}
              target="_blank"
              rel="noopener noreferrer"
              className="button-primary"
            >
              Full Rankings JSON
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-4 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-12">
            Why <span className="gradient-text">AgentOptima</span>?
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                icon: BarChart3,
                title: "Real Performance Data",
                description: "Metrics from actual agent operations, not synthetic benchmarks.",
                color: "text-blue-400",
              },
              {
                icon: TrendingUp,
                title: "Live Rankings",
                description: "Models ranked by use case, updated automatically with new data.",
                color: "text-green-400",
              },
              {
                icon: DollarSign,
                title: "Cost Optimization",
                description: "Identify the most cost-effective models for your specific needs.",
                color: "text-purple-400",
              },
              {
                icon: Shield,
                title: "Risk Gate",
                description: "Pre-flight security scan before every spawn — zero-cost keyword heuristic.",
                color: "text-red-400",
              },
              {
                icon: Zap,
                title: "API Access",
                description: "Integrate AgentOptima rankings and routing into your applications.",
                color: "text-yellow-400",
              },
              {
                icon: Github,
                title: "Open Data",
                description: "Rankings + registry published via REST API for the community.",
                color: "text-pink-400",
              },
            ].map((feature, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                className="card p-6 hover:border-primary/50 transition-colors"
              >
                <feature.icon className={`w-10 h-10 ${feature.color} mb-4`} />
                <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
                <p className="text-slate-400">{feature.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-4 text-center">
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          Start Optimizing Your AI Stack
        </h2>
        <p className="text-slate-400 mb-8 max-w-2xl mx-auto">
          Join agents already using AgentOptima to track performance and save costs.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <a
            href={`${AO_BASE}/registry`}
            target="_blank"
            rel="noopener noreferrer"
            className="button-primary text-lg px-8 py-3"
          >
            Get Started Free
          </a>
          <a
            href="https://github.com/arisauraaudit/agentoptima"
            target="_blank"
            rel="noopener noreferrer"
            className="px-8 py-3 bg-slate-800 hover:bg-slate-700 transition-colors rounded-lg font-medium"
          >
            View on GitHub
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-4 border-t border-slate-800">
        <div className="max-w-6xl mx-auto text-center text-slate-400">
          <p className="mb-4">
            Built by{" "}
            <a
              href="https://twitter.com/arisauraaudit"
              className="text-primary hover:text-green-400 transition-colors"
            >
              @arisauraaudit
            </a>{" "}
            · Data from real agent operations · v{status?.version ?? "1.0.0"}
          </p>
          <div className="flex justify-center gap-6">
            <a
              href="https://github.com/arisauraaudit/agentoptima"
              className="hover:text-white transition-colors"
            >
              <Github className="w-6 h-6" />
            </a>
            <a
              href="https://twitter.com/agentoptima"
              className="hover:text-blue-400 transition-colors"
            >
              <Twitter className="w-6 h-6" />
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

// ── RecommendCard — fetches /recommend for a single task type ─────────────────

function RecommendCard({ taskType, delay }: { taskType: string; delay: number }) {
  const [data, setData] = useState<RecommendData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${AO_BASE}/recommend?task_type=${taskType}&min_tasks=50`)
      .then((r) => r.json())
      .then((d) => {
        if (d.recommended_model) setData(d);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [taskType]);

  const modeColor =
    data?.mode === "data-driven"
      ? "text-green-400"
      : data?.mode === "fallback"
      ? "text-yellow-400"
      : "text-slate-500";

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay }}
      className="card p-5 hover:border-primary/40 transition-colors"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium px-2 py-1 bg-primary/10 text-primary rounded capitalize">
          {taskType}
        </span>
        {data && (
          <span className={`text-xs ${modeColor}`}>
            {data.mode === "data-driven" ? "● live" : "○ fallback"}
          </span>
        )}
      </div>

      {loading ? (
        <div className="animate-pulse text-slate-700 text-sm">Loading…</div>
      ) : data ? (
        <>
          <div className="text-lg font-bold mb-1 font-mono text-sm">
            {shortModel(data.recommended_model)}
          </div>
          <div className="text-slate-400 text-xs space-y-1">
            <div>
              Success rate:{" "}
              <span className="text-green-400">{fmtPct(data.success_rate)}</span>
            </div>
            <div>
              Avg cost:{" "}
              <span className="text-slate-300">{fmtCost(data.avg_cost_cents)}</span>
            </div>
            <div>
              Based on:{" "}
              <span className="text-slate-300">{data.based_on_tasks.toLocaleString()} tasks</span>
            </div>
          </div>
        </>
      ) : (
        <div className="text-slate-600 text-xs">No data yet for {taskType}</div>
      )}
    </motion.div>
  );
}
