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
// Surrogate YATIM: `Buffer.from(s,"utf8")` menukarnya dengan `EF BF BD` (U+FFFD) DIAM-DIAM,
// sedangkan Python `str.encode("utf-8")` MELEMPAR. Tanpa penjaga ini, `pattern:\ud800`,
// `pattern:\udfff`, dan `pattern:\ufffd` (yang SAH) menghasilkan root yang SAMA di sini —
// tiga kunci berbeda runtuh jadi satu, dan file palsu bisa meminjam root yang jujur.
// Dijaga di titik encode, bukan hanya di validator, supaya tidak ada jalur yang terlewat.
function assertWellFormed(text) {
  if (typeof text.isWellFormed === "function" ? !text.isWellFormed() : /[\uD800-\uDFFF]/.test(
    text.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, "")
  )) {
    throw new Error(
      `bagian preimage bukan UTF-8 well-formed (surrogate yatim): ${JSON.stringify(text)}`
    );
  }
}

function frame(text) {
  assertWellFormed(text);
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

// --- VALIDASI: cermin `MemorySnapshot.from_mapping` + `decanonical_value` di Python -------
// Sampai review 2.1b, skrip ini hanya menghitung. Akibatnya bisa diadili dengan satu kalimat:
// alat audit PUBLIK kita mencetak root JUJUR untuk file yang isinya BUKAN itu — pasangan
// `[kunci, body, EXTRA]` dengan profil palsu di elemen ketiga tetap menghasilkan root vektor
// beku, karena elemen ketiga diabaikan diam-diam. Karena itu setiap penjaga Python punya
// kembarannya di sini, dan keduanya BERHENTI di titik yang sama.
const ADDRESS_RE = /^0x[0-9a-f]{40}$/;
const EXPORT_FIELDS = new Set(["version", "providers", "patterns", "rubrics"]);
const NUMBER_TAG = "$u";
// Bentuk desimal KANONIK — satu bentuk per angka. `-0` sengaja di luar: Python mendekode
// `{"$u":"-0"}` menjadi 0 lalu meng-encode ulang `"0"`, skrip ini menghash `"-0"` apa adanya.
// Satu file, dua root. Ditolak di KEDUA sisi, bukan "dipilih" salah satu.
const DECIMAL_RE = /^(0|-?[1-9][0-9]*)$/;
// uint256 = 78 digit. Cermin `MAX_DECIMAL_DIGITS` di Python. Batas ini BUKAN kerapian:
// tanpa ia, `{"$u":"1"+"0".repeat(5000)}` dihitung di sini sementara `int()` di CPython
// melempar `ValueError` pada 4300 digit — satu file, satu sisi mati, sisi lain mencetak root.
const MAX_DECIMAL_DIGITS = 78;
const MAX_UINT256 = (1n << 256n) - 1n;
const SECTION_KEY_RULES = { providers: null, patterns: "pattern:", rubrics: "rubric:" };

function validateBody(value, depth = 0) {
  if (depth > 32) throw new Error("body ekspor terlalu dalam");
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    assertWellFormed(value);
    return;
  }
  if (typeof value === "number") {
    throw new Error("ekspor memuat bilangan JSON; encoding ini melarangnya (rusak di atas 2^53)");
  }
  if (Array.isArray(value)) {
    for (const item of value) validateBody(item, depth + 1);
    return;
  }
  if (typeof value !== "object") throw new Error("tipe tidak dapat dikanonikkan: " + typeof value);
  const keys = Object.keys(value);
  if (keys.includes(NUMBER_TAG)) {
    if (keys.length !== 1) {
      throw new Error(
        `kunci ${NUMBER_TAG} hanya sah sebagai penanda integer tunggal, dapat ${JSON.stringify(value)}`
      );
    }
    const text = value[NUMBER_TAG];
    if (typeof text !== "string" || !DECIMAL_RE.test(text)) {
      throw new Error(
        `penanda integer ${JSON.stringify(value)} bukan desimal KANONIK ` +
          "(tanpa -0, tanpa nol di depan, tanpa tanda +)"
      );
    }
    const digits = text.startsWith("-") ? text.length - 1 : text.length;
    if (digits > MAX_DECIMAL_DIGITS) {
      throw new Error(
        `integer ${digits} digit melewati batas ${MAX_DECIMAL_DIGITS} (uint256)`
      );
    }
    // 2**256 JUGA 78 digit, jadi panjang saja bukan batas. `BigInt` di sini aman: panjangnya
    // sudah dibatasi di atas.
    const nilai = BigInt(text);
    if (nilai > MAX_UINT256 || nilai < -MAX_UINT256) {
      throw new Error(`integer ${text} di luar rentang uint256`);
    }
    return;
  }
  for (const k of keys) {
    if (!BODY_KEY_RE.test(k)) {
      throw new Error(
        `kunci body ${JSON.stringify(k)} butuh escape JSON; encoding ini melarangnya ` +
          "(lihat BODY_KEY_RE di agent/agent/memory_policy.py)"
      );
    }
    validateBody(value[k], depth + 1);
  }
}

