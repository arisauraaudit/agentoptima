"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Zap, Github, ArrowRight, ChevronDown, Shield, Database, Link2 } from "lucide-react";
import Link from "next/link";

const AO_BASE = "https://agentoptima.ai";

interface StatusData {
  tasks_logged: number;
  models_tracked: number;
  version?: string;
}

const FALLBACK: StatusData = {
  tasks_logged: 416000,
  models_tracked: 16,
};

function NavBar() {
  return (
    <nav className="border-b border-[rgba(0,212,170,0.1)] px-6 py-4 flex items-center justify-between sticky top-0 z-50 bg-[#0a0a0f]/80 backdrop-blur-xl">
      <div className="flex items-center gap-2">
        <Zap size={18} className="text-[#00d4aa]" />
        <span className="font-bold text-base tracking-tight">AgentOptima</span>
      </div>
      <div className="flex items-center gap-4">
        <Link href="/docs" className="text-sm text-slate-400 hover:text-white transition-colors hidden sm:block">
          Docs
        </Link>
        <a
          href="https://github.com/arisauraaudit/agentoptima"
          target="_blank"
          rel="noopener noreferrer"
          className="text-slate-400 hover:text-white transition-colors"
        >
          <Github size={17} />
        </a>
        <Link
          href="/onboarding"
          className="button-primary text-sm px-4 py-2"
          style={{ borderRadius: "8px" }}
        >
          Get API key
        </Link>
      </div>
    </nav>
  );
}

