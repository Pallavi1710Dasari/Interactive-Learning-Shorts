// The language identity registry, as the Motion section shows it
// (#motion/identities): every language's badge on each of the four fields,
// its symbol large, its signature colour and the two field tones with their
// contrast, and the hook chip it opens a reel with. Read from
// identities.generated.json (shorts/motion_identities.py export).

import data from "./identities.generated.json";
import { IdentitySting, IdentitySymbol, IdentityTitle, LanguageBadge, SpeakerBadge, toneOn, type IdentitySpec } from "./Identity";
import { FIELDS, FIELD_NAMES, type FieldName } from "../tokens";
import { LARGE, SMALL_TEXT, contrastChecks, contrastRatio as ratio } from "./contrast";

const REG = data as unknown as { host: IdentitySpec; languages: Record<string, IdentitySpec> };

export function allIdentities(): { key: string; spec: IdentitySpec }[] {
  return [...Object.entries(REG.languages).map(([key, spec]) => ({ key, spec })), { key: "host", spec: REG.host }];
}

export const contrastRatio = ratio;

const muted = "#9AA0C0";

/** A part of the frame, scaled down: `w x h` design units at `scale`. */
function Mini({ field, w, h, scale, children }: { field: FieldName; w: number; h: number; scale: number; children: React.ReactNode }) {
  return (
    <div style={{ width: w * scale, height: h * scale, overflow: "hidden", borderRadius: 10, flex: "none", position: "relative" }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: w, height: h, background: FIELDS[field],
                    transform: `scale(${scale})`, transformOrigin: "0 0" }}>{children}</div>
    </div>
  );
}

