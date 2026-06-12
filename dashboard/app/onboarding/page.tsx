"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useState, useCallback } from "react";
import {
  Zap, Check, Copy, ArrowRight, AlertCircle, Loader2,
  Terminal, Code2, Globe
} from "lucide-react";
import Link from "next/link";

const AO_BASE = "https://agentoptima.ai";

// ── Types ─────────────────────────────────────────────────────────────────────

interface GeneratedKey {
  key: string;
  label: string;
  budget_limit_cents: number;
}

interface TestResult {
  content: string;
  model: string;
  cost_cents: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtCents(c: number): string {
  if (c < 1) return "<0.01¢";
  if (c < 100) return `${c.toFixed(2)}¢`;
  return `$${(c / 100).toFixed(3)}`;
}

function CopyButton({ text, size = 14 }: { text: string; size?: number }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="p-1.5 rounded hover:bg-white/10 transition-colors flex-shrink-0"
      title="Copy"
    >
      {copied
        ? <Check size={size} className="text-[#00d4aa]" />
        : <Copy size={size} className="text-slate-400" />}
    </button>
  );
}

// ── Code snippets ─────────────────────────────────────────────────────────────

const SNIPPETS: Record<string, (k: string) => string> = {
  Python: (k) =>
`from openai import OpenAI

client = OpenAI(
    api_key="${k}",
    base_url="https://agentoptima.ai/v1"
)

response = client.chat.completions.create(
    model="auto",   # AgentOptima picks cheapest model
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)`,

  JavaScript: (k) =>
`import OpenAI from 'openai';

const client = new OpenAI({
  apiKey: '${k}',
  baseURL: 'https://agentoptima.ai/v1',
  dangerouslyAllowBrowser: true,
});

const response = await client.chat.completions.create({
  model: 'auto',   // AgentOptima picks cheapest model
  messages: [{ role: 'user', content: 'Hello!' }],
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

// ── Step indicator ────────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: number }) {
  const steps = ["Get your key", "Connect", "You're live"];
  return (
    <div className="flex items-center justify-center gap-3 mb-10">
      {steps.map((label, i) => {
        const step = i + 1;
        const done = step < current;
        const active = step === current;
        return (
          <div key={label} className="flex items-center gap-3">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                  done
                    ? "bg-[#00d4aa] text-[#0a0a0f]"
                    : active
                    ? "bg-[rgba(0,212,170,0.15)] border border-[#00d4aa] text-[#00d4aa]"
                    : "bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] text-slate-500"
                }`}
              >
                {done ? <Check size={12} /> : step}
              </div>
              <span
                className={`text-[10px] hidden sm:block ${
                  active ? "text-[#00d4aa]" : "text-slate-500"
                }`}
              >
                {label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                className={`w-10 sm:w-16 h-px mt-[-10px] transition-all ${
                  done ? "bg-[#00d4aa]" : "bg-[rgba(255,255,255,0.08)]"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Step 1: Get your key ──────────────────────────────────────────────────────

function Step1({
  onNext,
}: {
  onNext: (key: GeneratedKey) => void;
}) {
  const [label, setLabel] = useState("my-app");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generatedKey, setGeneratedKey] = useState<GeneratedKey | null>(null);

  const handleCreate = async () => {
    if (!label.trim()) { setError("Give your key a name first."); return; }
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${AO_BASE}/api/v1/keys/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: label.trim() }),
      });
      const d = await r.json();
      if (d.key) {
        setGeneratedKey({ key: d.key, label: label.trim(), budget_limit_cents: d.budget_limit_cents ?? 0 });
      } else {
        setError(d.detail || "Failed to create key. Try again.");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (generatedKey) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        className="space-y-5"
      >
        <div className="flex items-center gap-2 text-[#00d4aa] text-sm font-medium">
          <Check size={16} /> Key created — copy it below
        </div>

        {/* Prominent key copy box */}
        <div className="rounded-xl border-2 border-[rgba(0,212,170,0.4)] bg-[rgba(0,212,170,0.06)] p-5">
          <div className="text-xs text-[#00d4aa] font-semibold uppercase tracking-wider mb-3">Your API key</div>
          <div className="flex items-center gap-3 bg-[#0a0a0f] border border-[rgba(0,212,170,0.2)] rounded-lg px-4 py-3.5">
            <code className="text-[#00d4aa] text-base flex-1 break-all font-mono tracking-wide">{generatedKey.key}</code>
            <CopyButton text={generatedKey.key} size={18} />
          </div>
          <div className="flex items-start gap-2 mt-3">
            <AlertCircle size={13} className="text-amber-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-300 leading-relaxed">
              <span className="font-semibold">Save this now — we show it once.</span> Copy it to a safe place before continuing.
            </p>
          </div>
        </div>

        <button
          onClick={() => onNext(generatedKey)}
          className="button-primary w-full py-3 flex items-center justify-center gap-2"
        >
          Continue to connect your app <ArrowRight size={16} />
        </button>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className="space-y-5"
    >
      <div>
        <label className="block text-sm text-slate-300 font-medium mb-2">
          Name this key
        </label>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          placeholder="e.g. my-app"
          className="w-full bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] hover:border-[rgba(0,212,170,0.2)] focus:border-[rgba(0,212,170,0.4)] rounded-lg px-4 py-3 text-sm text-white placeholder-slate-600 focus:outline-none transition-colors"
          autoFocus
        />
      </div>

      {error && (
        <div className="flex items-center gap-2 text-red-400 text-sm">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      <button
        onClick={handleCreate}
        disabled={loading}
        className="button-primary w-full py-3.5 flex items-center justify-center gap-2 text-base"
      >
        {loading ? (
          <>
            <Loader2 size={16} className="animate-spin" /> Generating…
          </>
        ) : (
          <>
            Generate my key →
          </>
        )}
      </button>

      <p className="text-center text-xs text-slate-600">Free to start · No credit card required</p>
    </motion.div>
  );
}

// ── Step 2: Connect ───────────────────────────────────────────────────────────

function Step2({
  generatedKey,
  onNext,
}: {
  generatedKey: GeneratedKey;
  onNext: (result?: TestResult) => void;
}) {
  const [tab, setTab] = useState<"Python" | "JavaScript" | "curl">("Python");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testError, setTestError] = useState("");

  const snippet = SNIPPETS[tab](generatedKey.key);

  const handleTest = useCallback(async () => {
    setTesting(true);
    setTestError("");
    setTestResult(null);
    try {
      const r = await fetch(`${AO_BASE}/v1/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${generatedKey.key}`,
        },
        body: JSON.stringify({
          model: "auto",
          messages: [{ role: "user", content: "Say hello in one sentence." }],
        }),
      });
      const d = await r.json();
      if (d.choices?.[0]?.message?.content) {
        setTestResult({
          content: d.choices[0].message.content,
          model: d.model || "auto",
          cost_cents: d.usage?.total_cost_cents ?? 0,
        });
      } else {
        setTestError(d.detail || "Unexpected response. Check your key.");
      }
    } catch {
      setTestError("Connection failed. Make sure you're online.");
    } finally {
      setTesting(false);
    }
  }, [generatedKey.key]);

  const tabIcons: Record<string, React.ReactNode> = {
    Python: <Terminal size={13} />,
    JavaScript: <Code2 size={13} />,
    curl: <Globe size={13} />,
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className="space-y-5"
    >
      <p className="text-sm text-slate-400">
        Drop this into your app. Change one line - everything else stays the same.
      </p>

      {/* Code tabs */}
      <div className="card overflow-hidden">
        <div className="flex items-center gap-1 px-4 pt-3 pb-0 border-b border-[rgba(0,212,170,0.1)]">
          {(["Python", "JavaScript", "curl"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 ${
                tab === t
                  ? "text-[#00d4aa] border-[#00d4aa]"
                  : "text-slate-500 border-transparent hover:text-slate-300"
              }`}
            >
              {tabIcons[t]} {t}
            </button>
          ))}
          <div className="ml-auto pb-1">
            <CopyButton text={snippet} />
          </div>
        </div>
        <pre className="text-xs text-slate-300 p-5 overflow-x-auto leading-relaxed font-mono">
          <code>{snippet}</code>
        </pre>
      </div>

      {/* Test button */}
      <div className="card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">Test your connection</div>
            <div className="text-xs text-slate-500 mt-0.5">Sends a real request using your key</div>
          </div>
          <button
            onClick={handleTest}
            disabled={testing}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              testResult
                ? "bg-[rgba(0,212,170,0.1)] border border-[rgba(0,212,170,0.3)] text-[#00d4aa]"
                : "bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] text-white hover:border-[rgba(0,212,170,0.3)]"
            }`}
          >
            {testing ? (
              <><Loader2 size={14} className="animate-spin" /> Testing...</>
            ) : testResult ? (
              <><Check size={14} /> Connected</>
            ) : (
              "Run test →"
            )}
          </button>
        </div>

        <AnimatePresence>
          {testResult && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="space-y-2"
            >
              <div className="bg-[rgba(0,212,170,0.04)] border border-[rgba(0,212,170,0.15)] rounded-lg p-3">
                <div className="text-xs text-slate-400 mb-1">Response</div>
                <div className="text-sm text-white">{testResult.content}</div>
              </div>
              <div className="flex items-center gap-4 text-xs text-slate-500">
                <span>Model: <span className="text-slate-300">{testResult.model}</span></span>
                <span>Cost: <span className="text-[#00d4aa]">{fmtCents(testResult.cost_cents)}</span></span>
              </div>
            </motion.div>
          )}
          {testError && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2 text-red-400 text-xs"
            >
              <AlertCircle size={12} /> {testError}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <button
        onClick={() => onNext(testResult ?? undefined)}
        className="button-primary w-full py-3 flex items-center justify-center gap-2"
      >
        Continue <ArrowRight size={16} />
      </button>
    </motion.div>
  );
}

// ── Step 3: You're live ───────────────────────────────────────────────────────

function Step3({
  generatedKey,
  testResult,
}: {
  generatedKey: GeneratedKey;
  testResult?: TestResult;
}) {
  const budgetUSD = (generatedKey.budget_limit_cents / 100).toFixed(2);

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className="space-y-6"
    >
      {/* Success banner */}
      <div className="text-center py-4">
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 200, damping: 15 }}
          className="w-16 h-16 rounded-full bg-[rgba(0,212,170,0.12)] border border-[rgba(0,212,170,0.3)] flex items-center justify-center mx-auto mb-4"
        >
          <Zap size={28} className="text-[#00d4aa]" />
        </motion.div>
        <h3 className="text-xl font-bold mb-1">You&apos;re live.</h3>
        <p className="text-slate-400 text-sm">AgentOptima is now routing your requests.</p>
      </div>

      {/* Mini savings card */}
      {testResult && (
        <div className="card p-5 space-y-3">
          <div className="text-xs text-slate-400 font-medium uppercase tracking-wider">First request</div>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[rgba(255,255,255,0.03)] rounded-lg p-3 text-center">
              <div className="text-xs text-slate-500 mb-1">Cost</div>
              <div className="text-lg font-bold text-white">{fmtCents(testResult.cost_cents)}</div>
            </div>
            <div className="bg-[rgba(0,212,170,0.04)] border border-[rgba(0,212,170,0.15)] rounded-lg p-3 text-center">
              <div className="text-xs text-slate-500 mb-1">Same prompt cached</div>
              <div className="text-lg font-bold text-[#00d4aa]">$0.00</div>
            </div>
          </div>
        </div>
      )}

      {/* Key summary */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Key label</span>
          <span className="text-sm text-white font-medium">{generatedKey.label}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Budget limit</span>
          <span className="text-sm text-white font-medium">${budgetUSD} / mo</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Your key</span>
          <div className="flex items-center gap-1">
            <code className="text-xs text-[#00d4aa] font-mono">
              {generatedKey.key.slice(0, 10)}...
            </code>
            <CopyButton text={generatedKey.key} size={12} />
          </div>
        </div>
      </div>

      {/* CTAs */}
      <div className="space-y-3">
        <Link
          href={`/dashboard?key=${encodeURIComponent(generatedKey.key)}`}
          className="button-primary w-full py-3 flex items-center justify-center gap-2 text-center"
        >
          View your dashboard <ArrowRight size={16} />
        </Link>
        <Link
          href="/docs"
          className="block w-full py-3 text-center text-sm text-slate-400 border border-[rgba(255,255,255,0.08)] rounded-lg hover:border-[rgba(0,212,170,0.2)] hover:text-white transition-all"
        >
          Read the docs →
        </Link>
      </div>
    </motion.div>
  );
}

// ── Root ──────────────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const [step, setStep] = useState(1);
  const [generatedKey, setGeneratedKey] = useState<GeneratedKey | null>(null);
  const [testResult, setTestResult] = useState<TestResult | undefined>(undefined);

  const stepTitles = ["Get your key", "Connect your app", "You're live"];

  return (
    <div className="min-h-screen bg-[#0a0a0f] bg-grid text-white">
      {/* Nav */}
      <nav className="border-b border-[rgba(0,212,170,0.1)] px-6 py-4">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Zap size={18} className="text-[#00d4aa]" />
            <span className="font-bold text-base tracking-tight">AgentOptima</span>
          </Link>
          <span className="text-xs text-slate-500">Step {step} of 3</span>
        </div>
      </nav>

      {/* Main content */}
      <div className="max-w-lg mx-auto px-6 py-12">
        <StepIndicator current={step} />

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-2xl font-black tracking-tight mb-1">{stepTitles[step - 1]}</h1>
        </motion.div>

        <AnimatePresence mode="wait">
          {step === 1 && (
            <motion.div key="step1">
              <Step1
                onNext={(key) => {
                  setGeneratedKey(key);
                  setStep(2);
                }}
              />
            </motion.div>
          )}
          {step === 2 && generatedKey && (
            <motion.div key="step2">
              <Step2
                generatedKey={generatedKey}
                onNext={(result) => {
                  if (result) setTestResult(result);
                  setStep(3);
                }}
              />
            </motion.div>
          )}
          {step === 3 && generatedKey && (
            <motion.div key="step3">
              <Step3 generatedKey={generatedKey} testResult={testResult} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
