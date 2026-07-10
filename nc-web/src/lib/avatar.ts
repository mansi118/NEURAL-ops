// Avatar helpers — deterministic initials + color from a name/mxid. Pure; unit-tested.

/** Up-to-two-letter initials from a display name or mxid (strips the @…: host and separators). */
export function initials(name: string): string {
  const parts = name.replace(/^@/, "").replace(/:.*/, "").split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0][0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

/** Stable HSL color derived from the name (same name → same color). */
export function colorFor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360} 55% 52%)`;
}
