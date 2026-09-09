import "./globals.css";
import Link from "next/link";
import { CHAIN_ID, CHAIN_NAME } from "../lib/chain.js";
import { display, sans, mono } from "../fonts/fonts.js";

export const metadata = {
  title: "The Evaluator — verdict evidence",
  description:
    "Job timeline, per-criterion evidence, and a judge panel for an ERC-8183 escrow referee with auditable provider memory.",
};

/** @param {{ children: unknown }} props */
export default function RootLayout({ children }) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable}`}
    >
      <body>
        <a className="skip" href="#content">
          Skip to content
        </a>
        <header className="top">
          <div className="wrap">
            <h1>The Evaluator</h1>
            <nav aria-label="Main">
              <Link href="/">Timeline</Link>
              <Link href="/panel">Judge panel</Link>
            </nav>
            <span className="net">
              {CHAIN_NAME} · {CHAIN_ID} · static artifacts, no RPC
            </span>
          </div>
        </header>
        <main className="wrap" id="content">
          {children}
        </main>
      </body>
    </html>
  );
}
