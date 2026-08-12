/**
 * The two people, seated across a table, drawn as one scene.
 *
 * Circular head-and-shoulders avatars read as a contact list, not an interview.
 * This is a single composition instead: interviewer on the left in three-quarter
 * view, student on the right facing them, a desk between, a mic on it. Whoever is
 * talking leans in and brightens; the other dims and sits back — the same read
 * you get glancing at a real interview.
 *
 * Drawn by hand rather than generated because these must be the same two people
 * in every short, and an image model cannot hold a character across ten videos.
 */

export function InterviewScene({
  speaker, speaking,
}: {
  speaker: "interviewer" | "student";
  speaking: boolean;
}) {
  const asking = speaker === "interviewer";
  return (
    <svg viewBox="0 0 360 150" className="scene" role="img"
         aria-label={`${speaker} speaking`}>
      <defs>
        <linearGradient id="deskG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#16211f" />
          <stop offset="100%" stopColor="#0a1211" />
        </linearGradient>
        <linearGradient id="jacket" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3f6f9e" />
          <stop offset="100%" stopColor="#27496b" />
        </linearGradient>
        <linearGradient id="hoodie" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2ec792" />
          <stop offset="100%" stopColor="#18815f" />
        </linearGradient>
        <radialGradient id="spot" cx="50%" cy="0%" r="80%">
          <stop offset="0%" stopColor="rgba(255,255,255,.1)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0)" />
        </radialGradient>
      </defs>

      <rect x="0" y="0" width="360" height="150" fill="url(#spot)" />

      {/* ---------------------------------------------------- interviewer, left */}
      <g className={`person left${asking ? " on" : ""}`}>
        {/* torso, angled toward the centre */}
        <path d="M28 150c0-30 16-44 40-44s40 14 40 44z" fill="url(#jacket)" />
        <path d="M62 112l6 12 6-12-4-4h-4z" fill="#a8c8ea" opacity=".5" />
        <rect x="61" y="96" width="14" height="14" rx="6" fill="#d9a878" />
        {/* head, turned right */}
        <ellipse cx="70" cy="78" rx="19" ry="21" fill="#e8bf93" />
        <path d="M51 76c-1-15 9-23 19-23s19 8 19 23c-2-10-9-14-19-14s-17 4-19 14z"
              fill="#33261c" />
        {/* glasses — the interviewer's tell, readable at any size */}
        <g stroke="#101a22" strokeWidth="2" fill="none" opacity=".9">
          <circle cx="64" cy="78" r="6" />
          <circle cx="78" cy="78" r="6" />
          <path d="M70 78h2" />
        </g>
        <circle cx="64" cy="78" r="2" fill="#181310" />
        <circle cx="78" cy="78" r="2" fill="#181310" />
        <path d="M59 69q5-2.5 10 0M74 69q5-2.5 10 0" stroke="#33261c" strokeWidth="1.8"
              fill="none" strokeLinecap="round" />
        <g className={asking && speaking ? "mouth talking" : "mouth"}>
          {asking && speaking
            ? <ellipse cx="72" cy="88" rx="4" ry="3.2" fill="#7d3f3f" />
            : <path d="M68 88q4 2.4 8 0" stroke="#7d3f3f" strokeWidth="1.9" fill="none"
                    strokeLinecap="round" />}
        </g>
        {/* clipboard — he is the one asking */}
        <g transform="rotate(-8 34 126)">
          <rect x="22" y="116" width="24" height="30" rx="3" fill="#e6e2d6" />
          <rect x="29" y="113" width="10" height="5" rx="2" fill="#8d8f8c" />
          <path d="M27 124h14M27 130h14M27 136h9" stroke="#9aa0a0" strokeWidth="1.6"
                strokeLinecap="round" />
        </g>
      </g>

      {/* --------------------------------------------------------- student, right */}
      <g className={`person right${!asking ? " on" : ""}`}>
        <path d="M252 150c0-32 17-46 42-46s42 14 42 46z" fill="url(#hoodie)" />
        <path d="M284 116v16M300 116v13" stroke="#eafaf3" strokeWidth="2.2"
              strokeLinecap="round" opacity=".8" />
        <rect x="287" y="94" width="14" height="14" rx="6" fill="#c98d5f" />
        {/* head, turned left */}
        <circle cx="294" cy="76" r="20" fill="#e0a373" />
        <g fill="#241a12">
          <circle cx="281" cy="62" r="8" />
          <circle cx="293" cy="57" r="9" />
          <circle cx="306" cy="62" r="8" />
          <circle cx="311" cy="71" r="6" />
        </g>
        <circle cx="287" cy="77" r="2.5" fill="#181310" />
        <circle cx="301" cy="77" r="2.5" fill="#181310" />
        <circle cx="288" cy="76" r="0.9" fill="#fff" opacity=".9" />
        <circle cx="302" cy="76" r="0.9" fill="#fff" opacity=".9" />
        <path d="M282 68q5-3 10-1M297 67q5-2 10 1" stroke="#241a12" strokeWidth="1.8"
              fill="none" strokeLinecap="round" />
        <g className={!asking && speaking ? "mouth talking" : "mouth"}>
          {!asking && speaking
            ? <ellipse cx="294" cy="87" rx="4.6" ry="3.8" fill="#6d3535" />
            : <path d="M289 87q5 3 10 0" stroke="#6d3535" strokeWidth="2" fill="none"
                    strokeLinecap="round" />}
        </g>
        {/* gesturing hand — she is explaining */}
        <ellipse cx="258" cy="128" rx="7" ry="9" fill="#e0a373"
                 transform="rotate(18 258 128)" />
      </g>

      {/* ------------------------------------------------------------------ desk */}
      <path d="M96 150c0-14 30-22 84-22s84 8 84 22z" fill="url(#deskG)" />
      <path d="M96 150c0-14 30-22 84-22s84 8 84 22" fill="none"
            stroke="rgba(255,255,255,.08)" strokeWidth="1.4" />
      {/* mic, leaning to whoever is talking */}
      <g className="mic" transform={`rotate(${asking ? -12 : 12} 180 148)`}>
        <rect x="178" y="126" width="4" height="22" rx="2" fill="#5c6360" />
        <ellipse cx="180" cy="122" rx="7" ry="9" fill="#2b3230" />
        <ellipse cx="180" cy="122" rx="4.5" ry="6.5" fill="#464e4b" />
        {speaking && <circle cx="180" cy="122" r="12" className="micwave" />}
      </g>
    </svg>
  );
}
