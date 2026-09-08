import Link from "next/link";
import { loadIndex } from "../lib/data.js";
import { formatUsdc6 } from "../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel, EXPLORER_NAME } from "../lib/chain.js";
import { TxLink, AddressLink, shorten } from "../components/Links.jsx";

export default async function TimelinePage() {
  const index = await loadIndex();
  const jobs = index.jobs;

  return (
    <div>
      <h2>Timeline job 418–422 (Base Sepolia)</h2>
      <p className="lead">
        Lima job yang benar-benar mendarat di chain, urut menurut jobId. Kolom
        &quot;verdict&quot; adalah <code>kind</code> yang diumumkan{" "}
        <code>EvaluatorVault.postVerdict</code>; kolom &quot;status ACP&quot; adalah enum status
        job di ERC-8183. Setiap verdict punya tautan ke transaksi <code>VerdictPosted</code>-nya
        di {EXPLORER_NAME} — explorer itu yang dipakai karena hanya di sana verifikasi Sourcify
        kontrak vault terbaca, sehingga nama event tampil terdekode alih-alih sebagai topic
        mentah.
      </p>

      <table>
        <thead>
          <tr>
            <th>Job</th>
            <th>Provider</th>
            <th>Budget</th>
            <th>Status ACP</th>
            <th>Verdict</th>
            <th>Bentuk bundel</th>
            <th>tx VerdictPosted</th>
            <th>Bukti</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((/** @type {any} */ job) => (
            <tr key={job.jobId}>
              <td className="mono">
                <strong>{job.jobId}</strong>
              </td>
              <td>
                <AddressLink address={job.provider} label={shorten(job.provider)} />
                <div style={{ color: "var(--muted)", fontSize: 12 }}>{job.providerLabel}</div>
              </td>
              <td className="mono">
                {formatUsdc6(job.budgetUsdc6) ?? <span className="none">belum ada</span>}
              </td>
              <td>{acpStatusLabel(job.acpStatus)}</td>
              <td>
                <span className={"tag " + (job.verdictKind === 1 ? "pass" : "fail")}>
                  {verdictKindLabel(job.verdictKind)}
                </span>
              </td>
              <td className="mono">
                {job.bundleKind}
                <div style={{ color: "var(--muted)" }}>depth {job.depth || "—"}</div>
              </td>
              <td>
                <TxLink hash={job.verdictTxHash} label={shorten(job.verdictTxHash)} />
              </td>
              <td>
                <Link href={"/verdict/" + job.jobId}>buka bukti</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Apa yang terjadi, urutannya</h2>
      <ul className="lead">
        {jobs.map((/** @type {any} */ job) => (
          <li key={job.jobId}>
            <strong className="mono">job {job.jobId}</strong> — {job.note}
          </li>
        ))}
      </ul>

      <div className="card note">
        <h3 style={{ marginTop: 0 }}>Dari mana angka di halaman ini</h3>
        <dl className="kv">
          {Object.entries(index.source).map(([key, value]) => (
            <div key={key} style={{ display: "contents" }}>
              <dt className="mono">{key}</dt>
              <dd>{String(value)}</dd>
            </div>
          ))}
        </dl>
        <p className="lead" style={{ marginBottom: 0 }}>
          Halaman ini tidak memanggil RPC, tidak menyambung wallet, dan tidak menghitung hash
          apa pun. Ia hanya menampilkan artefak yang sudah ada di repo.
        </p>
      </div>
    </div>
  );
}
