"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useTheme } from "./theme/ThemeProvider.jsx";

/**
 * Latar ambient: bidang klaim yang belum terbukti, bintik netral tanpa arti, yang
 * MENGERAS jadi kisi bukti biru saat kursor menyapunya, seolah sebuah verifier sedang
 * dijalankan di atas bidang itu. Tesis produk dibuat bisa disentuh (jadikan yang tak
 * terlihat bisa dibaca), bukan hiasan: hanya sinyal yang sudah teruraikan yang berwarna
 * biru, di atas derau yang netral.
 *
 * Penyingkapannya sementara. Sebuah sel hanya diberi energi selagi lensa MENDEKATINYA,
 * dan selain itu meluruh dengan laju tetap, jadi petak yang mengeras tertinggal di
 * belakang kursor lalu memudar dalam durasi tetap. Diam di tempat, ia larut; halaman
 * yang menganggur hanya menampilkan derau.
 *
 * Menahan diri secara struktural:
 *  - bidang derau statis (digambar sekali ke buffer offscreen);
 *  - loop render digerbangi aktivitas: berhenti begitu lensa menetap dan penyingkapan
 *    memudar habis, jadi halaman menganggur tidak mengecat apa pun (tidak ada rAF abadi);
 *  - `prefers-reduced-motion` merender satu bingkai teruraikan dan tidak pernah melacak;
 *  - intensitasnya digerakkan token --wave-alpha (sadar tema).
 */
const CELL = 20; // ukuran sel kisi bukti (px)
const NOISE_GAP = 26; // jarak bintik klaim yang belum teruraikan (px)
const FOLLOW = 0.09; // easing lensa rendah, supaya perjalanannya terbaca sebagai jeda
const FADE = 0.02; // peluruhan tetap per bingkai → penyingkapan memudar ~0.8s

/** @param {number} p */
const ss = (p) => p * p * (3 - 2 * p); // falloff smoothstep

/**
 * Hash per-sel deterministik: satu wilayah selalu mengeras jadi pola yang sama.
 * @param {number} ix
 * @param {number} iy
 */
function bitAt(ix, iy) {
  const s = Math.sin(ix * 127.1 + iy * 311.7) * 43758.5453;
  return s - Math.floor(s); // 0..1
}

