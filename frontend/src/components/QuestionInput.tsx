import { Loader2, Send } from "lucide-react";

type QuestionInputProps = {
  value: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export default function QuestionInput({
  value,
  loading,
  onChange,
  onSubmit
}: QuestionInputProps) {
  return (
    <form
      className="question-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label className="field-label" htmlFor="question">
        Staff question
      </label>
      <textarea
        id="question"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="What is required before issuing a credit note?"
        rows={5}
      />
      <div className="form-actions">
        <button type="submit" className="primary-button" disabled={loading || value.trim().length < 3}>
          {loading ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
          <span>{loading ? "Checking" : "Ask"}</span>
        </button>
      </div>
    </form>
  );
}
