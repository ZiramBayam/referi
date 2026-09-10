import { cn } from "../lib/utils.js";

/**
 * Wordmark Referi yang asli: huruf besar dengan spasi huruf lebar di muka display,
 * ditutup satu garis miring biru. Garis miring itu bagian dari tandanya, bukan hiasan,
 * jadi ia ikut di setiap penempatan.
 *
 * @param {{ className?: string, size?: number }} props
 */
export function Logo({ className, size = 19 }) {
  return (
    <span
      className={cn(
        "font-display font-semibold uppercase tracking-[0.08em] text-ink",
        className
      )}
      style={{ fontSize: size }}
    >
      REFERI
      <span className="ml-px text-primary">/</span>
    </span>
  );
}
