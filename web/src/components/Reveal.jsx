"use client";

import { useEffect } from "react";

/**
 * Satu IntersectionObserver untuk seluruh halaman.
 *
 * MASALAH YANG DIPERBAIKINYA: animasi masuk sebelumnya berjalan saat halaman
 * DIMUAT. Langkah, baris tabel, dan jendela membaca semuanya ada jauh di bawah
 * lipatan, jadi gerakannya selesai sebelum siapa pun sempat melihatnya — biaya
 * penuh, nol manfaat.
 *
 * Elemen menyatakan diri lewat `data-reveal`; komponen ini menambahkan `is-in`
 * begitu elemen benar-benar masuk viewport, lalu BERHENTI mengamatinya. Sekali
 * muncul, selamanya muncul: mengulang animasi tiap kali digulir bolak-balik
 * membuat halaman rujukan terasa gelisah.
 *
 * Tanpa JavaScript, atau bila `IntersectionObserver` tidak ada, elemen tetap
 * terlihat — CSS-nya menyembunyikan HANYA di dalam blok `prefers-reduced-motion:
 * no-preference` DAN hanya ketika kelas penanda `js-reveal` sudah dipasang di
 * `<html>` oleh komponen ini. Jadi kegagalan apa pun berarti "tampil biasa",
 * bukan "halaman kosong".
 */
export default function Reveal() {
  useEffect(() => {
    const root = document.documentElement;
    if (!("IntersectionObserver" in window)) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;

    root.classList.add("js-reveal");

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          e.target.classList.add("is-in");
          io.unobserve(e.target);
        }
      },
      // Sedikit di dalam viewport, supaya gerakannya terlihat DIMULAI, bukan
      // sudah setengah jalan saat elemennya menyentuh tepi layar.
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 }
    );

    for (const el of document.querySelectorAll("[data-reveal]")) io.observe(el);
    return () => io.disconnect();
  }, []);

  return null;
}
