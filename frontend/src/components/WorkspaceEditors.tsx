import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Loader2, X } from "lucide-react";
import type { Bot, BotInput, Memory, Routine, RoutineInput } from "../types";
import { CRITERIA } from "../workspace";

function Editor({
  title,
  children,
  onClose,
  busy,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="editor-dialog"
      aria-labelledby={id}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <header>
        <h2 id={id}>{title}</h2>
        <button className="icon-button" aria-label="Close editor" disabled={busy} onClick={onClose}>
          <X size={19} />
        </button>
      </header>
      {children}
    </dialog>
  );
}

function useSave(onSave: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return {
    busy,
    error,
    submit: async (event: React.FormEvent) => {
      event.preventDefault();
      if (busy) return;
      setBusy(true);
      setError("");
      try {
        await onSave();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to save.");
      } finally {
        setBusy(false);
      }
    },
  };
}

function Footer({
  busy,
  error,
  label = "Save",
  onClose,
}: {
  busy: boolean;
  error: string;
  label?: string;
  onClose: () => void;
}) {
  return (
    <>
      <p role={error ? "alert" : undefined} className="form-error">
        {error}
      </p>
      <footer>
        <button type="button" className="button secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="button primary" disabled={busy}>
          {busy && <Loader2 size={15} className="spin" />}
          {busy ? "Saving…" : label}
        </button>
      </footer>
    </>
  );
}

export function BotEditor({
  bot,
  onSave,
  onClose,
}: {
  bot?: Bot;
  onSave: (data: BotInput) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState(bot?.name ?? "");
  const [role, setRole] = useState(bot?.role ?? "");
  const [instructions, setInstructions] = useState(bot?.instructions ?? "");
  const save = useSave(() =>
    onSave({ name: name.trim(), role: role.trim(), instructions: instructions.trim() }),
  );
  return (
    <Editor title={bot ? "Edit bot" : "Create a bot"} onClose={onClose} busy={save.busy}>
      <form onSubmit={save.submit}>
        <p className="form-intro">
          Give your bot a role. It can research your knowledge, create documents, and remember how
          you work.
        </p>
        <label>
          Name
          <input
            autoFocus
            required
            maxLength={80}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Chief of Staff"
          />
        </label>
        <label>
          What does this bot do?
          <input
            required
            minLength={3}
            maxLength={500}
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder="Prepare briefings and turn plans into action"
          />
        </label>
        <label>
          Instructions
          <textarea
            rows={5}
            maxLength={4000}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="How should it approach its work?"
          />
        </label>
        <Footer {...save} onClose={onClose} label={bot ? "Save changes" : "Create bot"} />
      </form>
    </Editor>
  );
}

export function MemoryEditor({
  memory,
  onSave,
  onClose,
}: {
  memory?: Memory;
  onSave: (key: string, value: string) => Promise<void>;
  onClose: () => void;
}) {
  const [key, setKey] = useState(memory?.key ?? "");
  const [value, setValue] = useState(memory?.value ?? "");
  const save = useSave(() => onSave(key.trim(), value.trim()));
  return (
    <Editor
      title={memory ? "Edit a memory" : "Remember a preference"}
      onClose={onClose}
      busy={save.busy}
    >
      <form onSubmit={save.submit}>
        <p className="form-intro">
          This bot will use your saved preferences in future work. You can edit or forget them
          anytime.
        </p>
        <label>
          Name
          <input
            autoFocus={!memory}
            required
            readOnly={!!memory}
            aria-label="Name"
            pattern="[a-z][a-z0-9_.\-]*"
            maxLength={80}
            value={key}
            onChange={(e) => setKey(e.target.value.toLowerCase().replace(/ /g, "_"))}
            placeholder="e.g. report_style"
          />
          <small>Lowercase letters, numbers, underscores, dots or dashes.</small>
        </label>
        <label>
          What should it remember?
          <textarea
            autoFocus={!!memory}
            required
            maxLength={1000}
            rows={5}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Keep reports concise. Use British English and end with next steps."
          />
        </label>
        <Footer {...save} onClose={onClose} label="Save memory" />
      </form>
    </Editor>
  );
}

export function RoutineEditor({
  bot,
  routine,
  onSave,
  onClose,
}: {
  bot: Bot;
  routine?: Routine;
  onSave: (input: RoutineInput) => Promise<void>;
  onClose: () => void;
}) {
  const [input, setInput] = useState<RoutineInput>(() =>
    routine
      ? { ...routine }
      : {
          bot_id: bot.id,
          name: "",
          goal: "",
          completion_criteria: CRITERIA,
          recurrence: "weekdays",
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          local_time: "08:00",
          weekday: 0,
          enabled: true,
        },
  );
  function change<K extends keyof RoutineInput>(key: K, value: RoutineInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
  }
  const save = useSave(() =>
    onSave({
      bot_id: input.bot_id,
      name: input.name.trim(),
      goal: input.goal.trim(),
      completion_criteria: input.completion_criteria,
      recurrence: input.recurrence,
      timezone: input.timezone,
      local_time: input.local_time,
      weekday: input.weekday,
      enabled: input.enabled,
    }),
  );
  return (
    <Editor
      title={routine ? "Edit routine" : "Create a routine"}
      onClose={onClose}
      busy={save.busy}
    >
      <form onSubmit={save.submit}>
        <p className="form-intro">
          {bot.name} will run this task on schedule, even when you’re away. Each run uses your
          current knowledge and bot memory.
        </p>
        <label>
          Name
          <input
            autoFocus
            required
            maxLength={80}
            placeholder="e.g. Monday operations brief"
            value={input.name}
            onChange={(e) => change("name", e.target.value)}
          />
        </label>
        <label>
          Task
          <textarea
            required
            minLength={3}
            maxLength={4000}
            rows={3}
            placeholder="Prepare a briefing from our operations policies, with key steps and escalation contacts."
            value={input.goal}
            onChange={(e) => change("goal", e.target.value)}
          />
        </label>
        <div className="form-row">
          <label>
            Repeat
            <select
              value={input.recurrence}
              onChange={(e) => change("recurrence", e.target.value as RoutineInput["recurrence"])}
            >
              <option value="weekdays">Weekdays</option>
              <option value="daily">Every day</option>
              <option value="weekly">Every week</option>
            </select>
          </label>
          <label>
            At
            <input
              required
              type="time"
              value={input.local_time}
              onChange={(e) => change("local_time", e.target.value)}
            />
          </label>
        </div>
        {input.recurrence === "weekly" && (
          <label>
            Day
            <select
              value={input.weekday}
              onChange={(e) => change("weekday", Number(e.target.value))}
            >
              {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map(
                (day, i) => (
                  <option key={day} value={i}>
                    {day}
                  </option>
                ),
              )}
            </select>
          </label>
        )}
        <label>
          Timezone
          <input
            required
            value={input.timezone}
            maxLength={80}
            onChange={(e) => change("timezone", e.target.value)}
            list="timezones"
          />
          <datalist id="timezones">
            {[
              "Asia/Kuala_Lumpur",
              "Asia/Singapore",
              "Europe/London",
              "America/New_York",
              "America/Los_Angeles",
              "UTC",
            ].map((zone) => (
              <option key={zone} value={zone} />
            ))}
          </datalist>
        </label>
        <p className="field-note">If a previous run is waiting for you, the next run waits too.</p>
        <Footer {...save} onClose={onClose} label={routine ? "Save routine" : "Schedule routine"} />
      </form>
    </Editor>
  );
}
