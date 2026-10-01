// The frame every motion component draws into: 1080 x 1920 design units, a
// full-bleed colour field, and absolutely positioned layers. <Fit> scales the
// whole frame to any width with one CSS transform, so a component's numbers
// are always design units, never screen pixels.

import type { CSSProperties, ReactNode } from "react";
import iconData from "./icons.json";
import { FIELDS, FONT, H, W, type FieldName } from "./tokens";

import "./fonts.css";

const ICONS = (iconData as { icons: Record<string, string> }).icons;
export const ICON_NAMES = Object.keys(ICONS);

export function Frame({ field, children, style }: {
  field: FieldName; children?: ReactNode; style?: CSSProperties;
}) {
  return (
    <div style={{
      position: "relative", width: W, height: H, overflow: "hidden",
      background: FIELDS[field], fontFamily: FONT.body, ...style,
    }}>
      {children}
    </div>
  );
}

/** The frame scaled to `width` screen pixels. */
export function Fit({ width, children }: { width: number; children: ReactNode }) {
  const s = width / W;
  return (
    <div style={{ width, height: H * s, position: "relative", overflow: "hidden", flex: "none" }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H,
                    transform: `scale(${s})`, transformOrigin: "0 0" }}>
        {children}
      </div>
    </div>
  );
}

/** A full-frame layer. */
export function Layer({ children, style }: { children?: ReactNode; style?: CSSProperties }) {
  return <div style={{ position: "absolute", inset: 0, ...style }}>{children}</div>;
}

/** Something placed at (x, y) design units, optionally centred on that point. */
export function At({ x, y, center = false, children, style }: {
  x: number; y: number; center?: boolean; children?: ReactNode; style?: CSSProperties;
}) {
  return (
    <div style={{ position: "absolute", left: x, top: y,
                  transform: center ? "translate(-50%, -50%)" : undefined, ...style }}>
      {children}
    </div>
  );
}

/** A line icon from icons.json (24-unit grid, round caps). */
export function Icon({ name, size, color, fill = "none", stroke = 2, style }: {
  name: string; size: number; color: string; fill?: string; stroke?: number; style?: CSSProperties;
}) {
  const d = ICONS[name];
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ display: "block", ...style }}
         aria-hidden="true">
      {d && <path d={d} fill={fill} stroke={color} strokeWidth={stroke}
                  strokeLinecap="round" strokeLinejoin="round" />}
    </svg>
  );
}

/** The full-frame SVG overlay connectors and arrows draw on. */
export function Overlay({ children }: { children: ReactNode }) {
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}
         style={{ position: "absolute", inset: 0, overflow: "visible", pointerEvents: "none" }}>
      {children}
    </svg>
  );
}
