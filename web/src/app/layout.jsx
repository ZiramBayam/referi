import "./globals.css";
import Link from "next/link";
import { CHAIN_ID, CHAIN_NAME } from "../lib/chain.js";
import { loadDeployment } from "../lib/data.js";
import { AddressLink } from "../components/Links.jsx";
import Icon from "../components/Icon.jsx";
import Reveal from "../components/Reveal.jsx";
import { display, sans, mono } from "../fonts/fonts.js";

const REPO_URL = "https://github.com/ZiramBayam/referi";

export const metadata = {
  title: "REFERI — verdict evidence",
  description:
    "Job timeline, per-criterion evidence, and a judge panel for an ERC-8183 escrow referee with auditable provider memory.",
};

/** @param {{ children: unknown }} props */
export default async function RootLayout({ children }) {
  // Alamat vault dibaca dari artefak deploy, bukan ditulis ulang sebagai konstanta:
  // satu sumber, dan footer tidak bisa diam-diam menunjuk kontrak yang salah.
  const deployment = await loadDeployment();
  const vault = deployment?.EvaluatorVault;

  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable}`}
    >
      <body>
        <Reveal />
        <a className="skip" href="#content">
          Skip to content
        </a>
        <header className="top">
          <div className="wrap">
            <h1>REFERI</h1>
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

        <footer className="site">
          <div className="wrap">
            <div className="cols">
              <div>
                <span className="k">Evaluator vault</span>
                {vault ? (
                  <AddressLink address={vault} label={vault} />
                ) : (
                  <span className="none">not available</span>
                )}
              </div>
              <div>
                <span className="k">Network</span>
                <span className="mono">
                  {CHAIN_NAME} · chainId {CHAIN_ID}
                </span>
              </div>
              <div>
                <span className="k">Source</span>
                <a href={REPO_URL} target="_blank" rel="noreferrer">
                  ZiramBayam/referi
                  <Icon name="external-link" size={12} />
                </a>
              </div>
            </div>
            <p className="disclaimer">
              Hackathon project on Base Sepolia — testnet only, never run on mainnet. What does
              not work is written down rather than hidden: the repository ships a list of 36
              limitations and trust assumptions in <code>docs/limitations.md</code>.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