function Row({ k, spec }: { k: string; spec: IdentitySpec }) {
  const host = k === "host";
  return (
    <div style={{ background: "#151A33", borderRadius: 14, padding: "14px 16px", display: "flex", gap: 20, alignItems: "center",
                  flexWrap: "wrap" }}>
      <div style={{ width: 140 }}>
        <div style={{ fontWeight: 800, fontSize: 18 }}>{spec.name}</div>
        <div style={{ color: muted, fontSize: 12 }}>{k}{spec.file ? ` · ${spec.file}` : ""}</div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {(["navy", "paper"] as FieldName[]).map((f) => (
          <div key={f} style={{ background: FIELDS[f], borderRadius: 12, padding: 10 }}>
            <IdentitySymbol spec={spec} size={92} colour={toneOn(spec, f)} />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
        {[["signature", spec.colour, ""], ["on dark (3:1)", spec.on_dark, "navy / blue"], ["on light (3:1)", spec.on_light, "paper / yellow"],
          ["text on dark (4.5:1)", spec.text_on_dark ?? "", "navy / blue"], ["text on light (4.5:1)", spec.text_on_light ?? "", "paper / yellow"]]
          .filter(([, c]) => c).map(([label, c, on]) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 20, height: 20, borderRadius: 5, background: c, border: "1px solid rgba(255,255,255,0.25)" }} />
            <span style={{ width: 210 }}>{label} {c}</span>
            {on && <span style={{ color: muted }}>{on.split(" / ").map((f) =>
              `${f} ${contrastRatio(c, FIELDS[f as FieldName]).toFixed(1)}:1`).join(" · ")}</span>}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {FIELD_NAMES.map((f) => (
            <Mini key={f} field={f} w={300} h={84} scale={0.62}>
              <LanguageBadge spec={spec} field={f} right={14} top={14} />
            </Mini>
          ))}
        </div>
        {!host ? (
          <Mini field="navy" w={760} h={300} scale={0.5}>
            <IdentityTitle spec={spec} label="Interview" field="navy" x={40} y={20} t={2} />
          </Mini>
        ) : (
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            {(["navy", "paper"] as FieldName[]).map((f) => (
              <div key={f} style={{ background: FIELDS[f], borderRadius: 12, padding: 14 }}>
                <SpeakerBadge member={{ role: "INTERVIEWER", side: "left", label: "Interviewer", voice_slot: "", identity: spec }}
                              field={f} active={false} t={0} size={72} />
              </div>
            ))}
            <span style={{ color: muted, fontSize: 12 }}>The host badge shows its role's initial.</span>
          </div>
        )}
      </div>
    </div>
  );
}

export function IdentitySheet() {
  return (
    <div>
      <p style={{ color: muted, fontSize: 13, margin: "0 0 14px", maxWidth: 980 }}>
        Every course language's identity (shorts/motion_identities.yaml): an original geometric symbol, a signature colour,
        and the two tones of it the player draws — one for the dark fields, one for the light — each at least 3:1 against
        both of its fields and clear of the reserved coral, mint and lavender. The badge sits in a reel's top-right corner
        for the whole reel; the hook opens with the symbol large and the chip ("REACT · INTERVIEW"). The grey host is the
        asking speaker of every two-speaker reel.
      </p>
      <div style={{ background: "#151A33", borderRadius: 14, padding: "14px 16px", marginBottom: 12 }}>
        <div style={{ fontWeight: 800, marginBottom: 4 }}>Intro sting <span style={{ color: muted, fontWeight: 600, fontSize: 13 }}>
          — optional, OFF by default (MOTION_INTRO_STING=1 adds it to plans written from then on). 1 second; frames at 0.15, 0.35, 0.55, 0.8 s.</span></div>
        {["react", "python", "os"].map((k) => (
          <div key={k} style={{ display: "flex", gap: 8, marginTop: 8 }}>
            {[0.15, 0.35, 0.55, 0.8].map((t) => (
              <Mini key={t} field="navy" w={1080} h={1080} scale={0.16}>
                <div style={{ position: "absolute", inset: 0 }}><IdentitySting spec={REG.languages[k]} t={t} /></div>
              </Mini>
            ))}
          </div>
        ))}
      </div>
      <ContrastTable />
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {allIdentities().map(({ key, spec }) => <Row key={key} k={key} spec={spec} />)}
      </div>
    </div>
  );
}

/** Every identity-coloured or chat text the player draws, by background:
 * the worst ratio over all 16 identities, against the bar it must meet
 * (4.5:1 small text, 3:1 large symbols and titles). Computed from the same
 * colour functions the player draws with (contrast.ts). */
function ContrastTable() {
  const rows = contrastChecks(allIdentities());
  const elements = [...new Set(rows.map((r) => r.element))];
  const cols: (FieldName | "end card")[] = [...FIELD_NAMES, "end card"];
  const fails = rows.filter((r) => r.ratio < r.min).length;
  const cell: React.CSSProperties = { padding: "6px 10px", borderTop: "1px solid #232A4D", fontFamily: "'JetBrains Mono', monospace", fontSize: 12 };
  return (
    <div style={{ background: "#151A33", borderRadius: 14, padding: "14px 16px", marginBottom: 12 }} data-part="contrast-table">
      <div style={{ fontWeight: 800, marginBottom: 2 }}>Contrast <span style={{ color: muted, fontWeight: 600, fontSize: 13 }}>
        — {rows.length} checks, {fails === 0 ? "all pass" : `${fails} FAIL`}</span></div>
      <div style={{ color: muted, fontSize: 12, marginBottom: 8, maxWidth: 980 }}>
        Small text must reach {SMALL_TEXT}:1 against what is behind it; large symbols and big titles {LARGE}:1. Each cell is the
        worst ratio over all {allIdentities().length} identities on that background (the bubble rows are per bubble, not per
        identity). Upcoming and older bubble words are dimmed by colour, never by transparency, so they keep {SMALL_TEXT}:1.
      </div>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr>
          <th style={{ ...cell, textAlign: "left", fontFamily: "inherit" }}>element</th>
          <th style={{ ...cell, fontFamily: "inherit" }}>needs</th>
          {cols.map((c) => <th key={c} style={{ ...cell, fontFamily: "inherit" }}>{c}</th>)}
        </tr></thead>
        <tbody>
          {elements.map((el) => {
            const mine = rows.filter((r) => r.element === el);
            return (
              <tr key={el}>
                <td style={{ ...cell, fontFamily: "inherit", fontSize: 13 }}>{el}</td>
                <td style={{ ...cell, textAlign: "center" }}>{mine[0].min}:1</td>
                {cols.map((c) => {
                  const here = mine.filter((r) => r.field === c);
                  if (!here.length) return <td key={c} style={cell} />;
                  const worst = here.reduce((a, b) => (b.ratio < a.ratio ? b : a));
                  const ok = worst.ratio >= worst.min;
                  return (
                    <td key={c} style={{ ...cell, textAlign: "center", color: ok ? "#E9EBF7" : "#F2555A" }}
                        title={`${worst.who}: ${worst.fg} on ${worst.bg}`}>
                      <span style={{ display: "inline-block", padding: "1px 6px", borderRadius: 4, background: worst.bg, color: worst.fg, marginRight: 6 }}>Aa</span>
                      {worst.ratio.toFixed(2)} {ok ? "✓" : "✗"}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
