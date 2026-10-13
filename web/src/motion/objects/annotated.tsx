// Rev 2 objects (plan.rev >= 2, shorts/schema.py MotionPlan.rev): the
// first-real-reel fixes of 2026-10-13. Older plans keep the reference
// renderers in reference.tsx.
//
//   EndCardCued     the CTA, every step on a spoken word: Follow pressed on
//                   "follow", the Up next card slides in on "next", the
//                   hashtags pop one per word, a final settle

import { At, Icon } from "../Stage";
import { C, FONT, W } from "../tokens";
import { clamp, ease, seg } from "../time";
import { popStyle } from "./reference";
import type { IdentitySpec } from "../identity/Identity";
import { toneOn } from "../identity/Identity";

/** The CTA end card, rev 2. Ages are seconds since each step (negative or
 * 99 = not yet). `tagsShown`: how many hashtags have popped. */
export function EndCardCued({ series, upNext, tags, local, tapAge, revealAge, tagAges, settleAge, identity }: {
  series: string; upNext: string; tags: string[]; local: number; tapAge: number; revealAge: number;
  tagAges: number[]; settleAge: number; identity?: IdentitySpec | null;
}) {
  const press = tapAge >= 0 && tapAge < 0.35 ? Math.sin((tapAge / 0.35) * Math.PI) : 0;
  const followed = tapAge >= 0.15;
  const slide = revealAge >= 0 ? ease.outCubic(clamp(revealAge / 0.55)) : 0;
  const settle = settleAge >= 0 && settleAge < 0.6 ? Math.sin((settleAge / 0.6) * Math.PI) * 0.025 : 0;
  const ring = identity ? toneOn(identity, "navy") : C.yellow;
  return (
    <div style={{ position: "absolute", inset: 0, background: "var(--motion-card-bg, linear-gradient(to bottom, #5B4BF5, #4234D6))",
                  color: C.white, transform: `scale(${1 + settle})` }}>
      <At x={W / 2} y={560} center style={popStyle(seg(local, 0, 0.5))}>
        <div style={{ fontSize: 58, fontWeight: 800, letterSpacing: -1, whiteSpace: "nowrap" }}>{series}</div>
      </At>
      <At x={W / 2} y={700} center style={popStyle(seg(local, 0.12, 0.5))}>
        <div style={{ position: "relative" }}>
          {tapAge >= 0 && tapAge < 0.7 && (
            <div style={{ position: "absolute", left: "50%", top: "50%", width: 420, height: 130, borderRadius: 999,
                          border: `6px solid ${ring}`, opacity: 1 - tapAge / 0.7,
                          transform: `translate(-50%,-50%) scale(${1 + tapAge * 0.6})` }} />
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 18, padding: "30px 92px", borderRadius: 999,
                        background: followed ? "rgba(255,255,255,0.16)" : C.white, color: followed ? C.white : C.indigo,
                        border: `4px solid ${followed ? "rgba(255,255,255,0.5)" : C.white}`,
                        fontWeight: 800, fontSize: 50, transform: `scale(${1 - 0.08 * press})`, whiteSpace: "nowrap" }}>
            {followed && <Icon name="check" size={46} color={C.white} stroke={3} />}
            {followed ? "Following" : "Follow"}
          </div>
        </div>
      </At>
      {revealAge >= 0 && (
        <div style={{ position: "absolute", left: 90, top: 880, width: 900, opacity: clamp(revealAge / 0.08),
                      transform: `translateX(${(1 - slide) * 700}px)` }}>
          <div style={{ borderRadius: 36, padding: "36px 44px", background: "rgba(255,255,255,0.1)",
                        border: "3px solid rgba(255,255,255,0.28)" }}>
            <div style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 28, letterSpacing: 4, color: C.amber }}>UP NEXT</div>
            <div style={{ marginTop: 14, fontWeight: 800, lineHeight: 1.12,
                          fontSize: Math.min(64, Math.floor(1700 / Math.max(1, upNext.length * 0.55))) }}>{upNext}</div>
          </div>
        </div>
      )}
      <div style={{ position: "absolute", left: 60, right: 60, top: 1210, display: "flex", flexWrap: "wrap",
                    justifyContent: "center", gap: 18 }}>
        {tags.map((label, i) => {
          const age = tagAges[i] ?? -1;
          if (age < 0) return null;
          return (
            <div key={label} style={{ padding: "14px 28px", borderRadius: 999, background: "rgba(255,255,255,0.14)",
                                      fontFamily: FONT.mono, fontWeight: 700, fontSize: 32, whiteSpace: "nowrap",
                                      ...popStyle(clamp(age / 0.4)) }}>{label}</div>
          );
        })}
      </div>
    </div>
  );
}

