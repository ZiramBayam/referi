import Link from "next/link";
import { notFound } from "next/navigation";
import { loadJobs, loadJob, loadBundle, loadDeliverable } from "../../../lib/data.js";
import { readSmallInt, readUint, readSectionIndex, formatUsdc6 } from "../../../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel } from "../../../lib/chain.js";
import { TxLink, AddressLink, Hash, shorten } from "../../../components/Links.jsx";
import Checks from "../../../components/Checks.jsx";

export async function generateStaticParams() {
  const jobs = await loadJobs();
  return jobs.map((/** @type {{ jobId: string }} */ j) => ({ jobId: j.jobId }));
}

/** @param {{ params: Promise<{ jobId: string }> }} props */
export default async function VerdictPage({ params }) {
  const { jobId } = await params;
  const job = await loadJob(jobId);
  const bundle = await loadBundle(jobId);
  if (!job || !bundle) notFound();

  const deliverable = await loadDeliverable(jobId);
  const evaluation = bundle.evaluation ?? null;
  const gate = bundle.gate ?? null;

  const checks = (evaluation?.checks ?? []).map((/** @type {any} */ c) => ({
    check: c.check,
    criterion: c.criterion,
    status: c.status,
    detail: c.detail,
    proof: c.proof,
    pattern: c.pattern,
    section: readSectionIndex(c.section),
    depth: c.depth,
  }));

  return (
    <div>
      <p className="lead">
        <Link href="/">← timeline job</Link>
      </p>
      <h2>
        Verdict job <span className="mono">{jobId}</span> —{" "}
        {verdictKindLabel(readSmallInt(bundle.verdict))}
      </h2>
      <p className="lead">
        Kenapa diputus begitu, dan apa buktinya. Seluruh isi halaman ini adalah bundel bukti
        yang di-keccak menjadi <code>reasonHash</code> di transaksi{" "}
        <code>VerdictPosted</code> — bukan ringkasan yang ditulis ulang.
      </p>

      <div className="card">
        <dl className="kv">
          <dt>versi bundel</dt>
          <dd className="mono">{bundle.version}</dd>
          <dt>bentuk bundel</dt>
          <dd className="mono">{bundle.kind}</dd>
          <dt>mode memori</dt>
          <dd className="mono">{bundle.mode}</dd>
          <dt>memory_root (dari agen)</dt>
          <dd>
            <Hash value={bundle.memory_root} />
          </dd>
          <dt>kedalaman cek</dt>
          <dd className="mono">{evaluation?.depth ?? gate?.depth ?? "—"}</dd>
          <dt>provider</dt>
          <dd>
            <AddressLink address={job.provider} /> ({job.providerLabel})
          </dd>
          <dt>budget</dt>
          <dd className="mono">
            {formatUsdc6(job.budgetUsdc6) ?? <span className="none">belum ada</span>} unit token
            escrow (6 desimal)
          </dd>
          <dt>status ACP terakhir</dt>
          <dd>{acpStatusLabel(job.acpStatus)}</dd>
          <dt>hash deliverable</dt>
          <dd>
            <Hash value={evaluation?.deliverable} />
          </dd>
          <dt>tx VerdictPosted</dt>
          <dd>
            <TxLink hash={job.verdictTxHash} />
          </dd>
          <dt>tx finalize</dt>
          <dd>
            <TxLink hash={job.finalizeTxHash} />
          </dd>
          <dt>berkas bundel</dt>
          <dd className="mono">
            agent/data/chain-abc/verdicts/{job.bundleFile}
            <div style={{ color: "var(--muted)" }}>
              nama berkas = keccak256 atas isi berkas; salinannya disajikan apa adanya di{" "}
              <a href={"/verdicts/" + jobId + ".json"}>/verdicts/{jobId}.json</a>
            </div>
          </dd>
        </dl>
      </div>

      <p className="lead">
        <strong>memory_root ditampilkan apa adanya.</strong> Halaman ini tidak menghitung root:
        angka di atas dibaca langsung dari bundel yang ditulis agen, dan root yang MENGIKAT adalah
        yang tercatat di transaksi <code>VerdictPosted</code> di atas.
      </p>

      {gate ? (
        <div>
          <h2>Keputusan gerbang (tanpa evaluasi deliverable)</h2>
          <p className="lead">
            Job ini ditolak <em>sebelum</em> deliverable dinilai, jadi bundelnya berbentuk{" "}
            <code>gate-rejection</code> dan tidak punya hasil cek per-kriteria.
          </p>
          <div className="card">
            <dl className="kv">
              <dt>diterima?</dt>
              <dd>
                <span className={"tag " + (gate.accept ? "pass" : "fail")}>
                  {gate.accept ? "accept" : "reject"}
                </span>
              </dd>
              <dt>alasan</dt>
              <dd>{gate.reason}</dd>
              <dt>budget</dt>
              <dd className="mono">{readUint(gate.budget) ?? "belum ada"}</dd>
              <dt>cap provider</dt>
              <dd className="mono">
                {readUint(gate.cap?.usdc) ?? <span className="none">belum ada</span>} (basis{" "}
                {gate.cap?.basis ?? "—"}, sample_size {readUint(gate.cap?.sample_size) ?? "—"})
              </dd>
              <dt>risk level</dt>
              <dd className="mono">{readUint(gate.risk_level) ?? "belum ada"}</dd>
              <dt>job insiden yang mendasarinya</dt>
              <dd>
                {(gate.incident_jobs ?? []).length === 0 ? (
                  <span className="none">belum ada</span>
                ) : (
                  gate.incident_jobs.map((/** @type {any} */ j, i) => {
                    const id = readUint(j);
                    return (
                      <span key={i} className="mono">
                        {i > 0 ? ", " : ""}
                        {id ? <Link href={"/verdict/" + id}>{id}</Link> : "belum ada"}
                      </span>
                    );
                  })
                )}
              </dd>
              <dt>provider</dt>
              <dd>
                <AddressLink address={gate.provider} label={shorten(gate.provider)} />
              </dd>
            </dl>
          </div>
        </div>
      ) : null}

      {evaluation ? (
        <div>
          <h2>Bukti per-kriteria</h2>
          <p className="lead">
            Kategori rubric <code>{evaluation.category}</code>, kedalaman{" "}
            <code>{evaluation.depth}</code>. <code>failed_checks</code>:{" "}
            <span className="mono">
              {evaluation.failed_checks.length ? evaluation.failed_checks.join(", ") : "[] (kosong)"}
            </span>
          </p>
          <Checks checks={checks} criteria={evaluation.criteria} />

          {evaluation.unscored?.length ? (
            <div className="card warn">
              <h3 style={{ marginTop: 0 }}>Kriteria yang TIDAK dinilai</h3>
              <p className="mono">{evaluation.unscored.join(", ")}</p>
              <p style={{ marginBottom: 0 }}>{evaluation.unscored_reason}</p>
            </div>
          ) : null}
        </div>
      ) : null}

      <h2>Deliverable yang dinilai</h2>
      {deliverable ? (
        <div className="card">
          <dl className="kv">
            <dt>keccak256(teks)</dt>
            <dd>
              <Hash value={deliverable.sha_keccak} />
            </dd>
          </dl>
          <pre className="doc">{deliverable.text}</pre>
        </div>
      ) : (
        <p className="none">
          belum ada — job ini ditolak sebelum provider sempat submit, jadi tidak ada teks
          deliverable yang tersimpan.
        </p>
      )}
    </div>
  );
}