function validateExport(exported) {
  if (exported === null || typeof exported !== "object" || Array.isArray(exported)) {
    throw new Error("file ekspor harus objek JSON di level teratas");
  }
  if (exported.version !== ENCODING_VERSION) {
    throw new Error(`ekspor memakai encoding ${exported.version}, skrip ini ${ENCODING_VERSION}`);
  }
  for (const field of Object.keys(exported)) {
    if (!EXPORT_FIELDS.has(field)) {
      // Field top-level asing TIDAK ikut ter-hash: ia bisa bercerita lain kepada manusia
      // daripada yang diikat root.
      throw new Error(`ekspor memuat field top-level yang tidak dijangkar root: ${field}`);
    }
  }
  for (const [field, prefix] of Object.entries(SECTION_KEY_RULES)) {
    const rows = exported[field] === undefined ? [] : exported[field];
    if (!Array.isArray(rows)) throw new Error(`seksi ${field} harus array, dapat ${rows === null ? "null" : typeof rows}`);
    for (const item of rows) {
      if (!Array.isArray(item) || item.length !== 2) {
        throw new Error(
          `entri seksi ${field} harus pasangan [kunci, body], dapat ${JSON.stringify(item)}`
        );
      }
      const [key, body] = item;
      if (typeof key !== "string") throw new Error(`kunci seksi ${field} harus string`);
      assertWellFormed(key);
      if (prefix === null) {
        // Cermin `normalize_address` + tuntutan kanonisitas `from_mapping`: nama yang
        // dijangkar root WAJIB nama yang dibaca jalur keputusan, huruf demi huruf.
        if (!ADDRESS_RE.test(key)) {
          throw new Error(
            `nama entity provider ${JSON.stringify(key)} bukan alamat 0x + 40 hex huruf kecil`
          );
        }
      } else if (!key.startsWith(prefix)) {
        throw new Error(
          `kunci reference ${JSON.stringify(key)} di seksi ${field} tidak berawalan ${prefix} — ` +
            "ia akan dijangkar root tetapi tidak pernah dibaca jalur keputusan"
        );
      }
      validateBody(body);
    }
  }
}

function preimage(exported) {
  validateExport(exported);
  const parts = [frame(ENCODING_VERSION)];
  for (const [field, tag] of SECTIONS) parts.push(section(tag, exported[field] ?? []));
  return Buffer.concat(parts);
}

// --- penjaga SUMBER: nama properti tidak boleh ber-escape -------------------------------
// `BODY_KEY_RE` di atas menolak kunci yang BUTUH escape sesudah didekode. Yang tersisa adalah
// kunci yang DITULIS ber-escape padahal hasil dekodenya legal (`"k\u0042"` -> `kB`), dan itu
// terbukti berbahaya: V8 mengintern nama properti ber-backslash LINTAS panggilan `JSON.parse`
// dalam satu isolate, sehingga dokumen berikutnya bisa membaca nama hasil intern milik dokumen
// sebelumnya. Skrip ini sendiri hanya mem-parse satu file per proses sehingga tidak terpapar —
// tapi `web/` adalah isolate berumur panjang yang mem-parse banyak ekspor, dan alat audit tidak
// boleh MENERIMA file yang memancing bug itu hanya karena kebetulan dirinya aman.
// Diperiksa DI ATAS TEKS, sebelum JSON.parse: sesudah dekode buktinya sudah hilang.
// Cermin `assert_no_escaped_object_keys` di `agent/agent/memory_export.py`.
function assertNoEscapedObjectKeys(text) {
  let i = 0;
  while (i < text.length) {
    if (text[i] !== '"') {
      i += 1;
      continue;
    }
    const start = i;
    i += 1;
    while (i < text.length) {
      if (text[i] === "\\") {
        i += 2;
        continue;
      }
      if (text[i] === '"') break;
      i += 1;
    }
    if (i >= text.length) throw new Error("file bukan JSON yang sah (string tidak ditutup)");
    const raw = text.slice(start, i + 1);
    i += 1;
    let j = i;
    while (j < text.length && " \t\r\n".includes(text[j])) j += 1;
    const isKey = j < text.length && text[j] === ":";
    if (!isKey) continue;
    let suspect = raw.includes("\\");
    for (let k = 0; !suspect && k < raw.length; k += 1) {
      const code = raw.charCodeAt(k);
      if (code < 0x20 || code > 0x7e) suspect = true;
    }
    if (suspect) {
      throw new Error(
        `nama properti ${raw} butuh escape di SUMBER JSON; encoding ini melarangnya ` +
          "(lihat assert_no_escaped_object_keys di agent/agent/memory_export.py)"
      );
    }
  }
}

const file = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(REPO, "agent", "tests", "fixtures", "memory_root_vector.json");
const bytesOnDisk = fs.readFileSync(file);
const source = bytesOnDisk.toString("utf8");
// UTF-8 ILEGAL: `toString("utf8")` menggantinya dengan U+FFFD tanpa satu pun keluhan, jadi
// file rusak tetap menghasilkan root — sementara Python `read_text` MATI. Dua perilaku
// berbeda atas file yang sama adalah persis yang tidak boleh ada di alat audit.
if (Buffer.compare(Buffer.from(source, "utf8"), bytesOnDisk) !== 0) {
  throw new Error("file ekspor bukan UTF-8 yang sah");
}
assertNoEscapedObjectKeys(source);
const exported = JSON.parse(source);
const bytes = preimage(exported);
const keccak256 = loadKeccak256();

process.stdout.write(`file       : ${path.relative(REPO, file)}\n`);
process.stdout.write(`encoding   : ${exported.version}\n`);
process.stdout.write(`preimage   : ${bytes.length} byte\n`);
process.stdout.write(`memory_root: 0x${keccak256(bytes).toString("hex")}\n`);
