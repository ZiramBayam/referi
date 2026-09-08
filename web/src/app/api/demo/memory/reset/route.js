// Proksi same-origin ke endpoint hapus memori milik `agent/`.
//
// KENAPA PROKSI, bukan fetch langsung dari browser ke :8010 — diukur, bukan diduga:
//   $ curl -i -X OPTIONS http://127.0.0.1:8010/demo/memory/reset \
//       -H 'Origin: http://localhost:3000' -H 'Access-Control-Request-Method: POST'
//     HTTP/1.0 501 Unsupported method ('OPTIONS')
//   $ curl -i -X POST … -H 'Origin: http://localhost:3000'   → 200, TANPA satu pun
//     header Access-Control-Allow-*.
// `Content-Type: application/json` memicu preflight, preflight itu dijawab 501, dan
// tanpa `Access-Control-Allow-Origin` browser tidak boleh MEMBACA badan responsnya.
//
// KOREKSI atas versi sebelumnya komentar ini: "browser tidak bisa membaca respons"
// BUKAN berarti "browser tidak bisa MEMICU aksinya". `text/plain` termasuk
// CORS-safelisted request header, jadi halaman jahat mana pun bisa mengirim
//   fetch('http://127.0.0.1:8010/demo/memory/reset', {method:'POST', mode:'no-cors',
//         headers:{'content-type':'text/plain'}, body:'{}'})
// TANPA preflight; permintaannya tetap sampai dan penghapusan tetap terjadi, hanya
// responsnya yang buram bagi penyerang. Menghapus adalah efek samping, bukan bacaan —
// jadi CORS tidak pernah menjadi pertahanan di sini. Yang benar-benar menahan adalah
// (a) sisi agen menolak peer non-loopback dan (b) cek same-origin di bawah.
//
// Proses Next ini sendiri HARUS terikat loopback (`next dev|start -H 127.0.0.1` di
// package.json). Default Next adalah 0.0.0.0; tanpa `-H` rute ini menjadi relay LAN
// yang membatalkan jaminan loopback sisi agen. Cek `Origin`/`Sec-Fetch-Site` di bawah
// adalah lapisan kedua supaya keselamatan rute tidak bergantung pada pengikatan saja.
//
// Rute ini TIDAK menghapus apa pun sendiri. Ia tidak menyentuh disk, tidak menyentuh
// chain, dan tidak menyimpan apa pun.

import { demoModeEnabled } from "../../../../../lib/demoMode.js";

// Gerbang DEMO_MODE harus dibaca PER PERMINTAAN, bukan saat build (sama seperti
// `panel/page.jsx`). Tanpa ini nilainya beku pada `next build`.
export const dynamic = "force-dynamic";

const DEFAULT_BASE = "http://127.0.0.1:8010";
const RESET_PATH = "/demo/memory/reset";
const TIMEOUT_MS = 10_000;

// Header yang dikirim KE sisi agen. Dikumpulkan di satu tempat karena sisi 8010 boleh
// memperketat syaratnya (mis. mewajibkan `content-type` persis, atau token) — proksi
// ini pemanggil sisi-server, jadi ia bebas mengirim apa pun yang diwajibkan dan hanya
// konstanta ini yang perlu berubah.
const UPSTREAM_HEADERS = { "content-type": "application/json" };
const UPSTREAM_BODY = "{}";

// Loopback saja, dicocokkan seperti `LOOPBACK_HOSTS` di sisi agen. Env salah ketik tidak
// boleh mengubah proses Next ini menjadi relay yang mengirim "hapus berkas" ke mesin lain.
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

/** URL endpoint agen, atau `null` bila env-nya menunjuk ke luar loopback / tidak sah. */
function resetUrl() {
  const raw = (process.env.NEXT_PUBLIC_AGENT_RESET_API || DEFAULT_BASE).trim();
  let url;
  try {
    url = new URL(RESET_PATH, raw.endsWith("/") ? raw : raw + "/");
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  if (!LOOPBACK_HOSTS.has(url.hostname)) return null;
  return url.toString();
}

/**
 * `null` bila permintaan ini sah datang dari halaman kita sendiri, atau kode alasan
 * bila TIDAK.
 *
 * Satu-satunya pemanggil sah adalah `fetch("/api/demo/memory/reset", {method:"POST"})`
 * di `panel/MemoryControl.jsx`. Untuk POST, semua browser arus utama mengirim `Origin`,
 * dan sejak Fetch Metadata juga `Sec-Fetch-Site`. Jadi keduanya DIWAJIBKAN: permintaan
 * lintas situs (`cross-site`/`same-site`), permintaan tanpa metadata (curl, skrip), dan
 * navigasi form dari dokumen lain semuanya jatuh ke sini.
 */
function crossSiteReason(request) {
  const site = request.headers.get("sec-fetch-site");
  if (site === null) return "missing_fetch_metadata";
  if (site !== "same-origin") return "cross_site_request";

  // `Sec-Fetch-Site` bisa dipalsukan oleh klien non-browser; `Origin` vs `Host` adalah
  // cek kedua yang murah. Keduanya harus menunjuk otoritas yang sama.
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (origin === null || host === null) return "missing_origin";
  let originHost;
  try {
    originHost = new URL(origin).host;
  } catch {
    return "bad_origin";
  }
  if (originHost !== host) return "origin_host_mismatch";
  return null;
}

export async function POST(request) {
  // DEMO_MODE mati → 404, kode alasan yang sama dengan sisi agen. Bukan 403: 403
  // mengakui rutenya ada.
  if (!demoModeEnabled()) {
    return Response.json({ ok: false, reason: "not_found" }, { status: 404 });
  }

  const bad = crossSiteReason(request);
  if (bad !== null) {
    return Response.json(
      {
        ok: false,
        reason: bad,
        detail:
          "Only the panel served from this origin may call this route; " +
          "the request must carry Sec-Fetch-Site: same-origin and an Origin matching Host.",
      },
      { status: 403 },
    );
  }

  const url = resetUrl();
  if (url === null) {
    return Response.json(
      {
        ok: false,
        reason: "reset_url_not_loopback",
        detail:
          "NEXT_PUBLIC_AGENT_RESET_API must point at loopback (e.g. " +
          DEFAULT_BASE +
          ")",
      },
      { status: 400 },
    );
  }

  // Badan permintaan klien SENGAJA diabaikan: panel hanya pernah mereset basis data
  // demo bawaan, dan membiarkan browser memilih field `db` berarti menyerahkan pilihan
  // nama berkas ke sisi yang paling tidak tepercaya. Badan kosong = default `memory.db`
  // di sisi agen.
  let upstream;
  try {
    upstream = await fetch(url, {
      method: "POST",
      headers: UPSTREAM_HEADERS,
      body: UPSTREAM_BODY,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (e) {
    return Response.json(
      {
        ok: false,
        reason: "reset_server_unreachable",
        url,
        detail: String(e),
      },
      { status: 503 },
    );
  }

  const raw = await upstream.text();
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    // Jawaban bukan JSON = kemungkinan besar bukan server yang kita kira. Jangan
    // tafsirkan; laporkan apa adanya, dipotong supaya tidak membanjiri layar.
    return Response.json(
      { ok: false, reason: "reset_server_bad_response", url, detail: raw.slice(0, 300) },
      { status: 502 },
    );
  }

  // Status DAN badan diteruskan APA ADANYA. UI menampilkan yang dikatakan agen, bukan
  // tafsiran rute ini.
  return Response.json(body, { status: upstream.status });
}
