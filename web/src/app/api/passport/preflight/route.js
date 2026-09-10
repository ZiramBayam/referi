import { evaluateDemoAction } from "../../../../lib/passportDemo.js";

const MAX_AMOUNT = 1_000_000;

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

  return Response.json(
    evaluateDemoAction({
      amount,
      memoryAvailable: body?.memoryAvailable !== false,
      oracleFresh: body?.oracleFresh === true,
    }),
  );
}
