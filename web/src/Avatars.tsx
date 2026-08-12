/**
 * The two characters.
 *
 * Drawn by hand as SVG rather than generated, on purpose: image models cannot
 * hold a character across ten videos, and these have to be the same person in
 * every short. Being vector also means they stay sharp at any reel size and cost
 * nothing to render.
 *
 * The interviewer is cool-toned and slightly narrower; the student is warm-toned
 * and rounder. They must be tellable apart at thumbnail size, so the difference
 * is in silhouette and hue, not in detail.
 */

type Props = { size?: number; speaking?: boolean; dim?: boolean };

export function Interviewer({ size = 96, speaking = false, dim = false }: Props) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} role="img"
         aria-label="Interviewer" className={avatarClass(speaking, dim)}>
      <defs>
        <linearGradient id="intBg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#1b3a5c" />
          <stop offset="100%" stopColor="#0e2438" />
        </linearGradient>
        <linearGradient id="intShirt" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4a7fb5" />
          <stop offset="100%" stopColor="#2f5c8a" />
        </linearGradient>
      </defs>
      <circle cx="60" cy="60" r="58" fill="url(#intBg)" />
      {/* shoulders */}
      <path d="M18 120c0-23 19-34 42-34s42 11 42 34z" fill="url(#intShirt)" />
      {/* collar */}
      <path d="M48 88l12 13 12-13-6-4h-12z" fill="#8fb4e8" opacity=".55" />
      {/* neck */}
      <rect x="52" y="72" width="16" height="16" rx="7" fill="#d9a878" />
      {/* head */}
      <ellipse cx="60" cy="52" rx="21" ry="24" fill="#e8bf93" />
      {/* hair — short, tidy, squared off */}
      <path d="M38 48c0-14 10-22 22-22s22 8 22 22c0-6-6-9-22-9s-22 3-22 9z" fill="#2b2118" />
      <path d="M37 48c-1-16 10-25 23-25s24 9 23 25c-2-11-11-16-23-16s-21 5-23 16z" fill="#3a2c20" />
      {/* glasses — the interviewer's tell */}
      <g stroke="#0f1a24" strokeWidth="2.4" fill="none" opacity=".85">
        <circle cx="51" cy="52" r="7.5" />
        <circle cx="69" cy="52" r="7.5" />
        <path d="M58.5 52h3M43.5 51l-4-2M76.5 51l4-2" />
      </g>
      {/* eyes */}
      <circle cx="51" cy="52" r="2.4" fill="#1a1410" />
      <circle cx="69" cy="52" r="2.4" fill="#1a1410" />
      {/* brows */}
      <path d="M45 42.5q6-3 12 0M63 42.5q6-3 12 0" stroke="#2b2118" strokeWidth="2.2"
            fill="none" strokeLinecap="round" />
      {/* mouth — asks, so slightly open when speaking */}
      {speaking ? (
        <ellipse cx="60" cy="64" rx="5" ry="4" fill="#7d3f3f" />
      ) : (
        <path d="M55 64q5 3 10 0" stroke="#7d3f3f" strokeWidth="2.2" fill="none"
              strokeLinecap="round" />
      )}
    </svg>
  );
}

export function Student({ size = 96, speaking = false, dim = false }: Props) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} role="img"
         aria-label="Student" className={avatarClass(speaking, dim)}>
      <defs>
        <linearGradient id="stuBg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#1d5c48" />
          <stop offset="100%" stopColor="#0d3328" />
        </linearGradient>
        <linearGradient id="stuHood" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2fbf8f" />
          <stop offset="100%" stopColor="#1d9e75" />
        </linearGradient>
      </defs>
      <circle cx="60" cy="60" r="58" fill="url(#stuBg)" />
      {/* shoulders — rounder than the interviewer's */}
      <path d="M14 120c0-25 21-36 46-36s46 11 46 36z" fill="url(#stuHood)" />
      {/* hoodie strings */}
      <path d="M52 90v14M68 90v11" stroke="#eafaf3" strokeWidth="2.6" strokeLinecap="round"
            opacity=".8" />
      {/* hood opening */}
      <path d="M44 86q16 10 32 0l-4-6H48z" fill="#0d3328" opacity=".35" />
      {/* neck */}
      <rect x="52" y="70" width="16" height="17" rx="7" fill="#c98d5f" />
      {/* head — rounder */}
      <circle cx="60" cy="51" r="23" fill="#e0a373" />
      {/* hair — curly, taller */}
      <g fill="#241a12">
        <circle cx="45" cy="36" r="9" />
        <circle cx="58" cy="30" r="10.5" />
        <circle cx="72" cy="35" r="9.5" />
        <circle cx="79" cy="45" r="7" />
        <circle cx="39" cy="46" r="7" />
      </g>
      {/* eyes — wide, curious */}
      <circle cx="52" cy="51" r="3" fill="#1a1410" />
      <circle cx="68" cy="51" r="3" fill="#1a1410" />
      <circle cx="53" cy="50" r="1" fill="#fff" opacity=".9" />
      <circle cx="69" cy="50" r="1" fill="#fff" opacity=".9" />
      {/* brows — raised, mid-explanation */}
      <path d="M46 42q6-3.5 12-1M62 41q6-2.5 12 1" stroke="#241a12" strokeWidth="2.2"
            fill="none" strokeLinecap="round" />
      {/* mouth — explaining */}
      {speaking ? (
        <ellipse cx="60" cy="63" rx="6" ry="5" fill="#6d3535" />
      ) : (
        <path d="M54 63q6 4 12 0" stroke="#6d3535" strokeWidth="2.4" fill="none"
              strokeLinecap="round" />
      )}
    </svg>
  );
}

function avatarClass(speaking: boolean, dim: boolean) {
  return ["avatar", speaking ? "speaking" : "", dim ? "dim" : ""].filter(Boolean).join(" ");
}

/** Pick the right character for a beat. */
export function Avatar({ speaker, ...rest }: Props & { speaker: "interviewer" | "student" }) {
  return speaker === "interviewer" ? <Interviewer {...rest} /> : <Student {...rest} />;
}
