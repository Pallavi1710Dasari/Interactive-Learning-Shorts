/**
 * One line-icon set for the action rail.
 *
 * WHY THESE ARE DRAWN RATHER THAN TYPED. The rail used emoji and typographic
 * characters together — 💬 🔖 🏷 beside ➦ ⤓ ↻ — and that is the single thing that
 * made it read as unfinished. Emoji are rendered by the OS, so they arrive at a
 * different weight, a different optical size and, on most platforms, in full
 * colour: a flat cream column with two glossy stickers in the middle of it. The
 * arrows next to them are text glyphs, which land thin and small at the same font
 * size. Nothing lines up, and no amount of CSS fixes it, because none of those
 * shapes are under the page's control.
 *
 * These are. One 24x24 grid, one 1.9 stroke, round caps, `currentColor` — so the
 * whole rail inherits one colour, one weight and one optical size, and a state
 * change is a fill, not a different picture. `filled` is what the like and save
 * buttons toggle: the same outline, solid, so the shape never moves when it
 * activates.
 */
type IconProps = { filled?: boolean };

const S = {
  width: 24, height: 24, viewBox: "0 0 24 24",
  fill: "none", stroke: "currentColor",
  strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
};

export function HeartIcon({ filled }: IconProps) {
  return (
    <svg {...S} fill={filled ? "currentColor" : "none"} aria-hidden="true">
      <path d="M12 20s-7.2-4.4-9.1-8.4A5 5 0 0 1 12 6.1a5 5 0 0 1 9.1 5.5C19.2 15.6 12 20 12 20Z" />
    </svg>
  );
}

/** "This confused me" — a speech bubble, because it is a note back to the author. */
export function CommentIcon() {
  return (
    <svg {...S} aria-hidden="true">
      <path d="M20 12.5a7.5 7.5 0 0 1-10.9 6.7L4 20.5l1.4-4.7A7.5 7.5 0 1 1 20 12.5Z" />
      <path d="M9.6 10.2a2.4 2.4 0 1 1 3.3 2.2c-.6.3-.9.8-.9 1.4v.3" />
      <path d="M12 17.1h.01" />
    </svg>
  );
}

export function ShareIcon() {
  return (
    <svg {...S} aria-hidden="true">
      <path d="M8.6 13.1 15.4 17M15.4 7 8.6 10.9" />
      <circle cx="18" cy="5.4" r="2.6" />
      <circle cx="6" cy="12" r="2.6" />
      <circle cx="18" cy="18.6" r="2.6" />
    </svg>
  );
}

export function SaveIcon({ filled }: IconProps) {
  return (
    <svg {...S} fill={filled ? "currentColor" : "none"} aria-hidden="true">
      <path d="M6.5 3.8h11a1 1 0 0 1 1 1v15.4l-6.5-4-6.5 4V4.8a1 1 0 0 1 1-1Z" />
    </svg>
  );
}

export function DownloadIcon() {
  return (
    <svg {...S} aria-hidden="true">
      <path d="M12 3.6v10.8" />
      <path d="m7.6 10.4 4.4 4.4 4.4-4.4" />
      <path d="M4.4 19.2h15.2" />
    </svg>
  );
}

export function ReplayIcon() {
  return (
    <svg {...S} aria-hidden="true">
      <path d="M20 12a8 8 0 1 1-2.6-5.9" />
      <path d="M20.2 3.9v4.6h-4.6" />
    </svg>
  );
}

/** The rendering spinner — the same ring, open, turned by CSS. */
export function SpinnerIcon() {
  return (
    <svg {...S} aria-hidden="true">
      <path d="M12 3.6a8.4 8.4 0 1 1-8.4 8.4" opacity="0.95" />
    </svg>
  );
}

export function VolumeIcon({ level }: { level: "on" | "idle" | "off" | "warn" }) {
  if (level === "warn") {
    return (
      <svg {...S} aria-hidden="true">
        <path d="M12 4.2 3.6 19.1h16.8L12 4.2Z" />
        <path d="M12 10v3.4M12 16.4h.01" />
      </svg>
    );
  }
  return (
    <svg {...S} aria-hidden="true">
      <path d="M5 9.4h3.1L12.6 5.6v12.8L8.1 14.6H5a.8.8 0 0 1-.8-.8V10.2a.8.8 0 0 1 .8-.8Z"
            fill={level === "off" ? "none" : "currentColor"} />
      {level === "off"
        ? <path d="m16.4 9.6 4.2 4.8M20.6 9.6l-4.2 4.8" />
        : <>
            <path d="M16 9.7a3.6 3.6 0 0 1 0 4.6" />
            {level === "on" && <path d="M18.7 7.3a7.2 7.2 0 0 1 0 9.4" />}
          </>}
    </svg>
  );
}

/** Redraw these frames — a pen nib, for "say what to change about the picture". */
export function RedrawIcon() {
  return (
    <svg {...S} aria-hidden="true">
      <path d="M4.2 19.8h4l10-10a2.3 2.3 0 0 0-3.2-3.2l-10 10v3.2Z" />
      <path d="M13.6 7.4 16.6 10.4" />
    </svg>
  );
}
