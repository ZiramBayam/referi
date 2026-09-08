import "./globals.css";
import Link from "next/link";
import { CHAIN_ID, CHAIN_NAME } from "../lib/chain.js";

export const metadata = {
  title: "The Evaluator — bukti verdict",
  description:
    "Timeline job, bukti per-kriteria, dan panel juri untuk wasit escrow ERC-8183 dengan memori provider yang bisa diaudit.",
};

/** @param {{ children: unknown }} props */
export default function RootLayout({ children }) {
  return (
    <html lang="id">
      <body>
        <header className="top">
          <div className="wrap">
            <h1>The Evaluator</h1>
            <nav>
              <Link href="/">Timeline job</Link>
              <Link href="/panel">Panel juri</Link>
            </nav>
            <span className="net">
              {CHAIN_NAME} (chainId {CHAIN_ID}) — data dari artefak statis, tanpa RPC di browser
            </span>
          </div>
        </header>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
