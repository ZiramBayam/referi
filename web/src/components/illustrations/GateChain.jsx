"use client";

import { useRef } from "react";
import { useInView, useReducedMotion } from "motion/react";
import { cn } from "../../lib/utils.js";

/**
 * Rantai gerbang, digambar dan dijalankan.
 *
 * Ini satu-satunya ilustrasi di situs, dan ia ada karena kalimat tidak bisa
 * menunjukkan bentuk mekanismenya: SATU insiden mengompilasi SATU hipotesis, yang
 * memilih EMPAT kewajiban, yang seluruhnya harus bertemu di SATU gerbang sebelum
 * satu passport sekali-pakai dikeluarkan, dan bahwa dari passport itu hanya ada satu
 * jalan keluar yang diterima sementara pengulangannya ditolak.
 *
 * Animasinya menjalankan urutan itu, bukan menghias: tiap penghubung menggambar
 * dirinya dan tiap simpul menyala persis saat aliran tiba, sehingga arah bacanya
 * ikut bergerak. Semua pengaturan waktunya `animation-delay` di elemen masing-masing
 * dengan durasi loop yang sama, jadi gelombangnya tetap sebaris selamanya.
 *
 * Loop hanya hidup saat diagramnya terlihat (kelas dipasang lewat useInView), dan
 * `prefers-reduced-motion` mematikannya lewat aturan global di globals.css.
 *
 * Digambar dua kali, bukan diskalakan: versi mendatar untuk layar lebar, versi
 * menumpuk untuk ponsel. Satu SVG mendatar yang dikecilkan ke 340px akan membuat
 * labelnya sekitar 7px, dan diagram yang tidak terbaca lebih buruk daripada tidak
 * ada diagram.
 *
 * Semua warna memakai token, jadi ia ikut berganti bersama tema.
 */

const LINE = "var(--border-strong)";
const OBLIGATIONS = ["state anchor", "oracle freshness", "simulation match", "post-state"];

/** Detik ke berapa tiap tahap menyala di dalam satu putaran 5.2 detik. */
const T = {
  incident: 0,
  conn1: 0.3,
  hypothesis: 0.55,
  conn2: 0.85,
  rows: 1.25,
  rowStep: 0.12,
  converge: 1.75,
  gate: 2.3,
  conn3: 2.55,
  stamp: 2.8,
  accept: 3.0,
  refuse: 3.2,
};

/** @param {number} d */
const at = (d) => ({ animationDelay: `${d}s` });

export function GateChain() {
  const ref = useRef(/** @type {any} */ (null));
  const reduce = useReducedMotion();
  const inView = useInView(ref, { margin: "-10%" });
  // Diam saat di luar layar: loop hias yang terus berputar di balik lipatan itu
  // biaya baterai tanpa penonton.
  const run = inView && !reduce;

  return (
    <div ref={ref}>
      <Horizontal run={run} />
      <Stacked run={run} />
    </div>
  );
}

