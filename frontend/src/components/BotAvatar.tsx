export function botColor(name: string): number {
  if (/chief/i.test(name)) return 0;
  if (/operat/i.test(name)) return 1;
  if (/research/i.test(name)) return 2;
  if (/support/i.test(name)) return 3;
  return [...name].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 6;
}

export default function BotAvatar({
  name,
  size = "normal",
}: {
  name: string;
  size?: "small" | "normal" | "large";
}) {
  return (
    <span aria-hidden="true" className={`bot-avatar avatar-${botColor(name)} avatar-${size}`}>
      <i />
      <i />
    </span>
  );
}
