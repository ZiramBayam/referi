// Port JavaScript dari cek DETERMINISTIK agen: `agent/agent/checks/base.py`,
// `format.py`, `links.py`, kategori rubric `general` dari `agent/agent/criteria.py`.
//
// KENAPA ada di sini: panel juri harus bisa menilai teks yang JURI tempel sendiri, di
// mesin juri, tanpa Python. Yang diport HANYA cek deterministik — tidak ada rubric LLM
// (memang dipotong di agen juga), tidak ada gerbang cap, tidak ada memori, tidak ada 402,
// tidak ada transaksi.
//
// BATAS YANG WAJIB DIBACA: port ini BUKAN pengganti agen. Verdict yang MENGIKAT tetap
// yang diumumkan on-chain oleh `EvaluatorVault`; panel hanya menunjukkan bahwa cek yang
// sama menghasilkan temuan yang sama atas teks yang sama. Yang membuktikan kesetaraannya
// adalah artefak: teks `demo/deliverables/422.json` pada `depth=full` harus menghasilkan
// `failed_checks: ["format"]`, persis bundel 422 yang sudah mendarat di chain.

export const CHECK_FORMAT = "format";
export const CHECK_LINKS = "links";

export const STATUS_PASS = "pass";
export const STATUS_FAIL = "fail";
export const STATUS_UNVERIFIED = "unverified";

export const DEPTH_SAMPLING = "sampling";
export const DEPTH_FULL = "full";

// base.py: berapa bagian PERTAMA yang isinya dibaca saat `sampling`.
export const SAMPLING_SECTION_LIMIT = 2;
// base.py: MAX_EXCERPT_LEN
const MAX_EXCERPT_LEN = 160;

// criteria.py CATALOG[general]
export const REQUIRED_SECTIONS = ["summary"];
export const LINK_SECTIONS = [];

const HEADING_RE = /^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*$/;

// format.py `_PLACEHOLDER_RE`
const PLACEHOLDER_RE =
  /(?:\b(?:todo|tbd|fixme|wip|lorem ipsum|coming soon|placeholder|to be filled)\b|<[a-z][a-z0-9 _-]{2,30}>)/i;