/** @param {{ run: boolean }} props */
function Horizontal({ run }) {
  const draw = cn(run && "chain-draw");
  const node = cn(run && "chain-node");

  return (
    <svg
      viewBox="0 44 900 192"
      width="100%"
      className="hidden h-auto sm:block"
      role="img"
      aria-labelledby="gate-chain-title gate-chain-desc"
    >
      <title id="gate-chain-title">How one incident becomes one permission</title>
      <desc id="gate-chain-desc">
        A stale-oracle incident compiles into a Control Hypothesis, which selects four proof
        obligations. All four converge on a single gate. Only when every one holds does the gate
        issue a single-use Execution Passport, which admits exactly one call and refuses a replay.
      </desc>

      {/* 01 insiden */}
      <rect x="6" y="80" width="150" height="90" rx="10" fill="none" stroke="var(--proof-review)" strokeOpacity="0.4" />
      <circle className={node} style={at(T.incident)} cx="28" cy="106" r="6" fill="none" stroke="var(--proof-review)" strokeWidth="1.5" />
      <text x="44" y="110" className="font-mono" fontSize="10" letterSpacing="0.12em" fill="var(--faint)">01 INCIDENT</text>
      <text x="22" y="140" className="font-sans" fontSize="13" fill="var(--ink)">a stale oracle</text>
      <text x="22" y="157" className="font-sans" fontSize="13" fill="var(--ink)">moved value once</text>

      <line className={draw} style={at(T.conn1)} pathLength="100" x1="156" y1="125" x2="179" y2="125" stroke={LINE} strokeWidth="1.25" />
      <path className={node} style={at(T.hypothesis)} d="M179 121 l7 4 l-7 4 z" fill={LINE} />

      {/* 02 hipotesis */}
      <rect x="190" y="80" width="170" height="90" rx="10" fill="none" stroke="var(--border)" />
      <circle className={node} style={at(T.hypothesis)} cx="212" cy="106" r="6" fill="var(--primary)" />
      <text x="228" y="110" className="font-mono" fontSize="10" letterSpacing="0.12em" fill="var(--faint)">02 HYPOTHESIS</text>
      <text x="206" y="140" className="font-sans" fontSize="13" fill="var(--ink)">the mechanism,</text>
      <text x="206" y="157" className="font-sans" fontSize="13" fill="var(--ink)">not the symptom</text>

      <line className={draw} style={at(T.conn2)} pathLength="100" x1="360" y1="125" x2="383" y2="125" stroke={LINE} strokeWidth="1.25" />
      <path className={node} style={at(T.rows)} d="M383 121 l7 4 l-7 4 z" fill={LINE} />

      {/* 03 empat kewajiban */}
      <rect x="394" y="62" width="206" height="126" rx="10" fill="none" stroke="var(--border)" />
      <text x="410" y="84" className="font-mono" fontSize="10" letterSpacing="0.12em" fill="var(--faint)">03 OBLIGATIONS</text>
      {OBLIGATIONS.map((label, i) => {
        const y = 106 + i * 22;
        return (
          <g key={label}>
            <circle className={node} style={at(T.rows + i * T.rowStep)} cx="416" cy={y - 4} r="4" fill="none" stroke="var(--primary-ink)" strokeWidth="1.25" />
            <text x="430" y={y} className="font-mono" fontSize="11" fill="var(--muted)">
              {label}
            </text>
            {/* Keempatnya bertemu di titik gerbang yang sama, dan itulah gambarnya. */}
            <line className={draw} style={at(T.converge + i * T.rowStep)} pathLength="100" x1="600" y1={y - 4} x2="638" y2="125" stroke={LINE} strokeWidth="1" strokeOpacity="0.7" />
          </g>
        );
      })}

      {/* Gerbang: dua palang dengan satu celah */}
      <g className={cn(run && "chain-gate")} style={at(T.gate)}>
        <line x1="642" y1="52" x2="642" y2="112" stroke="var(--ink)" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="642" y1="138" x2="642" y2="198" stroke="var(--ink)" strokeWidth="2.5" strokeLinecap="round" />
      </g>
      <text x="642" y="220" textAnchor="middle" className="font-mono" fontSize="10" letterSpacing="0.12em" fill="var(--faint)">GATE</text>

      <line className={draw} style={at(T.conn3)} pathLength="100" x1="650" y1="125" x2="676" y2="125" stroke={LINE} strokeWidth="1.25" />

      {/* 04 passport, stempel bersudut */}
      <rect className={node} style={at(T.stamp)} x="686" y="115" width="20" height="20" transform="rotate(45 696 125)" fill="var(--primary)" />
      {/* Keterangan MENGAPIT stempel, tidak di bawahnya: kedua cabang berangkat dari
          sudut bawah stempel dan menyebar, jadi apa pun di bawahnya pasti tercoret. */}
      <text x="700" y="172" textAnchor="middle" className="font-mono" fontSize="10" letterSpacing="0.1em" fill="var(--faint)">04 PASSPORT</text>
      <text x="700" y="190" textAnchor="middle" className="font-sans" fontSize="13" fill="var(--ink)">single use</text>

      {/* Dua jalan keluar: satu diterima, satu ditolak */}
      <path className={draw} style={at(T.accept)} pathLength="100" d="M706 118 C 740 96, 760 92, 786 92" fill="none" stroke="var(--proof-pass)" strokeWidth="1.25" />
      <circle className={node} style={at(T.accept)} cx="790" cy="92" r="4" fill="var(--proof-pass)" />
      <text x="802" y="96" className="font-mono" fontSize="11" fill="var(--proof-pass)">exact call</text>

      <path className={node} style={at(T.refuse)} d="M706 132 C 740 154, 760 158, 782 158" fill="none" stroke="var(--proof-block)" strokeWidth="1.25" strokeDasharray="4 4" />
      <g className={node} style={at(T.refuse)} stroke="var(--proof-block)" strokeWidth="1.75" strokeLinecap="round">
        <line x1="786" y1="154" x2="794" y2="162" />
        <line x1="794" y1="154" x2="786" y2="162" />
      </g>
      <text x="802" y="162" className="font-mono" fontSize="11" fill="var(--proof-block)">replay</text>
    </svg>
  );
}

