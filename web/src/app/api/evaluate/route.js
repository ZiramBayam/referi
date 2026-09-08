// Endpoint evaluasi LOKAL untuk panel juri.
//
// Yang dijalankan: cek DETERMINISTIK `format` + `links` kategori `general`, port dari
// `agent/agent/checks/`. Yang TIDAK dijalankan, dan tidak boleh diklaim jalan di sini:
// gerbang cap, memori Sibyl, gerbang 402, dan transaksi apa pun. Endpoint ini tidak
// menyentuh chain, tidak menyentuh basis data memori, dan tidak menulis apa pun ke disk.

import { evaluateText, DEPTH_FULL, DEPTH_SAMPLING } from "../../../lib/checks.js";

// Batas ukuran teks yang diterima. Sekadar penjaga sumber daya di mesin juri, bukan
// aturan protokol.
const MAX_TEXT_BYTES = 200_000;

export async function POST(request) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "body bukan JSON" }, { status: 400 });
  }

  const text = payload?.text;
  const depth = payload?.depth;

  if (typeof text !== "string") {
    return Response.json({ error: "field `text` wajib berupa string" }, { status: 400 });
  }
  if (text.length > MAX_TEXT_BYTES) {
    return Response.json(
      { error: `teks melebihi batas panel (${MAX_TEXT_BYTES} karakter)` },
      { status: 413 },
    );
  }
  if (depth !== DEPTH_FULL && depth !== DEPTH_SAMPLING) {
    return Response.json(
      { error: "field `depth` hanya boleh 'sampling' atau 'full'" },
      { status: 400 },
    );
  }

  const evaluation = evaluateText(text, depth);
  return Response.json({
    evaluation,
    scope: {
      ran: ["format", "links"],
      not_ran: ["gerbang cap provider", "memori Sibyl", "gerbang 402", "transaksi on-chain"],
    },
  });
}
