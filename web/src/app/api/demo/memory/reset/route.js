// Proksi same-origin ke endpoint hapus memori milik `agent/`.
//
// KENAPA PROKSI, bukan fetch langsung dari browser ke :8010 — diukur, bukan diduga:
//   $ curl -i -X OPTIONS http://127.0.0.1:8010/demo/memory/reset \
//       -H 'Origin: http://localhost:3000' -H 'Access-Control-Request-Method: POST'
//     HTTP/1.0 501 Unsupported method ('OPTIONS')
//   $ curl -i -X POST … -H 'Origin: http://localhost:3000'   → 200, TANPA satu pun
//     header Access-Control-Allow-*.
// `Content-Type: application/json` memicu preflight, dan preflight itu dijawab 501;
// tanpa `Access-Control-Allow-Origin` browser juga tidak boleh MEMBACA badan respons.
// Jadi tombol di /panel memanggil rute ini (same-origin), dan Node yang meneruskannya.
// Memperbaiki CORS di sisi agen bukan pilihan: `agent/` di luar batas folder ini, dan
// kontrak HTTP-nya sudah mendarat.
//
// Rute ini TIDAK menghapus apa pun sendiri. Ia tidak menyentuh disk, tidak menyentuh
// chain, dan tidak menyimpan apa pun.

// Gerbang DEMO_MODE harus dibaca PER PERMINTAAN, bukan saat build (sama seperti
// `panel/page.jsx`). Tanpa ini nilainya beku pada `next build`.
export const dynamic = "force-dynamic";

const DEFAULT_BASE = "http://127.0.0.1:8010";
const RESET_PATH = "/demo/memory/reset";
const TIMEOUT_MS = 10_000;

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

export async function POST() {
  // DEMO_MODE mati → 404, kode alasan yang sama dengan sisi agen. Bukan 403: 403
  // mengakui rutenya ada.
  if (process.env.DEMO_MODE !== "1") {
    return Response.json({ ok: false, reason: "not_found" }, { status: 404 });
  }

  const url = resetUrl();
  if (url === null) {
    return Response.json(
      {
        ok: false,
        reason: "reset_url_not_loopback",
        detail:
          "NEXT_PUBLIC_AGENT_RESET_API harus menunjuk ke loopback (mis. " +
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
      headers: { "content-type": "application/json" },
      body: "{}",
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