// links.py `_URL_RE`
const URL_RE = /\b([a-z][a-z0-9+.-]{1,15}):(\/\/)?([^\s<>"'\)\]\}]+)/gi;

// links.py `_PRIVATE_HOST_RE`
const PRIVATE_HOST_RE =
  /^(?:localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+|0\.0\.0\.0|\[?::1\]?|.*\.local|.*\.internal|.*\.localdomain)$/i;

export const ALLOWED_SCHEMES = ["https", "ipfs"];

/**
 * Padanan `str.isprintable() == False` di Python: kategori kontrol/format (Cc, Cf, Cs,
 * Co, Cn) dan seluruh pemisah (Zs/Zl/Zp) KECUALI spasi biasa U+0020.
 * @param {string} ch
 */
function isNonPrintable(ch) {
  if (ch === " ") return false;
  return /[\p{C}\p{Z}]/u.test(ch);
}

/** @param {string} text */
function stripNonPrintable(text) {
  let out = "";
  for (const ch of text) out += isNonPrintable(ch) ? " " : ch;
  return out;
}

/**
 * base.py `excerpt` — satu-satunya pintu bagi teks pihak menuju tampilan/memori.
 * @param {string} text
 * @param {number} limit
 */
export function excerpt(text, limit = MAX_EXCERPT_LEN) {
  let cleaned = stripNonPrintable(text).split(/\s+/).filter(Boolean).join(" ");
  if (cleaned.length > limit) {
    cleaned = cleaned.slice(0, limit - 1).replace(/\s+$/, "") + "…";
  }
  return cleaned;
}

/**
 * base.py `normalize_heading`
 * @param {string} heading
 */
export function normalizeHeading(heading) {
  const cleaned = stripNonPrintable(heading)
    .split(/\s+/)
    .filter(Boolean)
    .join(" ")
    .trim()
    .toLowerCase();
  return cleaned
    .replace(/^[#*_`:.,;!?\-–— ]+/, "")
    .replace(/[#*_`:.,;!?\-–— ]+$/, "");
}

/**
 * base.py `parse_document`. Bagian index 0 = pembuka bila ada teks sebelum judul pertama.
 * @param {string} text
 */
export function parseDocument(text) {
  /** @type {{ index: number, heading: string, body: string, line: number }[]} */
  const sections = [];
  let heading = "";
  let startLine = 1;
  /** @type {string[]} */
  let buffer = [];
  const lines = text.split(/\r\n|\r|\n/);
  // `splitlines()` Python tidak menghasilkan baris kosong ekstra sesudah newline penutup.
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  lines.forEach((line, i) => {
    const match = HEADING_RE.exec(line);
    if (match === null) {
      buffer.push(line);
      return;
    }
    if (heading || buffer.join("").trim()) {
      sections.push({ index: sections.length, heading, body: buffer.join("\n"), line: startLine });
    }
    heading = match[2];
    startLine = i + 1;
    buffer = [];
  });
  if (heading || buffer.join("").trim() || sections.length === 0) {
    sections.push({ index: sections.length, heading, body: buffer.join("\n"), line: startLine });
  }
  return { text, sections };
}

/** @param {{ heading: string, body: string }} section */
export function sectionText(section) {
  return section.heading ? section.heading + "\n" + section.body : section.body;
}

/** @param {{ heading: string }} section */
export function sectionSlug(section) {
  return normalizeHeading(section.heading);
}

/**
 * base.py `sections_in_scope` — kedalaman yang tidak dikenal MELEMPAR, tidak jatuh
 * diam-diam ke yang lebih longgar.
 * @param {{ sections: { index: number, heading: string, body: string, line: number }[] }} document
 * @param {string} depth
 */
export function sectionsInScope(document, depth) {
  if (depth === DEPTH_FULL) return document.sections;
  if (depth === DEPTH_SAMPLING) return document.sections.slice(0, SAMPLING_SECTION_LIMIT);
  throw new Error("kedalaman cek tidak dikenal: " + JSON.stringify(depth));
}

/**
 * format.py `_around`
 * @param {string} text
 * @param {number} position
 * @param {number} width
 */
function around(text, position, width = 60) {
  const start = Math.max(0, position - Math.floor(width / 2));
  return text.slice(start, start + width);
}

/**
 * Cetakan daftar gaya Python (`['a', 'b']`), supaya `detail` cocok dengan bundel agen.
 * @param {string[]} items
 */
function pyList(items) {
  return "[" + items.map((i) => "'" + i + "'").join(", ") + "]";
}

/**
 * format.py `check_required_sections`.
 * @param {{ sections: { heading: string }[] }} document
 * @param {string[]} required
 * @param {string} criterionId
 * @param {string} depth
 */
export function checkRequiredSections(document, required, criterionId, depth) {
  const present = document.sections
    .filter((s) => s.heading)
    .map((s) => normalizeHeading(s.heading));
  const missing = required
    .map((r) => normalizeHeading(String(r)))
    .filter((want) => !present.some((h) => h.startsWith(want)));
  if (missing.length > 0) {
    return {
      check: CHECK_FORMAT,
      criterion: criterionId,
      status: STATUS_FAIL,
      detail: "bagian wajib hilang: " + pyList(missing) + "; judul yang ada: " + pyList(present),
      proof: excerpt(present.length ? "judul yang ada: " + present.join(", ") : "tanpa judul"),
      pattern: "format.missing-section",
      section: -1,
      depth,
    };
  }
  return {
    check: CHECK_FORMAT,
    criterion: criterionId,
    status: STATUS_PASS,
    detail: "seluruh " + required.length + " bagian wajib hadir",
    proof: "",
    pattern: "",
    section: -1,
    depth,
  };
}

/**
 * format.py `check_placeholders`.
 * @param {{ index: number, heading: string, body: string }[]} scope
 * @param {string} criterionId
 * @param {string} depth
 */
export function checkPlaceholders(scope, criterionId, depth) {
  for (const section of scope) {
    const text = sectionText(section);
    const match = PLACEHOLDER_RE.exec(text);
    if (match === null) continue;
    return {
      check: CHECK_FORMAT,
      criterion: criterionId,
      status: STATUS_FAIL,
      detail:
        "penanda pekerjaan '" +
        match[0] +
        "' pada bagian " +
        section.index +
        " (" +
        (sectionSlug(section) || "pembuka") +
        ")",
      proof: excerpt(around(text, match.index)),
      pattern: "format.placeholder-text",
      section: section.index,
      depth,
    };
  }
  return {
    check: CHECK_FORMAT,
    criterion: criterionId,
    status: STATUS_PASS,
    detail: "tanpa penanda pekerjaan pada " + scope.length + " bagian yang dibaca",
    proof: "",
    pattern: "",
    section: -1,
    depth,
  };
}

/**
 * links.py `_authority_of`
 * @param {string} rest
 */
function authorityOf(rest) {
  return rest.split("/")[0].split("?")[0].split("#")[0];
}

/**
 * links.py `_host_of` — port buang userinfo + port numerik, IPv6 literal ditangani sendiri.
 * @param {string} authority
 */
function hostOf(authority) {
  const parts = authority.split("@");
  const host = parts[parts.length - 1];
  if (host.startsWith("[")) {
    const end = host.indexOf("]");
    return end !== -1 ? host.slice(0, end + 1) : host;
  }
  const idx = host.lastIndexOf(":");
  if (idx === -1) return host;
  const tail = host.slice(idx + 1);
  return tail.length > 0 && /^[0-9]+$/.test(tail) ? host.slice(0, idx) : host;
}

/**
 * links.py `_unsafe_reason`
 * @param {string} scheme
 * @param {string} slashes
 * @param {string} rest
 * @returns {string | null}
 */
function unsafeReason(scheme, slashes, rest) {
  const s = scheme.toLowerCase();
  if (!ALLOWED_SCHEMES.includes(s)) {
    return "skema '" + s + "' di luar " + pyList([...ALLOWED_SCHEMES].sort());
  }
  if (!slashes) return "skema '" + s + "' tanpa //";
  const authority = authorityOf(rest);
  if (!authority) return "host kosong";
  if (authority.includes("@")) return "memuat userinfo user:pass@host";
  const host = hostOf(authority);
  if (!host) return "host kosong";
  for (const ch of host) {
    const code = ch.codePointAt(0);
    if (code !== undefined && code > 127) return "host memuat karakter non-ASCII (homograf)";
  }
  if (s === "https" && PRIVATE_HOST_RE.test(host)) {
    return "host '" + host + "' menunjuk jaringan internal/loopback";
  }
  if (s === "ipfs" && !/^[A-Za-z0-9]{16,}$/.test(host)) {
    return "CID ipfs '" + host + "' tidak berbentuk";
  }
  return null;
}

/**
 * links.py `check_links`. `probe` TIDAK PERNAH disuntikkan di sini: browser demo tidak
 * boleh disuruh mengetuk alamat pilihan pihak lain (SSRF), sama seperti default agen.
 * @param {{ index: number, heading: string, body: string }[]} scope
 * @param {string} criterionId
 * @param {string} depth
 * @param {string[]} requiredLinkSections
 */
export function checkLinks(scope, criterionId, depth, requiredLinkSections = []) {
  const required = requiredLinkSections.map((s) => String(s).toLowerCase());
  /** @type {string[]} */
  const seen = [];
  /** @type {Set<string>} */
  const sectionsWithLinks = new Set();

  for (const section of scope) {
    const text = sectionText(section);
    URL_RE.lastIndex = 0;
    let match = URL_RE.exec(text);
    while (match !== null) {
      const scheme = match[1];
      const slashes = match[2] || "";
      const rest = match[3];
      seen.push(scheme + ":" + slashes + rest);
      sectionsWithLinks.add(sectionSlug(section));
      const reason = unsafeReason(scheme, slashes, rest);
      if (reason !== null) {
        return {
          check: CHECK_LINKS,
          criterion: criterionId,
          status: STATUS_FAIL,
          detail: "tautan ditolak pada bagian " + section.index + ": " + reason,
          proof: excerpt(scheme + ":" + slashes + rest + " | " + reason),
          pattern: "links.unsafe-url",
          section: section.index,
          depth,
        };
      }
      match = URL_RE.exec(text);
    }
  }

  const missing = required
    .filter(
      (want) =>
        scope.some((s) => sectionSlug(s).startsWith(want)) &&
        ![...sectionsWithLinks].some((s) => s.startsWith(want)),
    )
    .sort();
  if (missing.length > 0) {
    return {
      check: CHECK_LINKS,
      criterion: criterionId,
      status: STATUS_FAIL,
      detail: "bagian sumber " + pyList(missing) + " tidak memuat satu pun tautan",
      proof: excerpt("bagian tanpa tautan: " + missing.join(", ")),
      pattern: "links.missing-source",
      section: -1,
      depth,
    };
  }

  if (seen.length === 0) {
    return {
      check: CHECK_LINKS,
      criterion: criterionId,
      status: STATUS_UNVERIFIED,
      detail: "tidak ada tautan pada " + scope.length + " bagian yang dibaca (depth=" + depth + ")",
      proof: "",
      pattern: "",
      section: -1,
      depth,
    };
  }
  return {
    check: CHECK_LINKS,
    criterion: criterionId,
    status: STATUS_PASS,
    detail: seen.length + " tautan lolos struktur saja (tanpa probe)",
    proof: "",
    pattern: "",
    section: -1,
    depth,
  };
}

export const CRITERIA_GENERAL = [
  {
    id: "format.required-sections",
    kind: "deterministic",
    check: CHECK_FORMAT,
    text: "deliverable memuat seluruh bagian wajib: " + pyList(REQUIRED_SECTIONS),
  },
  {
    id: "format.no-placeholder",
    kind: "deterministic",
    check: CHECK_FORMAT,
    text: "tidak ada penanda pekerjaan yang belum selesai (TODO/TBD/placeholder)",
  },
  {
    id: "links.safe-sources",
    kind: "deterministic",
    check: CHECK_LINKS,
    text:
      "tautan memakai skema yang diizinkan, bukan alamat internal, dan bagian sumber " +
      pyList(LINK_SECTIONS) +
      " benar-benar memuat tautan",
  },
];

/**
 * Jalankan seluruh cek deterministik kategori `general` atas satu teks deliverable.
 * Bentuk hasilnya sengaja sama dengan blok `evaluation` di bundel bukti.
 * @param {string} text
 * @param {string} depth
 */
export function evaluateText(text, depth) {
  const document = parseDocument(text);
  const scope = sectionsInScope(document, depth);
  const checks = [
    checkRequiredSections(document, REQUIRED_SECTIONS, "format.required-sections", depth),
    checkPlaceholders(scope, "format.no-placeholder", depth),
    checkLinks(scope, "links.safe-sources", depth, LINK_SECTIONS),
  ];
  const failed = [
    ...new Set(checks.filter((c) => c.status === STATUS_FAIL).map((c) => c.check)),
  ].sort();
  const unverified = checks
    .filter((c) => c.status === STATUS_UNVERIFIED)
    .map((c) => c.criterion);
  return {
    category: "general",
    depth,
    sections: document.sections.length,
    sections_read: scope.length,
    checks,
    criteria: CRITERIA_GENERAL,
    failed_checks: failed,
    unverified,
    verdict: failed.length > 0 ? 2 : 1,
  };
}
