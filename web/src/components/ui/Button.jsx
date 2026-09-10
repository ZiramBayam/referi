import { cn } from "../../lib/utils.js";

// CATATAN: JANGAN tambahkan `focus-visible:outline-none` di sini. `:focus-visible`
// di @layer base sudah meniadakan outline bawaan peramban untuk seluruh halaman;
// menuliskannya ulang sebagai utility membuatnya menang atas cincin fokus varian
// primary, dan aksi utama halaman kehilangan indikator keyboard-nya.
const base =
  "inline-flex items-center justify-center gap-2 font-medium whitespace-nowrap rounded-[10px] transition-[background,border-color,color,transform] duration-150 ease-out active:translate-y-px disabled:opacity-50 disabled:pointer-events-none";

/** @type {Record<string, string>} */
const variants = {
  // Sorotan inset di varian ini adalah utility `shadow-*`, dan ia MENANG atas cincin
  // `box-shadow` milik `:focus-visible` di @layer base, jadi aksi utama halaman adalah
  // satu-satunya kontrol yang tak terlihat saat di-Tab. Cincinnya dikembalikan sebagai
  // `outline` supaya tidak bertabrakan dengan mesin shadow Tailwind sama sekali;
  // varian lain tetap memakai cincin box-shadow global, dan rupanya sama.
  primary:
    "bg-primary text-on-primary hover:bg-primary-hover shadow-[0_1px_0_oklch(1_0_0/0.12)_inset] focus-visible:[outline:2px_solid_var(--ring)] focus-visible:[outline-offset:2px]",
  secondary: "bg-surface-2 text-ink border border-border hover:border-border-strong",
  ghost: "text-muted hover:text-ink hover:bg-surface",
};

/** @type {Record<string, string>} */
const sizes = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-[15px]",
};

/**
 * @param {string} [variant]
 * @param {string} [size]
 * @param {string} [className]
 */
export function buttonClasses(variant = "primary", size = "md", className) {
  return cn(base, variants[variant], sizes[size], className);
}

/** @param {any} props */
export function Button({ variant = "primary", size = "md", className, ...props }) {
  return <button className={buttonClasses(variant, size, className)} {...props} />;
}
