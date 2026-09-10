import { evaluateDemoAction } from "../../../../lib/passportDemo.js";
import { runAgentPreflight } from "../../../../lib/agentPreflight.js";

const MAX_AMOUNT = 1_000_000;

/**
 * Preflight selalu MENCOBA agen sungguhan lebih dulu.
 *
 * `REFERI_AGENT=off` memaksa fixture, untuk penempatan di mana Python tidak ada sama
 * sekali (misalnya hosting statis). Selain itu ia mencoba agen, dan bila agennya tidak
 * bisa dijalankan ia jatuh ke fixture SAMBIL MENGATAKANNYA lewat `engine` dan
 * `engineReason`. Situs menampilkan keduanya.
 *
 * Fallback yang diam adalah masalah yang justru dihapus perubahan ini: sebelumnya
 * halaman ini SELALU menjalankan implementasi ulang dalam JavaScript, dan tidak ada
 * cara membedakannya dari mesin yang sesungguhnya.
 */
export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "request body is not JSON" }, { status: 400 });
  }

  const amount = body?.amount;
  if (!Number.isInteger(amount) || amount < 0 || amount > MAX_AMOUNT) {
    return Response.json(
      { error: `amount must be an integer between 0 and ${MAX_AMOUNT}` },
      { status: 400 },
    );
  }

  const input = {
    amount,
    memoryAvailable: body?.memoryAvailable !== false,
    oracleFresh: body?.oracleFresh === true,
  };

  if (process.env.REFERI_AGENT === "off") {
    return Response.json({
      ...evaluateDemoAction(input),
      engine: "fixture",
      engineReason: "REFERI_AGENT=off",
    });
  }

  try {
    return Response.json(await runAgentPreflight(input));
  } catch (error) {
    return Response.json({
      ...evaluateDemoAction(input),
      engine: "fixture",
      engineReason: error instanceof Error ? error.message : "agent unavailable",
    });
  }
}
