import { cn } from "../../lib/utils.js";

/** Panel tenang: surface naik satu tingkat + garis rambut. Tanpa bayangan berat. */
/** @param {any} props */
export function Card({ className, ...props }) {
  return (
    <div
      className={cn("rounded-[var(--radius-card)] border border-border bg-surface", className)}
      {...props}
    />
  );
}
