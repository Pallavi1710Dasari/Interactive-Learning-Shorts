// #motion-gallery/avatars — every avatar in every state (phase 3), for review
// and for docs/reference/phase3/ screenshots.
//   #motion-gallery/avatars              all characters, idle / talking / reacting
//   #motion-gallery/avatars/<id>         one character, three states, larger
// Query: t=<seconds> (default 1.3, mid-syllable and mid-reaction),
// field=<navy|blue|paper|yellow>.

import { Avatar, AVATAR_BOX, type AvatarSpec, type AvatarState } from "./Avatar";
import data from "./avatars.generated.json";
import { FIELDS, theme, type FieldName } from "../tokens";

const STATES: AvatarState[] = ["idle", "talking", "reacting"];

export function allAvatars(): { key: string; spec: AvatarSpec }[] {
  const d = data as unknown as { host: AvatarSpec; characters: Record<string, AvatarSpec> };
  return [{ key: "host", spec: d.host }, ...Object.entries(d.characters).map(([key, spec]) => ({ key, spec }))];
}

function Cell({ spec, state, t, size, field }: { spec: AvatarSpec; state: AvatarState; t: number; size: number; field: FieldName }) {
  const th = theme(field);
  return (
    <div style={{ background: FIELDS[field], borderRadius: 14, padding: "14px 10px 8px", textAlign: "center",
                  width: AVATAR_BOX.w * (size / AVATAR_BOX.h) + 20 }}>
      <Avatar spec={spec} state={state} t={t} since={state === "reacting" ? 0.45 : 99} size={size}
              outline={th.dark ? "rgba(255,255,255,0.85)" : "#151936"} />
      <div style={{ color: th.ink, fontWeight: 800, fontSize: 15, marginTop: 6 }}>{state}</div>
    </div>
  );
}

export function AvatarSheet({ id, t, field }: { id?: string; t: number; field: FieldName }) {
  const list = allAvatars().filter((a) => !id || a.key === id);
  const size = id ? 360 : 190;
  return (
    <div>
      <h1 style={{ margin: "0 0 4px", fontSize: 24 }}>Motion avatars{id ? ` — ${list[0]?.spec.name ?? id}` : ""}</h1>
      <p style={{ color: "#9AA0C0", fontSize: 13, margin: "0 0 18px" }}>
        Original characters from shorts/motion_avatars.yaml, one per course language plus the host. Idle, talking and
        reacting at t = {t.toFixed(2)}s. No logos, no mascots, no stick figures.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 22 }}>
        {list.map(({ key, spec }) => (
          <div key={key} style={{ background: "#151A33", borderRadius: 16, padding: 12 }}>
            <div style={{ fontWeight: 800, marginBottom: 8 }}>
              {spec.name} <span style={{ color: "#9AA0C0", fontWeight: 600, fontSize: 13 }}>{key}</span>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              {STATES.map((s) => <Cell key={s} spec={spec} state={s} t={t} size={size} field={field} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
