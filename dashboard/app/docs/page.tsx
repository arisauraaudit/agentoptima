"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Zap, Copy, Check, ChevronRight } from "lucide-react";
import Link from "next/link";

// ── Helpers ───────────────────────────────────────────────────────────────────

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

function CodeBlock({ code, lang }: { code: string; lang?: string }) {
  return (
    <div className="card overflow-hidden my-3">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[rgba(0,212,170,0.08)]">
        {lang && <span className="text-xs text-slate-500 font-mono">{lang}</span>}
        <div className="ml-auto">
          <CopyButton text={code} />
        </div>
      </div>
      <pre className="text-xs text-slate-300 p-4 overflow-x-auto leading-relaxed font-mono">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function Section({
  id,
  title,
  children,
  delay = 0,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
  delay?: number;
}) {
  return (
    <motion.section
      id={id}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.45, delay }}
      className="mb-16"
    >
      <h2 className="text-2xl font-black tracking-tight mb-6 pb-3 border-b border-[rgba(0,212,170,0.1)]">
        {title}
      </h2>
      {children}
    </motion.section>
  );
}

function Param({
  name,
  type,
  required,
  desc,
}: {
  name: string;
  type: string;
  required?: boolean;
  desc: string;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start gap-2 sm:gap-4 py-3 border-b border-[rgba(255,255,255,0.04)] last:border-0">
      <div className="flex items-center gap-2 sm:w-48 flex-shrink-0">
        <code className="text-[#00d4aa] text-xs font-mono">{name}</code>
        {required && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[rgba(0,212,170,0.1)] text-[#00d4aa] font-medium">
            required
          </span>
        )}
      </div>
      <div className="flex-1">
        <div className="text-xs text-slate-500 font-mono mb-0.5">{type}</div>
        <div className="text-sm text-slate-300 leading-relaxed">{desc}</div>
      </div>
    </div>
  );
}

function EndpointBadge({ method }: { method: string }) {
  const colors: Record<string, string> = {
    GET: "bg-blue-500/15 text-blue-300 border-blue-500/20",
    POST: "bg-green-500/15 text-green-300 border-green-500/20",
    PUT: "bg-amber-500/15 text-amber-300 border-amber-500/20",
  };
  return (
    <span className={`text-xs font-bold font-mono px-2 py-0.5 rounded border ${colors[method] || ""}`}>
      {method}
    </span>
  );
}

// ── Nav TOC ───────────────────────────────────────────────────────────────────

const TOC = [
  { id: "quickstart", label: "Quick Start" },
  { id: "api-reference", label: "API Reference" },
  { id: "model-selection", label: "Model Selection" },
  { id: "cache-control", label: "Cache Control" },
  { id: "budget-limits", label: "Budget Limits" },
];

// ── Snippets ──────────────────────────────────────────────────────────────────

const QS_STEP1 = `pip install openai`;

const QS_STEP2 = `# 1. Get your key at https://agentoptima.ai/onboarding

# 2. Set your env variable
export AGENTOPTIMA_API_KEY="ao-your-key-here"`;

const QS_STEP3 = `from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["AGENTOPTIMA_API_KEY"],
    base_url="https://agentoptima.ai/v1"
)

response = client.chat.completions.create(
    model="auto",   # ← AgentOptima picks cheapest capable model
    messages=[{"role": "user", "content": "Summarize this article in 3 bullets."}]
)

print(response.choices[0].message.content)
# response.model → which model was used
# response.usage.total_cost_cents → actual cost`;

const CHAT_REQUEST = `POST /v1/chat/completions
Authorization: Bearer ao-your-key
Content-Type: application/json

{
  "model": "auto",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 500
}`;

const CHAT_RESPONSE = `{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "gpt-4o-mini",       // ← actual model used
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hi! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21,
    "total_cost_cents": 0.003    // ← actual cost
  }
}`;

