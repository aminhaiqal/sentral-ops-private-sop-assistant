import { useEffect, useRef } from "react";
import { ArrowUp, Loader2, Paperclip } from "lucide-react";

type Props = {
  value: string;
  loading: boolean;
  uploading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onAttach: () => void;
};

export default function QuestionInput({
  value,
  loading,
  uploading,
  onChange,
  onSubmit,
  onAttach,
}: Props) {
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!field.current) return;
    field.current.style.height = "auto";
    field.current.style.height = `${Math.min(field.current.scrollHeight, 180)}px`;
  }, [value]);
  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <button
        className="icon-button attach-button"
        type="button"
        onClick={onAttach}
        aria-label="Upload documents"
        title="Upload PDF or Markdown"
        disabled={uploading}
      >
        {uploading ? <Loader2 size={21} className="spin" /> : <Paperclip size={21} />}
      </button>
      <textarea
        ref={field}
        aria-label="Message Sentral"
        value={value}
        rows={1}
        maxLength={800}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Ask about your documents"
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            if (!loading && value.trim().length >= 3) onSubmit();
          }
        }}
      />
      <button
        type="submit"
        className="send-button"
        aria-label="Send message"
        disabled={loading || value.trim().length < 3}
      >
        {loading ? <Loader2 size={20} className="spin" /> : <ArrowUp size={22} strokeWidth={2.3} />}
      </button>
    </form>
  );
}