export function ProofLens() {
  const ref = useRef(/** @type {any} */ (null));
  const { theme } = useTheme();

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const cx = cv.getContext("2d");
    if (!cx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const isLight = theme === "light";
    const [BR, BG, BB] = [0, 78, 255]; // biru merek #004eff
    const NEUTRAL = isLight ? "0,0,0" : "247,247,247"; // derau chroma-0

    const waveAlpha =
      parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--wave-alpha")
      ) || (isLight ? 0.7 : 0.5);

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;
    let lensR = 150;
    let raf = 0;
    let running = false;

    const lens = { x: window.innerWidth / 2, y: window.innerHeight * 0.42 };
    const target = { x: lens.x, y: lens.y };
    let alpha = 0;
    let alphaTarget = 1;

    /** @type {Map<number, {c: number, p: number}>} */
    const cells = new Map();
    /** @param {number} ix @param {number} iy */
    const key = (ix, iy) => ix * 4096 + iy;

    const noise = document.createElement("canvas");
    const nctx = /** @type {any} */ (noise.getContext("2d"));

    function paintNoise() {
      noise.width = Math.floor(w * dpr);
      noise.height = Math.floor(h * dpr);
      nctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      nctx.clearRect(0, 0, w, h);
      for (let y = NOISE_GAP / 2; y < h; y += NOISE_GAP) {
        for (let x = NOISE_GAP / 2; x < w; x += NOISE_GAP) {
          const r = bitAt(Math.round(x), Math.round(y));
          if (r < 0.34) continue; // sebaran jarang & tidak rata (klaim, bukan grid)
          const a = waveAlpha * (0.04 + r * 0.05);
          nctx.fillStyle = `rgba(${NEUTRAL},${a})`;
          const s = r > 0.86 ? 2 : 1;
          nctx.fillRect(x, y, s, s);
        }
      }
    }

    function resize() {
      w = window.innerWidth;
      h = window.innerHeight;
      lensR = Math.max(110, Math.min(180, w * 0.14));
      cv.width = Math.floor(w * dpr);
      cv.height = Math.floor(h * dpr);
      cx.setTransform(dpr, 0, 0, dpr, 0, 0);
      paintNoise();
    }

    /**
     * Kedekatan (0..1, 0 di luar) tiap sel di dalam lensa.
     * @param {number} lx @param {number} ly
     */
    function region(lx, ly) {
      /** @type {Map<number, number>} */
      const out = new Map();
      if (alphaTarget <= 0) return out;
      const ix0 = Math.max(0, Math.floor((lx - lensR) / CELL));
      const ix1 = Math.ceil((lx + lensR) / CELL);
      const iy0 = Math.max(0, Math.floor((ly - lensR) / CELL));
      const iy1 = Math.ceil((ly + lensR) / CELL);
      for (let iy = iy0; iy <= iy1; iy++) {
        for (let ix = ix0; ix <= ix1; ix++) {
          const d = Math.hypot(ix * CELL + CELL / 2 - lx, iy * CELL + CELL / 2 - ly);
          if (d > lensR) continue;
          out.set(key(ix, iy), 1 - d / lensR);
        }
      }
      return out;
    }

    /**
     * Tiga jenis sel dari hash yang sama, dan ini yang membedakan bidang Referi dari
     * sidik jari perceptual-hash: kotak PADAT = kewajiban terpenuhi, kotak BERGARIS =
     * kewajiban terikat tapi belum terbukti, titik redup = klaim yang tak mengikat.
     *
     * @param {number} k @param {number} intensity
     */
    function drawCell(k, intensity) {
      const ix = Math.floor(k / 4096);
      const iy = k - ix * 4096;
      const r = bitAt(ix, iy);
      const solid = r > 0.72;
      const outlined = !solid && r > 0.55;
      const a = waveAlpha * intensity * (solid ? 0.55 : outlined ? 0.34 : 0.07) * alpha;
      if (a < 0.004) return;
      const x = ix * CELL;
      const y = iy * CELL;
      if (solid) {
        cx.fillStyle = `rgba(${BR},${BG},${BB},${a})`;
        cx.fillRect(x + 3, y + 3, CELL - 6, CELL - 6);
      } else if (outlined) {
        cx.strokeStyle = `rgba(${BR},${BG},${BB},${a})`;
        cx.lineWidth = 1;
        cx.strokeRect(x + 4.5, y + 4.5, CELL - 9, CELL - 9);
      } else {
        cx.fillStyle = `rgba(${BR},${BG},${BB},${a})`;
        cx.fillRect(x + 6, y + 6, CELL - 12, CELL - 12);
      }
    }

    function frame() {
      lens.x += (target.x - lens.x) * FOLLOW;
      lens.y += (target.y - lens.y) * FOLLOW;
      alpha += (alphaTarget - alpha) * FOLLOW;

      const prox = region(lens.x, lens.y);
      for (const k of prox.keys()) if (!cells.has(k)) cells.set(k, { c: 0, p: 0 });

      cx.clearRect(0, 0, w, h);
      cx.drawImage(noise, 0, 0, w, h);

      let active = false;
      for (const [k, st] of cells) {
        const p = prox.get(k) ?? 0;
        // Beri energi HANYA selagi lensa bergerak mendekat; tidak pernah saat berdiam.
        if (p > st.p + 0.0005) {
          const m = ss(p);
          if (m > st.c) st.c = m;
        }
        st.c -= FADE;
        if (st.c < 0) st.c = 0;
        st.p = p;

        if (st.c < 0.003 && p <= 0) {
          cells.delete(k);
          continue;
        }
        if (st.c > 0.003 || p > 0.0005) active = true;
        drawCell(k, st.c);
      }

      const moving =
        Math.abs(target.x - lens.x) > 0.4 ||
        Math.abs(target.y - lens.y) > 0.4 ||
        Math.abs(alphaTarget - alpha) > 0.01;

      if (!moving && !active) {
        running = false;
        return; // sudah menetap dan memudar habis; halaman menganggur tidak bekerja
      }
      raf = requestAnimationFrame(frame);
    }

    function staticFrame() {
      cx.clearRect(0, 0, w, h);
      cx.drawImage(noise, 0, 0, w, h);
      for (const [k, p] of region(lens.x, lens.y)) drawCell(k, ss(p));
    }

    function kick() {
      if (running || reduce || document.hidden) return;
      running = true;
      raf = requestAnimationFrame(frame);
    }

    /** @param {any} e */
    function onMove(e) {
      target.x = e.clientX;
      target.y = e.clientY;
      alphaTarget = 1;
      kick();
    }
    function onLeave() {
      alphaTarget = 0;
      kick();
    }
    function onVisibility() {
      if (document.hidden) {
        cancelAnimationFrame(raf);
        running = false;
      } else {
        kick();
      }
    }

    resize();
    window.addEventListener("resize", resize);

    if (reduce) {
      alpha = 1;
      staticFrame(); // satu bingkai teruraikan di tengah, tanpa pelacakan
    } else {
      window.addEventListener("pointermove", onMove, { passive: true });
      document.addEventListener("pointerleave", onLeave);
      document.addEventListener("visibilitychange", onVisibility);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [theme]);

  return (
    <canvas ref={ref} aria-hidden className="pointer-events-none fixed inset-0 z-0 h-full w-full" />
  );
}

/**
 * Memasang bidang ProofLens HANYA di halaman depan ("/"). Ia hidup di root layout
 * (bukan di page) supaya kanvasnya mempertahankan slot z-0 di belakang konteks
 * penumpukan z-10; pembatasan rutenya dilakukan di sini, bukan global.
 */
export function LandingLens() {
  const pathname = usePathname();
  if (pathname !== "/") return null;
  return <ProofLens />;
}
