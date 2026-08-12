import type { UsageTotals } from "./api";

/**
 * Running spend, always on screen.
 *
 * Generation cost is invisible until the bill arrives, and the steps are wildly
 * uneven — suggesting topics is one cheap call, building one short is a call per
 * diagram plus an Opus judge call. The `~` marks an estimated figure, i.e. one
 * derived from a price table because the provider reported no cost.
 */
export function CostPill({ total, delta }: { total: UsageTotals; delta?: UsageTotals }) {
  return (
    <span className="costpill" title={breakdown(total)}>
      <b>{money(total.cost, total.estimated)}</b>
      <span className="tok">{tokens(total.input_tokens + total.output_tokens)}</span>
      {delta && delta.cost > 0 && <em>+{money(delta.cost, delta.estimated)}</em>}
    </span>
  );
}

export function money(v: number, estimated = false): string {
  const s = v < 0.01 && v > 0 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;
  return estimated ? `~${s}` : s;
}

export function tokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M tok`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k tok`;
  return `${n} tok`;
}

function breakdown(t: UsageTotals): string {
  const rows = Object.entries(t.by_label)
    .sort((a, b) => b[1].cost - a[1].cost)
    .map(([k, v]) => `${k}: ${v.calls} calls, ${tokens(v.tokens)}, ${money(v.cost)}`);
  return [`${t.calls} model calls`, ...rows].join("\n");
}
