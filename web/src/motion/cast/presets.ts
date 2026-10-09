// Character presets on the web side (learning-shorts): the defaults from
// presets.generated.json (shorts/motion_character_presets.yaml, exported), and
// the API the designer saves through (GET/PUT/DELETE
// /api/motion-characters/presets). Without the API server the pages still show
// every default; only saving needs it.

import { useCallback, useEffect, useState } from "react";
import data from "./presets.generated.json";
import identities from "../identity/identities.generated.json";
import type { CharacterConfig } from "../characters/skins/config";
import type { IdentitySpec } from "../identity/Identity";

type Options = Record<string, string[]>;
const D = data as unknown as {
  host: CharacterConfig; languages: Record<string, CharacterConfig>; extras: Record<string, CharacterConfig>; options: Options;
};
const IDS = identities as unknown as { host: IdentitySpec; languages: Record<string, IdentitySpec> };

export const OPTIONS: Options = D.options;
export const LANGUAGES: string[] = Object.keys(D.languages);
export const EXTRAS: string[] = Object.keys(D.extras);
/** Every preset id: the host, each language, each extra. */
export const PRESET_IDS: string[] = ["host", ...LANGUAGES, ...EXTRAS];

export function defaultPreset(id: string): CharacterConfig {
  return id === "host" ? D.host : D.languages[id] ?? D.extras[id];
}

/** The identity a preset belongs to (its badge and colours), if any. */
export function identityOf(id: string): IdentitySpec | null {
  return id === "host" ? IDS.host : IDS.languages[id] ?? null;
}

export function labelOf(id: string): string {
  if (id === "host") return "Host";
  return IDS.languages[id]?.name ?? id.charAt(0).toUpperCase() + id.slice(1);
}

export interface PresetState {
  /** the effective config of every preset: saved over default */
  effective: Record<string, CharacterConfig>;
  saved: Set<string>;
  /** the API server answered; saving works */
  api: boolean;
  loading: boolean;
  reload: () => void;
}

function defaults(): Record<string, CharacterConfig> {
  return Object.fromEntries(PRESET_IDS.map((id) => [id, defaultPreset(id)]));
}

export function usePresets(): PresetState {
  const [state, setState] = useState<Omit<PresetState, "reload">>({ effective: defaults(), saved: new Set(), api: false, loading: true });
  const reload = useCallback(() => {
    fetch("/api/motion-characters/presets")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: { effective: Record<string, CharacterConfig>; saved: Record<string, CharacterConfig> }) =>
        setState({ effective: { ...defaults(), ...j.effective }, saved: new Set(Object.keys(j.saved)), api: true, loading: false }))
      .catch(() => setState({ effective: defaults(), saved: new Set(), api: false, loading: false }));
  }, []);
  useEffect(reload, [reload]);
  return { ...state, reload };
}

async function call(method: "PUT" | "DELETE", id: string, body?: CharacterConfig): Promise<CharacterConfig> {
  const r = await fetch(`/api/motion-characters/presets/${encodeURIComponent(id)}`, {
    method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : `HTTP ${r.status}`);
  return j.config as CharacterConfig;
}

export const savePreset = (id: string, cfg: CharacterConfig) => call("PUT", id, cfg);
export const resetPreset = (id: string) => call("DELETE", id);