const KEYS_CREATE = `POST /api/v1/keys/create
Content-Type: application/json

{
  "label": "my-app",
  "budget_limit_cents": 500,
  "email": "you@example.com"    // optional, for recovery
}

// Response
{
  "key": "ao-xxxxxxxxxxxxxxxxxxxxxxxx",
  "label": "my-app",
  "budget_limit_cents": 500,
  "created_at": "2025-01-01T00:00:00Z"
}`;

const KEYS_STATUS = `GET /api/v1/keys/status
Authorization: Bearer ao-your-key

// Response
{
  "label": "my-app",
  "plan": "free",
  "budget_limit_usd": 5.00,
  "budget_remaining_usd": 4.85,
  "spent_total_cents": 15,
  "last_30_days": {
    "spent_cents": 15,
    "saved_cents": 120,
    "saved_usd": 1.20,
    "cache_hit_count": 42,
    "cache_saved_cents": 80,
    "routing_saved_cents": 40
  },
  "enabled": true
}`;

const KEYS_BUDGET = `PUT /api/v1/keys/budget
Authorization: Bearer ao-your-key
Content-Type: application/json

{
  "budget_limit_cents": 5000    // $50.00 new limit
}

// Response
{
  "label": "my-app",
  "budget_limit_usd": 50.00,
  "budget_remaining_usd": 49.85
}`;

const MODEL_EXAMPLES = `// Let AgentOptima decide (recommended)
{ "model": "auto" }

// Pin to a specific model
{ "model": "gpt-4o" }
{ "model": "gpt-4o-mini" }
{ "model": "claude-3-5-sonnet-20241022" }
{ "model": "claude-3-haiku-20240307" }
{ "model": "gemini-1.5-pro" }
{ "model": "llama-3.1-70b-versatile" }`;

const CACHE_EXAMPLES = `// Default: cache is enabled
{ "model": "auto", "messages": [...] }

// Disable cache for this request
// Add header: X-AO-Cache: false
curl https://agentoptima.ai/v1/chat/completions \\
  -H "Authorization: Bearer ao-your-key" \\
  -H "X-AO-Cache: false" \\
  -H "Content-Type: application/json" \\
  -d '{"model": "auto", "messages": [...]}'`;

