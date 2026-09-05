#!/usr/bin/env node
// Menghitung ulang `memory_root` DI LUAR Python, dari file ekspor JSON saja.
//
// Kenapa ini ada (AC task 2.1r (e), ADR-020 keputusan 6): spec §3 mengklaim "siapa pun bisa
// merekonstruksi root". Klaim itu tidak berarti apa-apa selama satu-satunya implementasinya
// Python — dan alat audit publiknya justru `web/` (TypeScript). Skrip ini adalah pembuktian
// klaim tersebut, sekaligus perangkap: kalau encoding Python berubah diam-diam, angka di sini
// berhenti cocok.
//
// Pakai:
//   node agent/tools/memory_root_check.mjs [file-ekspor.json]
// Default filenya vektor uji beku `agent/tests/fixtures/memory_root_vector.json`.
//
// TIDAK menambah dependensi (CLAUDE.md): keccak256 diambil dari paket yang SUDAH ada di
// store pnpm repo ini (`@noble/hashes`, transitif). Kalau tidak ketemu, skrip BERHENTI
// dengan pesan jelas — bukan diam-diam memakai hash lain.

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");

const ENCODING_VERSION = "evaluator-memory-root/v1";
const SECTIONS = [
  ["providers", "provider"],
  ["patterns", "reference:pattern"],
  ["rubrics", "reference:rubric"],
];

function loadKeccak256() {
  const store = path.join(REPO, "node_modules", ".pnpm");
  const candidates = [];
  if (fs.existsSync(store)) {
    for (const dir of fs.readdirSync(store)) {
      if (dir.startsWith("@noble+hashes@")) {
        candidates.push(path.join(store, dir, "node_modules", "@noble", "hashes", "sha3.js"));
      }
    }
  }
  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;
    const { keccak_256 } = require(file);
    if (typeof keccak_256 === "function") return (buf) => Buffer.from(keccak_256(buf));
  }
  throw new Error(
    "keccak256 tidak ditemukan. Jalankan `pnpm install` di root repo dulu; skrip ini sengaja " +
      "tidak menambah dependensi baru."
  );
}

// --- JSON kanonik: kunci terurut BYTE UTF-8, tanpa spasi, ASCII murni ------------------
// Harus sama persis dengan `json.dumps(..., sort_keys=True, separators=(",",":"),
// ensure_ascii=True)` di Python. Yang mudah terlewat: escape non-ASCII menjadi \uXXXX
// (JSON.stringify TIDAK melakukannya) dan urutan kunci menurut byte, bukan menurut UTF-16.
function asciiString(text) {
  let out = '"';
  for (const unit of text) {
    for (let i = 0; i < unit.length; i += 1) {
      const code = unit.charCodeAt(i);
      const ch = unit[i];
      if (ch === '"') out += '\\"';
      else if (ch === "\\") out += "\\\\";
      else if (ch === "\b") out += "\\b";
      else if (ch === "\f") out += "\\f";
      else if (ch === "\n") out += "\\n";
      else if (ch === "\r") out += "\\r";
      else if (ch === "\t") out += "\\t";
      else if (code < 0x20 || code > 0x7e) out += "\\u" + code.toString(16).padStart(4, "0");
      else out += ch;
    }
  }
  return out + '"';
}

// Kunci objek dibatasi ke ASCII cetak TANPA `"` dan `\` — cermin `BODY_KEY_RE` di
// `memory_policy.py`. Nama properti adalah satu-satunya bagian encoding ini yang harus
// dilewatkan ke `JSON.parse` sebagai NAMA, dan implementasi `JSON.parse` bebas punya cache
// nama properti sendiri; kalau tidak ada satu pun nama yang butuh escape, tidak ada yang
// bisa didekode berbeda. Karena kedua sisi menolak himpunan yang sama, keduanya sama-sama
// menghitung atau sama-sama BERHENTI — tidak pernah menghasilkan dua angka berbeda dari
// satu file. Berhenti keras di sini disengaja: alat audit yang menebak lebih buruk daripada
// alat audit yang bilang "aku tidak bisa membaca ini".
const BODY_KEY_RE = /^[\x20-\x21\x23-\x5b\x5d-\x7e]*$/;

function byteCompare(a, b) {
  return Buffer.compare(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));
}

function canonicalJson(value) {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return asciiString(value);
  if (typeof value === "number") {
    throw new Error(
      "ekspor memuat bilangan JSON; encoding ini melarangnya (uint256 rusak di atas 2^53)"
    );
  }
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  if (typeof value === "object") {
    const keys = Object.keys(value).sort(byteCompare);
    for (const k of keys) {
      if (!BODY_KEY_RE.test(k)) {
        throw new Error(
          `kunci body ${JSON.stringify(k)} butuh escape JSON; encoding ini melarangnya ` +
            "(lihat BODY_KEY_RE di agent/agent/memory_policy.py)"
        );
      }
    }
    return "{" + keys.map((k) => asciiString(k) + ":" + canonicalJson(value[k])).join(",") + "}";
  }
  throw new Error("tipe tidak dapat dikanonikkan: " + typeof value);
}

// --- bingkai panjang-berprefiks (netstring) --------------------------------------------
function frame(text) {
  const raw = Buffer.from(text, "utf8");
  return Buffer.concat([Buffer.from(String(raw.length) + ":", "ascii"), raw, Buffer.from(",", "ascii")]);
}

function section(tag, pairs) {
  const sorted = [...pairs].sort((a, b) => byteCompare(a[0], b[0]));
  const parts = [frame(tag), frame(String(sorted.length))];
  const seen = new Set();
  for (const [key, body] of sorted) {
    if (seen.has(key)) throw new Error(`kunci ${key} muncul dua kali di seksi ${tag}`);
    seen.add(key);
    parts.push(frame(key));
    parts.push(frame(canonicalJson(body)));
  }
  return Buffer.concat(parts);
}

function preimage(exported) {
  if (exported.version !== ENCODING_VERSION) {
    throw new Error(`ekspor memakai encoding ${exported.version}, skrip ini ${ENCODING_VERSION}`);
  }
  const parts = [frame(ENCODING_VERSION)];
  for (const [field, tag] of SECTIONS) parts.push(section(tag, exported[field] ?? []));
  return Buffer.concat(parts);
}

const file = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(REPO, "agent", "tests", "fixtures", "memory_root_vector.json");
const exported = JSON.parse(fs.readFileSync(file, "utf8"));
const bytes = preimage(exported);
const keccak256 = loadKeccak256();

process.stdout.write(`file       : ${path.relative(REPO, file)}\n`);
process.stdout.write(`encoding   : ${exported.version}\n`);
process.stdout.write(`preimage   : ${bytes.length} byte\n`);
process.stdout.write(`memory_root: 0x${keccak256(bytes).toString("hex")}\n`);
