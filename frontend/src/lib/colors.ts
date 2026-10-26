/**
 * Deterministic color generation for stock symbols.
 * Produces curated, vibrant yet readable colors for event badges and calendar pills in dark mode.
 */

const PALETTE = [
  {
    bg: "rgba(59, 130, 246, 0.15)",
    border: "rgba(59, 130, 246, 0.4)",
    text: "#93c5fd",
    badge: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  },
  {
    bg: "rgba(16, 185, 129, 0.15)",
    border: "rgba(16, 185, 129, 0.4)",
    text: "#6ee7b7",
    badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  },
  {
    bg: "rgba(168, 85, 247, 0.15)",
    border: "rgba(168, 85, 247, 0.4)",
    text: "#d8b4fe",
    badge: "bg-purple-500/10 text-purple-400 border-purple-500/30",
  },
  {
    bg: "rgba(236, 72, 153, 0.15)",
    border: "rgba(236, 72, 153, 0.4)",
    text: "#f472b6",
    badge: "bg-pink-500/10 text-pink-400 border-pink-500/30",
  },
  {
    bg: "rgba(249, 115, 22, 0.15)",
    border: "rgba(249, 115, 22, 0.4)",
    text: "#fdba74",
    badge: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  },
  {
    bg: "rgba(20, 184, 166, 0.15)",
    border: "rgba(20, 184, 166, 0.4)",
    text: "#5eead4",
    badge: "bg-teal-500/10 text-teal-400 border-teal-500/30",
  },
  {
    bg: "rgba(99, 102, 241, 0.15)",
    border: "rgba(99, 102, 241, 0.4)",
    text: "#a5b4fc",
    badge: "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
  },
  {
    bg: "rgba(234, 179, 8, 0.15)",
    border: "rgba(234, 179, 8, 0.4)",
    text: "#fde047",
    badge: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  },
  {
    bg: "rgba(14, 165, 233, 0.15)",
    border: "rgba(14, 165, 233, 0.4)",
    text: "#7dd3fc",
    badge: "bg-sky-500/10 text-sky-400 border-sky-500/30",
  },
  {
    bg: "rgba(244, 63, 94, 0.15)",
    border: "rgba(244, 63, 94, 0.4)",
    text: "#fda4af",
    badge: "bg-rose-500/10 text-rose-400 border-rose-500/30",
  },
];

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export function getSymbolColor(symbol: string) {
  const index = hashString(symbol.toUpperCase()) % PALETTE.length;
  return PALETTE[index];
}

export const RESCHEDULED_STYLE = {
  bg: "rgba(245, 158, 11, 0.12)",
  border: "rgba(245, 158, 11, 0.5)",
  borderStyle: "dashed",
  text: "#fcd34d",
  badge: "bg-amber-500/15 text-amber-300 border-amber-500/40",
};