export default function LandingPage() {
  const [status, setStatus] = useState<StatusData | null>(null);

  useEffect(() => {
    fetch(`${AO_BASE}/api/v1/status`)
      .then((r) => r.json())
      .then((d: StatusData) => setStatus(d))
      .catch(() => setStatus(FALLBACK));
  }, []);

  const stats = status ?? FALLBACK;
  const requestsStr =
    stats.tasks_logged >= 1000
      ? `${(stats.tasks_logged / 1000).toFixed(0)}K`
      : stats.tasks_logged.toLocaleString();

  return (
    <div className="min-h-screen bg-[#0a0a0f] bg-grid text-white">
      <NavBar />

      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <section className="relative max-w-5xl mx-auto px-6 pt-24 pb-16 text-center">
        {/* Glow blob */}
        <div
          className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] rounded-full pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse at center, rgba(0,212,170,0.08) 0%, transparent 70%)",
            filter: "blur(40px)",
          }}
        />

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55 }}
          className="relative z-10"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[rgba(0,212,170,0.25)] bg-[rgba(0,212,170,0.06)] text-[#00d4aa] text-xs font-medium mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00d4aa] animate-pulse" />
            Live — {requestsStr} requests routed
          </div>

          <h1 className="text-5xl sm:text-7xl font-black tracking-tight leading-[1.05] mb-6">
            Stop overpaying
            <br />
            <span className="gradient-text">for AI.</span>
          </h1>

          <p className="text-slate-400 text-lg sm:text-xl max-w-2xl mx-auto mb-10 leading-relaxed">
            One line of code. AgentOptima routes every request to the cheapest capable model
            and caches repeated work — automatically.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/onboarding"
              className="button-primary inline-flex items-center gap-2 px-7 py-3.5 text-base"
              style={{ borderRadius: "10px" }}
            >
              Get your free API key <ArrowRight size={16} />
            </Link>
            <a
              href="#how-it-works"
              className="inline-flex items-center gap-2 px-7 py-3.5 text-base text-slate-300 hover:text-white border border-[rgba(255,255,255,0.1)] hover:border-[rgba(0,212,170,0.3)] rounded-[10px] transition-all"
            >
              See how it works <ChevronDown size={16} />
            </a>
          </div>
        </motion.div>
      </section>

      {/* ── Social proof bar ──────────────────────────────────────────── */}
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="border-y border-[rgba(0,212,170,0.08)] py-4"
      >
        <div className="max-w-3xl mx-auto px-6">
          <div className="flex flex-wrap items-center justify-center gap-6 text-sm text-slate-500">
            <span>
              <span className="text-white font-semibold font-mono">{requestsStr}</span> requests routed
            </span>
            <span className="text-slate-700">•</span>
            <span>
              <span className="text-white font-semibold font-mono">{stats.models_tracked}</span> models available
            </span>
            <span className="text-slate-700">•</span>
            <span>
              <span className="text-[#00d4aa] font-semibold">$0</span> surprise bills
            </span>
          </div>
        </div>
      </motion.section>

      {/* ── How it works ──────────────────────────────────────────────── */}
      <section id="how-it-works" className="max-w-5xl mx-auto px-6 py-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center mb-14"
        >
          <h2 className="text-3xl sm:text-4xl font-black tracking-tight mb-3">
            How it works
          </h2>
          <p className="text-slate-400">Three steps. Zero architecture changes.</p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {[
            {
              num: "01",
              title: "Connect",
              desc: "Change base_url to agentoptima.ai/v1. That's it. Your existing OpenAI client works exactly the same.",
              accent: "#00d4aa",
            },
            {
              num: "02",
              title: "Route",
              desc: "Every request auto-routed to cheapest capable model using 416K real benchmarks. No config needed.",
              accent: "#00d4aa",
            },
            {
              num: "03",
              title: "Save",
              desc: "Cache hits cost $0. Smart routing is 8x cheaper than GPT-4o on average. Watch savings stack up.",
              accent: "#00d4aa",
            },
          ].map((step, i) => (
            <motion.div
              key={step.num}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.12, duration: 0.45 }}
              className="card p-7 relative overflow-hidden group hover:border-[rgba(0,212,170,0.25)] transition-colors"
            >
              <div className="text-5xl font-black text-[rgba(0,212,170,0.08)] mb-4 font-mono">
                {step.num}
              </div>
              <div className="text-lg font-bold mb-2">{step.title}</div>
              <div className="text-sm text-slate-400 leading-relaxed">{step.desc}</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Code preview ──────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="card-glow overflow-hidden"
        >
          <div className="flex items-center gap-2 px-5 py-3 border-b border-[rgba(0,212,170,0.1)]">
            <div className="w-3 h-3 rounded-full bg-red-500/60" />
            <div className="w-3 h-3 rounded-full bg-yellow-500/60" />
            <div className="w-3 h-3 rounded-full bg-green-500/60" />
            <span className="ml-2 text-xs text-slate-500 font-mono">your_app.py</span>
          </div>
          <pre className="text-sm p-6 overflow-x-auto leading-7">
            <code>
              <span className="text-slate-500"># Before — paying full GPT-4o price</span>
              {"\n"}
              <span className="text-slate-300">client = OpenAI(</span>
              {"\n"}
              <span className="text-slate-300">    api_key=</span>
              <span className="text-amber-300">&quot;sk-...&quot;</span>
              {"\n"}
              <span className="text-slate-500 line-through opacity-60">    # base_url not set → goes to OpenAI directly</span>
              {"\n"}
              <span className="text-slate-300">)</span>
              {"\n\n"}
              <span className="text-[#00d4aa]"># After — automatic routing + caching</span>
              {"\n"}
              <span className="text-slate-300">client = OpenAI(</span>
              {"\n"}
              <span className="text-slate-300">    api_key=</span>
              <span className="text-amber-300">&quot;ao-your-key&quot;</span>
              <span className="text-slate-500">,</span>
              {"\n"}
              <span className="text-slate-300">    base_url=</span>
              <span className="text-[#00d4aa]">&quot;https://agentoptima.ai/v1&quot;</span>
              {"\n"}
              <span className="text-slate-300">)</span>
              {"\n"}
              <span className="text-slate-500"># Everything else stays the same ↑</span>
            </code>
          </pre>
        </motion.div>
      </section>

      {/* ── Why AgentOptima ───────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center mb-14"
        >
          <h2 className="text-3xl sm:text-4xl font-black tracking-tight mb-3">
            Why AgentOptima
          </h2>
          <p className="text-slate-400">Built for production teams who care about cost.</p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {[
            {
              icon: <Link2 size={20} className="text-[#00d4aa]" />,
              title: "No vendor lock-in",
              desc: "Works with any OpenAI-compatible client — LangChain, LlamaIndex, AutoGen, your own code. Zero lock-in.",
            },
            {
              icon: <Shield size={20} className="text-[#00d4aa]" />,
              title: "Hard budget limits",
              desc: "We stop calls before you hit your limit. No surprise bills. Hard ceiling, not a soft warning. Update anytime.",
            },
            {
              icon: <Database size={20} className="text-[#00d4aa]" />,
              title: "Real data",
              desc: "Routing powered by 416K actual benchmark results — not marketing claims. The cheapest model that gets the job done.",
            },
          ].map((item, i) => (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.45 }}
              className="card p-7 hover:border-[rgba(0,212,170,0.25)] transition-colors"
            >
              <div className="w-10 h-10 rounded-lg bg-[rgba(0,212,170,0.08)] flex items-center justify-center mb-4">
                {item.icon}
              </div>
              <div className="font-bold mb-2">{item.title}</div>
              <div className="text-sm text-slate-400 leading-relaxed">{item.desc}</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="card-glow p-12 text-center relative overflow-hidden"
        >
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background:
                "radial-gradient(ellipse at 50% 0%, rgba(0,212,170,0.07) 0%, transparent 70%)",
            }}
          />
          <h2 className="text-3xl sm:text-4xl font-black tracking-tight mb-4 relative z-10">
            Start saving today.
          </h2>
          <p className="text-slate-400 mb-8 relative z-10">
            Free to start. No credit card required. API key in 10 seconds.
          </p>
          <Link
            href="/onboarding"
            className="button-primary inline-flex items-center gap-2 px-8 py-4 text-base relative z-10"
            style={{ borderRadius: "10px" }}
          >
            Get your free API key <ArrowRight size={16} />
          </Link>
        </motion.div>
      </section>

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <footer className="border-t border-[rgba(0,212,170,0.08)] py-8">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-slate-500">
          <div className="flex items-center gap-2">
            <Zap size={14} className="text-[#00d4aa]" />
            <span>AgentOptima</span>
          </div>
          <div className="flex items-center gap-6">
            <Link href="/docs" className="hover:text-slate-300 transition-colors">
              Docs
            </Link>
            <Link href="/dashboard" className="hover:text-slate-300 transition-colors">
              Dashboard
            </Link>
            <a
              href="https://github.com/arisauraaudit/agentoptima"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-slate-300 transition-colors flex items-center gap-1"
            >
              <Github size={14} /> GitHub
            </a>
          </div>
          <div>Built by Aris</div>
        </div>
      </footer>
    </div>
  );
}