const BUDGET_UPDATE = `// Update your budget limit anytime
curl -X PUT https://agentoptima.ai/api/v1/keys/budget \\
  -H "Authorization: Bearer ao-your-key" \\
  -H "Content-Type: application/json" \\
  -d '{"budget_limit_cents": 10000}'    // $100 new limit`;

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DocsPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0f] bg-grid text-white">
      {/* Nav */}
      <nav className="border-b border-[rgba(0,212,170,0.1)] px-6 py-4 sticky top-0 z-50 bg-[#0a0a0f]/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Zap size={18} className="text-[#00d4aa]" />
            <span className="font-bold text-base tracking-tight">AgentOptima</span>
            <span className="text-slate-600">/</span>
            <span className="text-slate-400 text-sm">Docs</span>
          </Link>
          <Link
            href="/onboarding"
            className="button-primary text-sm px-4 py-2"
            style={{ borderRadius: "8px" }}
          >
            Get API key
          </Link>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-6 py-10 flex gap-10">
        {/* Sidebar TOC */}
        <aside className="hidden lg:block w-52 flex-shrink-0">
          <div className="sticky top-24">
            <div className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-4">
              On this page
            </div>
            <nav className="space-y-1">
              {TOC.map((item) => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className="flex items-center gap-2 text-sm text-slate-400 hover:text-white py-1.5 hover:text-[#00d4aa] transition-colors"
                >
                  <ChevronRight size={12} className="text-slate-600" />
                  {item.label}
                </a>
              ))}
            </nav>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 max-w-3xl">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-12"
          >
            <h1 className="text-4xl font-black tracking-tight mb-3">Documentation</h1>
            <p className="text-slate-400 text-lg">
              Everything you need to start routing AI requests through AgentOptima.
            </p>
          </motion.div>

          {/* ── Quick Start ─────────────────────────────────────────── */}
          <Section id="quickstart" title="Quick Start" delay={0.1}>
            <p className="text-slate-400 mb-6 leading-relaxed">
              Three steps from zero to optimized AI requests.
            </p>

            <div className="space-y-6">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-6 h-6 rounded-full bg-[rgba(0,212,170,0.15)] text-[#00d4aa] text-xs font-bold flex items-center justify-center">1</span>
                  <span className="text-sm font-semibold">Install the OpenAI SDK</span>
                </div>
                <CodeBlock code={QS_STEP1} lang="bash" />
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-6 h-6 rounded-full bg-[rgba(0,212,170,0.15)] text-[#00d4aa] text-xs font-bold flex items-center justify-center">2</span>
                  <span className="text-sm font-semibold">Get your API key</span>
                </div>
                <CodeBlock code={QS_STEP2} lang="bash" />
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-6 h-6 rounded-full bg-[rgba(0,212,170,0.15)] text-[#00d4aa] text-xs font-bold flex items-center justify-center">3</span>
                  <span className="text-sm font-semibold">Make your first optimized request</span>
                </div>
                <CodeBlock code={QS_STEP3} lang="python" />
              </div>
            </div>

            <div className="mt-6 p-4 bg-[rgba(0,212,170,0.04)] border border-[rgba(0,212,170,0.15)] rounded-lg text-sm text-slate-300">
              <span className="text-[#00d4aa] font-semibold">That&apos;s it.</span> Your existing code works unchanged — just swap the{" "}
              <code className="text-[#00d4aa] bg-[rgba(0,212,170,0.08)] px-1 rounded">base_url</code> and{" "}
              <code className="text-[#00d4aa] bg-[rgba(0,212,170,0.08)] px-1 rounded">api_key</code>.
              AgentOptima handles everything else automatically.
            </div>
          </Section>

          {/* ── API Reference ────────────────────────────────────────── */}
          <Section id="api-reference" title="API Reference" delay={0.1}>
            <p className="text-slate-400 mb-8 leading-relaxed">
              Base URL: <code className="text-[#00d4aa] bg-[rgba(0,212,170,0.08)] px-2 py-0.5 rounded text-sm">https://agentoptima.ai</code>
            </p>

            {/* POST /v1/chat/completions */}
            <div className="mb-10">
              <div className="flex items-center gap-3 mb-3">
                <EndpointBadge method="POST" />
                <code className="text-sm font-mono text-white">/v1/chat/completions</code>
              </div>
              <p className="text-sm text-slate-400 mb-4">
                OpenAI-compatible chat completions endpoint. Drop-in replacement — same request/response format.
              </p>

              <div className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-2 mt-5">Request</div>
              <div className="card p-4 mb-2">
                <Param name="model" type="string" required desc='Model to use. Pass "auto" for automatic cheapest-capable routing, or an explicit model name.' />
                <Param name="messages" type="array" required desc="Array of message objects with role and content fields. Standard OpenAI format." />
                <Param name="temperature" type="number" desc="Sampling temperature 0–2. Default: 1." />
                <Param name="max_tokens" type="integer" desc="Maximum tokens to generate. Default: model maximum." />
                <Param name="stream" type="boolean" desc="Stream partial responses via SSE. Default: false." />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
                <div>
                  <div className="text-xs text-slate-500 mb-1">Request example</div>
                  <CodeBlock code={CHAT_REQUEST} lang="http" />
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">Response example</div>
                  <CodeBlock code={CHAT_RESPONSE} lang="json" />
                </div>
              </div>
            </div>

            {/* POST /api/v1/keys/create */}
            <div className="mb-10">
              <div className="flex items-center gap-3 mb-3">
                <EndpointBadge method="POST" />
                <code className="text-sm font-mono text-white">/api/v1/keys/create</code>
              </div>
              <p className="text-sm text-slate-400 mb-4">
                Create a new API key with a hard budget limit. No authentication required.
              </p>
              <div className="card p-4 mb-3">
                <Param name="label" type="string" required desc="Human-readable name for this key (e.g. my-app, production)." />
                <Param name="budget_limit_cents" type="integer" required desc="Hard spending limit in cents. Requests stop when this is reached. e.g. 500 = $5.00" />
                <Param name="email" type="string" desc="Optional email for key recovery." />
              </div>
              <CodeBlock code={KEYS_CREATE} lang="http" />
            </div>

            {/* GET /api/v1/keys/status */}
            <div className="mb-10">
              <div className="flex items-center gap-3 mb-3">
                <EndpointBadge method="GET" />
                <code className="text-sm font-mono text-white">/api/v1/keys/status</code>
              </div>
              <p className="text-sm text-slate-400 mb-4">
                Get current key status, budget remaining, and 30-day savings summary.
              </p>
              <CodeBlock code={KEYS_STATUS} lang="http" />
            </div>

            {/* PUT /api/v1/keys/budget */}
            <div className="mb-4">
              <div className="flex items-center gap-3 mb-3">
                <EndpointBadge method="PUT" />
                <code className="text-sm font-mono text-white">/api/v1/keys/budget</code>
              </div>
              <p className="text-sm text-slate-400 mb-4">
                Update the budget limit for an existing key.
              </p>
              <div className="card p-4 mb-3">
                <Param name="budget_limit_cents" type="integer" required desc="New hard spending limit in cents. Must be ≥ 1." />
              </div>
              <CodeBlock code={KEYS_BUDGET} lang="http" />
            </div>
          </Section>

          {/* ── Model Selection ──────────────────────────────────────── */}
          <Section id="model-selection" title="Model Selection" delay={0.1}>
            <p className="text-slate-400 mb-5 leading-relaxed">
              AgentOptima uses 416K real benchmark results to route each request to the cheapest model
              capable of handling it well.
            </p>

            <div className="space-y-4 mb-6">
              <div className="card p-5">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-[rgba(0,212,170,0.08)] flex items-center justify-center flex-shrink-0">
                    <Zap size={14} className="text-[#00d4aa]" />
                  </div>
                  <div>
                    <div className="font-semibold mb-1">
                      <code className="text-[#00d4aa]">&quot;model&quot;: &quot;auto&quot;</code> — Recommended
                    </div>
                    <div className="text-sm text-slate-400 leading-relaxed">
                      AgentOptima analyzes your prompt and routes to the cheapest model that achieves
                      high quality on similar tasks. Simple prompts get cheap fast models.
                      Complex reasoning gets powerful models. You pay less for everything.
                    </div>
                  </div>
                </div>
              </div>

              <div className="card p-5">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-[rgba(255,255,255,0.05)] flex items-center justify-center flex-shrink-0">
                    <span className="text-xs text-slate-400 font-mono">pin</span>
                  </div>
                  <div>
                    <div className="font-semibold mb-1">Explicit model name — Pin to a specific model</div>
                    <div className="text-sm text-slate-400 leading-relaxed">
                      Pass any supported model name to bypass routing. Caching still applies — identical
                      prompts return from cache at $0 regardless of model.
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <CodeBlock code={MODEL_EXAMPLES} lang="json" />

            <div className="mt-4 text-sm text-slate-400">
              Supported providers include OpenAI, Anthropic, Google, Meta (via Groq), and more.
              The available model list is at <code className="text-[#00d4aa] bg-[rgba(0,212,170,0.08)] px-1 rounded text-xs">GET /api/v1/status</code>.
            </div>
          </Section>

          {/* ── Cache Control ────────────────────────────────────────── */}
          <Section id="cache-control" title="Cache Control" delay={0.1}>
            <p className="text-slate-400 mb-5 leading-relaxed">
              Exact-match caching is <strong className="text-white">on by default</strong> for all requests.
              Identical prompt + model combinations return instantly from cache — no API call, no cost.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
              <div className="card p-5">
                <div className="text-[#00d4aa] text-xs font-semibold uppercase tracking-wider mb-2">Cache HIT</div>
                <div className="text-white font-bold text-xl mb-1">$0.00</div>
                <div className="text-slate-400 text-sm">Response returned instantly from cache. No API call made. Zero cost.</div>
              </div>
              <div className="card p-5">
                <div className="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">Cache MISS</div>
                <div className="text-white font-bold text-xl mb-1">Normal cost</div>
                <div className="text-slate-400 text-sm">New prompt routed to cheapest capable model. Response cached for future hits.</div>
              </div>
            </div>

            <div className="mb-4">
              <div className="text-sm font-semibold mb-2">Bypass cache for a single request</div>
              <p className="text-sm text-slate-400 mb-3">
                Add the <code className="text-[#00d4aa] bg-[rgba(0,212,170,0.08)] px-1 rounded">X-AO-Cache: false</code> header
                to skip cache lookup and always make a fresh API call.
              </p>
              <CodeBlock code={CACHE_EXAMPLES} lang="bash" />
            </div>

            <div className="p-4 bg-[rgba(0,212,170,0.04)] border border-[rgba(0,212,170,0.12)] rounded-lg text-sm text-slate-300">
              <span className="text-[#00d4aa] font-semibold">Cache key:</span> SHA-256 of
              {" "}(model + messages array). Temperature, max_tokens, and other params are ignored for cache matching
              — only the prompt content matters.
            </div>
          </Section>

          {/* ── Budget Limits ────────────────────────────────────────── */}
          <Section id="budget-limits" title="Budget Limits" delay={0.1}>
            <p className="text-slate-400 mb-5 leading-relaxed">
              Every API key has a hard spending limit. When you hit it, requests return a{" "}
              <code className="text-red-400 bg-red-400/10 px-1 rounded text-xs">402 Payment Required</code> error.
              No charges beyond your limit. Ever.
            </p>

            <div className="space-y-4 mb-6">
              {[
                {
                  q: "How does the limit work?",
                  a: "AgentOptima tracks spent_total_cents per key. Before executing any request, we check if (spent_total + estimated_cost) would exceed budget_limit_cents. If yes, the request is rejected with a 402 error.",
                },
                {
                  q: "What happens when I hit my limit?",
                  a: "Requests fail with a clear error message: 'Budget limit reached. Update your limit at agentoptima.ai/dashboard.' No partial charges, no surprises.",
                },
                {
                  q: "How do I increase my limit?",
                  a: "Call PUT /api/v1/keys/budget with your new limit, or update it from the dashboard. The change takes effect immediately.",
                },
                {
                  q: "Can I set limit to zero to pause all requests?",
                  a: "Yes — set budget_limit_cents to 1 to effectively pause all spending. All requests will fail the budget check until you increase it.",
                },
              ].map((item) => (
                <div key={item.q} className="card p-5">
                  <div className="font-semibold text-sm mb-2">{item.q}</div>
                  <div className="text-sm text-slate-400 leading-relaxed">{item.a}</div>
                </div>
              ))}
            </div>

            <div className="text-sm font-semibold mb-2">Update your budget</div>
            <CodeBlock code={BUDGET_UPDATE} lang="bash" />
          </Section>

          {/* Footer CTA */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="card-glow p-8 text-center"
          >
            <h3 className="text-xl font-bold mb-2">Ready to start saving?</h3>
            <p className="text-slate-400 text-sm mb-5">Free key in 10 seconds. No credit card.</p>
            <Link
              href="/onboarding"
              className="button-primary inline-flex items-center gap-2 px-6 py-3"
              style={{ borderRadius: "8px" }}
            >
              Get your free API key <ChevronRight size={15} />
            </Link>
          </motion.div>
        </main>
      </div>
    </div>
  );
}
