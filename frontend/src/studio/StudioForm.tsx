import { useState } from "react";
import {
  ArrowLeft,
  Check,
  Loader2,
  Play,
  Search,
  Sparkles,
  Database,
  FilePenLine,
} from "lucide-react";
import type { StudioBot, StudioCatalog, StudioConfig, ToolId } from "./types";

export const SKILL_ICONS = {
  research: Search,
  analyze: Sparkles,
  save: Database,
  draft: FilePenLine,
};

const INITIAL: StudioConfig = {
  template_id: "lead_research_v1",
  name: "Lead Research Bot",
  objective: "",
  skills: ["research", "analyze", "save", "draft"],
  tools: ["brave_search", "llm", "database"],
  trigger: "manual",
  enabled: true,
  target: {
    industry: "",
    location: "",
    qualification_criteria: "",
    offering: "",
    max_prospects: 5,
    minimum_score: 70,
  },
  expected_results: {
    description:
      "Source-backed qualified prospects, supporting links, and personalized outreach drafts for my review.",
    minimum_qualified: 1,
  },
};

export default function StudioForm({
  bot,
  catalog,
  onSave,
  onBack,
  onConnections,
}: {
  bot?: StudioBot;
  catalog: StudioCatalog;
  onSave: (data: StudioConfig) => Promise<void>;
  onBack: () => void;
  onConnections: () => void;
}) {
  const [config, setConfig] = useState<StudioConfig>(() =>
    bot ? structuredClone(bot.configuration) : structuredClone(INITIAL),
  );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  function change<K extends keyof StudioConfig>(key: K, value: StudioConfig[K]) {
    setConfig((current) => ({ ...current, [key]: value }));
  }
  function target<K extends keyof StudioConfig["target"]>(
    key: K,
    value: StudioConfig["target"][K],
  ) {
    setConfig((current) => ({ ...current, target: { ...current.target, [key]: value } }));
  }
  function tool(id: ToolId) {
    change(
      "tools",
      config.tools.includes(id)
        ? config.tools.filter((item) => item !== id)
        : [...config.tools, id],
    );
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await onSave(config);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save the bot.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="studio-form-page">
      <button className="studio-back" onClick={onBack}>
        <ArrowLeft size={15} />
        Back to library
      </button>
      <div className="studio-page-heading">
        <div>
          <span className="studio-eyebrow">LEAD RESEARCH TEMPLATE</span>
          <h1>{bot ? "Edit your bot" : "Give your bot a job"}</h1>
          <p>Define the outcome. The registered skills handle the work in order.</p>
        </div>
      </div>
      <form onSubmit={submit} className="studio-config-form">
        <div className="studio-form-main">
          <section className="studio-form-section">
            <div className="studio-section-title">
              <span>1</span>
              <div>
                <h2>Objective</h2>
                <p>What responsibility should this bot take on?</p>
              </div>
            </div>
            <label>
              Bot name
              <input
                required
                maxLength={80}
                value={config.name}
                onChange={(e) => change("name", e.target.value)}
              />
            </label>
            <label>
              Objective
              <textarea
                autoFocus
                aria-label="Objective"
                required
                minLength={10}
                maxLength={2000}
                rows={3}
                placeholder="Find companies that would benefit from our service and prepare well-researched outreach drafts."
                value={config.objective}
                onChange={(e) => change("objective", e.target.value)}
              />
            </label>
            <div className="studio-form-row">
              <label>
                Target industry
                <input
                  required
                  minLength={2}
                  maxLength={160}
                  placeholder="e.g. Industrial automation"
                  value={config.target.industry}
                  onChange={(e) => target("industry", e.target.value)}
                />
              </label>
              <label>
                Location
                <input
                  required
                  minLength={2}
                  maxLength={160}
                  placeholder="e.g. Kuala Lumpur, Malaysia"
                  value={config.target.location}
                  onChange={(e) => target("location", e.target.value)}
                />
              </label>
            </div>
            <label>
              Qualification criteria
              <textarea
                required
                minLength={5}
                maxLength={2000}
                aria-label="Qualification criteria"
                rows={3}
                placeholder="What makes a good prospect? Use criteria that can be established from public company information."
                value={config.target.qualification_criteria}
                onChange={(e) => target("qualification_criteria", e.target.value)}
              />
            </label>
            <label>
              Your offering
              <textarea
                required
                minLength={5}
                maxLength={1200}
                aria-label="Your offering"
                rows={3}
                placeholder="Describe what you actually offer. The bot uses this to personalize drafts."
                value={config.target.offering}
                onChange={(e) => target("offering", e.target.value)}
              />
            </label>
          </section>
          <section className="studio-form-section">
            <div className="studio-section-title">
              <span>5</span>
              <div>
                <h2>Expected results</h2>
                <p>Define the deliverable and a measurable minimum.</p>
              </div>
            </div>
            <label>
              Desired output and success criteria
              <textarea
                required
                minLength={5}
                maxLength={1200}
                aria-label="Desired output and success criteria"
                rows={3}
                value={config.expected_results.description}
                onChange={(e) =>
                  change("expected_results", {
                    ...config.expected_results,
                    description: e.target.value,
                  })
                }
              />
            </label>
            <div className="studio-form-row three">
              <label>
                Maximum prospects
                <input
                  type="number"
                  required
                  min={1}
                  max={8}
                  value={config.target.max_prospects}
                  onChange={(e) => target("max_prospects", Number(e.target.value))}
                />
              </label>
              <label>
                Minimum fit score
                <input
                  type="number"
                  required
                  min={0}
                  max={100}
                  value={config.target.minimum_score}
                  onChange={(e) => target("minimum_score", Number(e.target.value))}
                />
              </label>
              <label>
                Minimum qualified
                <input
                  type="number"
                  required
                  min={0}
                  max={config.target.max_prospects}
                  value={config.expected_results.minimum_qualified}
                  onChange={(e) =>
                    change("expected_results", {
                      ...config.expected_results,
                      minimum_qualified: Number(e.target.value),
                    })
                  }
                />
              </label>
            </div>
            <p className="studio-field-help">
              Names and supporting quotes must match the search sources. Fit scores are AI
              judgments; review them before contacting anyone.
            </p>
          </section>
        </div>
        <aside className="studio-form-aside">
          <section className="studio-form-section">
            <div className="studio-section-title">
              <span>2</span>
              <div>
                <h2>Skills</h2>
                <p>This template uses four reusable skills.</p>
              </div>
            </div>
            <div className="studio-selected-skills">
              {catalog.skills.map((skill) => {
                const Icon = SKILL_ICONS[skill.id];
                return (
                  <label key={skill.id} className="studio-skill-choice">
                    <input
                      type="checkbox"
                      checked={config.skills.includes(skill.id)}
                      disabled={skill.id !== "draft"}
                      aria-label={`${skill.name} ${skill.id === "draft" ? "optional" : "required"} skill`}
                      onChange={() =>
                        change(
                          "skills",
                          config.skills.includes("draft")
                            ? ["research", "analyze", "save"]
                            : ["research", "analyze", "save", "draft"],
                        )
                      }
                    />
                    <Icon size={17} />
                    <span>
                      <strong>
                        {skill.name}
                        {skill.id === "draft" ? " · optional" : ""}
                      </strong>
                      <small>{skill.description}</small>
                    </span>
                  </label>
                );
              })}
            </div>
            <p className="studio-field-help">
              Research, Analyze and Save are required. Select Draft to add outreach messages for
              review. The order is fixed.
            </p>
          </section>
          <section className="studio-form-section">
            <div className="studio-section-title">
              <span>3</span>
              <div>
                <h2>Permitted tools</h2>
                <p>Grant access only to what this job needs.</p>
              </div>
            </div>
            {catalog.tools.map((item) => (
              <label key={item.id} className="studio-tool-choice">
                <input
                  type="checkbox"
                  checked={config.tools.includes(item.id)}
                  onChange={() => tool(item.id)}
                />
                <span>
                  <strong>{item.name}</strong>
                  <small className={item.configured ? "connection-ready" : "connection-missing"}>
                    {item.configured ? "Connected by administrator" : "Setup required"}
                  </small>
                </span>
              </label>
            ))}
            <button type="button" className="studio-text-button" onClick={onConnections}>
              Connection setup
            </button>
            <p className="studio-field-help">
              The template requires all three tools to execute. API keys stay on the server.
            </p>
          </section>
          <section className="studio-form-section">
            <div className="studio-section-title">
              <span>4</span>
              <div>
                <h2>Trigger</h2>
                <p>Choose when the work starts.</p>
              </div>
            </div>
            <div className="studio-manual-trigger">
              <Play size={15} />
              <div>
                <strong>Manual</strong>
                <span>Runs only when you choose Run bot.</span>
              </div>
              <Check size={14} />
            </div>
            <label className="studio-enable-choice">
              <input
                type="checkbox"
                checked={config.enabled}
                onChange={(e) => change("enabled", e.target.checked)}
              />
              Bot enabled for manual execution
            </label>
          </section>
        </aside>
        <footer className="studio-form-footer">
          {error && (
            <p className="studio-error" role="alert">
              {error}
            </p>
          )}
          <p>Outreach is saved as drafts. Nothing is sent automatically.</p>
          <div>
            <button className="button secondary" type="button" onClick={onBack} disabled={busy}>
              Cancel
            </button>
            <button className="button primary" disabled={busy}>
              {busy && <Loader2 className="spin" size={15} />}{" "}
              {busy ? "Saving…" : bot ? "Save changes" : "Create bot"}
            </button>
          </div>
        </footer>
      </form>
    </div>
  );
}