/** @param {{ run: boolean }} props */
function Stacked({ run }) {
  const draw = cn(run && "chain-draw");
  const node = cn(run && "chain-node");

  return (
    <svg
      viewBox="0 0 320 560"
      width="100%"
      className="h-auto sm:hidden"
      role="img"
      aria-labelledby="gate-chain-title-s gate-chain-desc-s"
    >
      <title id="gate-chain-title-s">How one incident becomes one permission</title>
      <desc id="gate-chain-desc-s">
        A stale-oracle incident compiles into a Control Hypothesis, which selects four proof
        obligations. All four converge on a single gate. Only when every one holds does the gate
        issue a single-use Execution Passport, which admits exactly one call and refuses a replay.
      </desc>

      <rect x="4" y="4" width="312" height="74" rx="10" fill="none" stroke="var(--proof-review)" strokeOpacity="0.4" />
      <circle className={node} style={at(T.incident)} cx="26" cy="28" r="6" fill="none" stroke="var(--proof-review)" strokeWidth="1.5" />
      <text x="42" y="32" className="font-mono" fontSize="11" letterSpacing="0.12em" fill="var(--faint)">01 INCIDENT</text>
      <text x="20" y="60" className="font-sans" fontSize="14" fill="var(--ink)">a stale oracle moved value once</text>

      <line className={draw} style={at(T.conn1)} pathLength="100" x1="160" y1="78" x2="160" y2="98" stroke={LINE} strokeWidth="1.25" />
      <path className={node} style={at(T.hypothesis)} d="M160 105 l-4 -7 h8 z" fill={LINE} />

      <rect x="4" y="108" width="312" height="74" rx="10" fill="none" stroke="var(--border)" />
      <circle className={node} style={at(T.hypothesis)} cx="26" cy="132" r="6" fill="var(--primary)" />
      <text x="42" y="136" className="font-mono" fontSize="11" letterSpacing="0.12em" fill="var(--faint)">02 HYPOTHESIS</text>
      <text x="20" y="164" className="font-sans" fontSize="14" fill="var(--ink)">the mechanism, not the symptom</text>

      <line className={draw} style={at(T.conn2)} pathLength="100" x1="160" y1="182" x2="160" y2="202" stroke={LINE} strokeWidth="1.25" />
      <path className={node} style={at(T.rows)} d="M160 209 l-4 -7 h8 z" fill={LINE} />

      <rect x="4" y="212" width="312" height="132" rx="10" fill="none" stroke="var(--border)" />
      <text x="20" y="236" className="font-mono" fontSize="11" letterSpacing="0.12em" fill="var(--faint)">03 OBLIGATIONS</text>
      {OBLIGATIONS.map((label, i) => {
        const y = 262 + i * 22;
        return (
          <g key={label}>
            <circle className={node} style={at(T.rows + i * T.rowStep)} cx="26" cy={y - 4} r="4" fill="none" stroke="var(--primary-ink)" strokeWidth="1.25" />
            <text x="42" y={y} className="font-mono" fontSize="12" fill="var(--muted)">
              {label}
            </text>
            {/* Cabang pendek ke rel kanan. Versi mendatar bisa memancarkan empat garis
                langsung ke gerbang karena gerbangnya ADA di sebelah kanan; di sini
                gerbangnya di bawah, jadi keempatnya dikumpulkan dulu ke satu rel. */}
            <line className={draw} style={at(T.converge + i * T.rowStep)} pathLength="100" x1="286" y1={y - 4} x2="296" y2={y - 4} stroke={LINE} strokeWidth="1" strokeOpacity="0.8" />
          </g>
        );
      })}
      {/* Rel: keempat kewajiban menjadi satu jalur, dan HANYA jalur itu menyentuh gerbang. */}
      <line className={draw} style={at(T.converge + 4 * T.rowStep)} pathLength="100" x1="296" y1="258" x2="296" y2="324" stroke={LINE} strokeWidth="1" strokeOpacity="0.8" />
      <path className={draw} style={at(T.gate - 0.15)} pathLength="100" d="M296 324 C 296 352, 232 356, 172 368" fill="none" stroke={LINE} strokeWidth="1.25" />

      <g className={cn(run && "chain-gate")} style={at(T.gate)}>
        <line x1="86" y1="380" x2="140" y2="380" stroke="var(--ink)" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="180" y1="380" x2="234" y2="380" stroke="var(--ink)" strokeWidth="2.5" strokeLinecap="round" />
      </g>
      <text x="160" y="404" textAnchor="middle" className="font-mono" fontSize="11" letterSpacing="0.12em" fill="var(--faint)">GATE</text>

      <line className={draw} style={at(T.conn3)} pathLength="100" x1="160" y1="410" x2="160" y2="430" stroke={LINE} strokeWidth="1.25" />

      <rect className={node} style={at(T.stamp)} x="150" y="434" width="20" height="20" transform="rotate(45 160 444)" fill="var(--primary)" />
      <text x="138" y="449" textAnchor="end" className="font-mono" fontSize="11" letterSpacing="0.1em" fill="var(--faint)">04 PASSPORT</text>
      <text x="182" y="449" textAnchor="start" className="font-sans" fontSize="13" fill="var(--ink)">single use</text>

      <path className={draw} style={at(T.accept)} pathLength="100" d="M152 458 C 120 486, 108 496, 92 508" fill="none" stroke="var(--proof-pass)" strokeWidth="1.25" />
      <circle className={node} style={at(T.accept)} cx="88" cy="512" r="4" fill="var(--proof-pass)" />
      <text x="76" y="536" textAnchor="middle" className="font-mono" fontSize="12" fill="var(--proof-pass)">exact call</text>

      <path className={node} style={at(T.refuse)} d="M168 458 C 200 486, 212 496, 226 506" fill="none" stroke="var(--proof-block)" strokeWidth="1.25" strokeDasharray="4 4" />
      <g className={node} style={at(T.refuse)} stroke="var(--proof-block)" strokeWidth="1.75" strokeLinecap="round">
        <line x1="228" y1="508" x2="238" y2="518" />
        <line x1="238" y1="508" x2="228" y2="518" />
      </g>
      <text x="240" y="536" textAnchor="middle" className="font-mono" fontSize="12" fill="var(--proof-block)">replay</text>
    </svg>
  );
}
