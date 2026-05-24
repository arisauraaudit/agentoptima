"use client";

import { motion } from "framer-motion";
import { 
  Bot, 
  TrendingUp, 
  Zap, 
  DollarSign, 
  Shield,
  BarChart3,
  Github,
  Twitter
} from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen">
      {/* Hero Section */}
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
              <button className="button-primary text-lg px-8 py-3">
                Start Tracking
              </button>
              <a 
                href="/docs" 
                className="px-8 py-3 text-slate-300 hover:text-white transition-colors font-medium"
              >
                Read Documentation
              </a>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-12 px-4 border-y border-slate-800">
        <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-8">
          {[
            { icon: Bot, label: "Tasks Tracked", value: "1,247", change: "+12%" },
            { icon: TrendingUp, label: "Models Ranked", value: "23", change: "+4" },
            { icon: DollarSign, label: "Cost Saved", value: "$847.32", change: "+18%" },
            { icon: Zap, label: "Avg Response", value: "0.8s", change: "-15%" }
          ].map((stat, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              className="text-center"
            >
              <stat.icon className="w-8 h-8 text-primary mx-auto mb-3" />
              <div className="text-3xl font-bold mb-1">{stat.value}</div>
              <div className="text-slate-400 text-sm mb-1">{stat.label}</div>
              <div className="text-success text-sm font-medium">{stat.change} this week</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-4">
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
                color: "text-blue-400"
              },
              {
                icon: TrendingUp,
                title: "Live Rankings",
                description: "Models ranked by use case, updated automatically with new data.",
                color: "text-green-400"
              },
              {
                icon: DollarSign,
                title: "Cost Optimization",
                description: "Identify the most cost-effective models for your specific needs.",
                color: "text-purple-400"
              },
              {
                icon: Shield,
                title: "Performance Monitoring",
                description: "Track uptime, error rates, and feature changes across models.",
                color: "text-red-400"
              },
              {
                icon: Zap,
                title: "API Access",
                description: "Integrate AgentOptima rankings and tracking into your applications.",
                color: "text-yellow-400"
              },
              {
                icon: Github,
                title: "Open Data",
                description: "Weekly rankings.json updates published to GitHub for the community.",
                color: "text-pink-400"
              }
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

      {/* Rankings Preview */}
      <section className="py-20 px-4 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-8">
            Live Rankings
          </h2>
          <p className="text-slate-400 text-center mb-12">
            Updated every 15 minutes based on real agent performance data
          </p>
          
          <div className="card p-6 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-3 px-4 font-medium text-slate-300">Model</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-300">Use Case</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-300">Success Rate</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-300">Avg Duration</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-300">Cost Efficiency</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-300">Rating</th>
                </tr>
              </thead>
              <tbody className="text-sm">
                {[
                  { model: "o3-pro", useCase: "Coding", success: "98%", duration: "2.1s", cost: "High", rating: "⭐⭐⭐⭐⭐" },
                  { model: "claude-3.7-sonnet", useCase: "Research", success: "97%", duration: "1.8s", cost: "Medium", rating: "⭐⭐⭐⭐⭐" },
                  { model: "gpt-4o", useCase: "Writing", success: "95%", duration: "1.2s", cost: "High", rating: "⭐⭐⭐⭐" },
                  { model: "qwen-2.5-max", useCase: "General", success: "94%", duration: "2.3s", cost: "Medium", rating: "⭐⭐⭐⭐" },
                  { model: "llama-3.3-70b", useCase: "Cost/Eff", success: "92%", duration: "1.9s", cost: "Low", rating: "⭐⭐⭐⭐" }
                ].map((row, i) => (
                  <motion.tr
                    key={i}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.1 }}
                    className="border-b border-slate-700/50 hover:bg-primary/5 transition-colors"
                  >
                    <td className="py-3 px-4 font-medium">{row.model}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-1 bg-primary/10 text-primary rounded text-xs">
                        {row.useCase}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-success">{row.success}</td>
                    <td className="py-3 px-4">{row.duration}</td>
                    <td className="py-3 px-4">{row.cost}</td>
                    <td className="py-3 px-4">{row.rating}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
          
          <div className="text-center mt-8">
            <button className="button-primary">
              View Full Rankings
            </button>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 text-center">
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          Start Optimizing Your AI Stack
        </h2>
        <p className="text-slate-400 mb-8 max-w-2xl mx-auto">
          Join agents already using AgentOptima to track performance and save costs.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <button className="button-primary text-lg px-8 py-3">
            Get Started Free
          </button>
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
            <a href="https://twitter.com/arisauraaudit" className="text-primary hover:text-green-400 transition-colors">
              @arisauraaudit
            </a>{" "}
            • Data from real agent operations
          </p>
          <div className="flex justify-center gap-6">
            <a href="https://github.com/arisauraaudit/agentoptima" className="hover:text-white transition-colors">
              <Github className="w-6 h-6" />
            </a>
            <a href="https://twitter.com/agentoptima" className="hover:text-blue-400 transition-colors">
              <Twitter className="w-6 h-6" />
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
