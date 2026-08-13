/** Inline busy indicator. Buttons keep their label so the action stays readable. */
export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spin">
      <span className="ring" aria-hidden />
      {label && <span>{label}</span>}
    </span>
  );
}
