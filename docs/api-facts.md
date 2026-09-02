# API FACTS — satu-satunya sumber kebenaran untuk API eksternal
Aturan: kode HANYA boleh memanggil fungsi/metode yang tercantum di sini. Jika butuh sesuatu yang tidak ada di file ini,
BERHENTI, verifikasi dari sumber primer (URL di bawah), tambahkan ke file ini bersama URL-nya, baru pakai.
Diverifikasi 24 Agu 2026.

## A. Kontrak ACP (implementasi ERC-8183 milik Virtuals) — sumber: `src/core/acpAbi.ts`, `src/core/constants.ts` di
## https://github.com/Virtual-Protocol/acp-node-v2 ; spek: https://eips.ethereum.org/EIPS/eip-8183
Alamat:
- Base Sepolia (84532): `0x0b93793923CD5De81850aF8604a233f3f24d461e`
- Base mainnet (8453):  `0x238E541BfefD82238730D00a2208E5497F1832E0`
- Sentinel "tanpa evaluator" (EVM): `0x0000000000000000000000000000000000000000`
- API: prod `https://api.acp.virtuals.io`, testnet `https://api-dev.acp.virtuals.io`

Fungsi (ABI SDK — PERHATIKAN `fund` punya `expectedBudget`, berbeda dari teks EIP):
```
createJob(address provider, address evaluator, uint256 expiredAt, string description, address hook) returns (uint256 jobId)
setProvider(uint256 jobId, address provider)                 // client, saat Open
setBudget(uint256 jobId, uint256 amount, bytes optParams)    // provider, saat Open
fund(uint256 jobId, uint256 expectedBudget, bytes optParams) // client, Open→Funded; provider harus sudah di-set
submit(uint256 jobId, bytes32 deliverable, bytes optParams)  // provider, Funded→Submitted
complete(uint256 jobId, bytes32 reason, bytes optParams)     // evaluator, Submitted→Completed
reject(uint256 jobId, bytes32 reason, bytes optParams)       // client saat Open; evaluator saat Funded/Submitted
claimRefund(uint256 jobId)                                   // siapa pun, setelah expiredAt, Funded/Submitted→Expired
getJob(uint256 jobId) returns (Job)                          // Job{id, client, provider, evaluator, description, budget, expiredAt, status, hook}
evaluatorFeeBP() / platformFeeBP() / whitelistedHooks(address) — view
setHookWhitelist / setEvaluatorFee / setPlatformFee — admin Virtuals (BUKAN kita)
```
Event: JobCreated(jobId, client, provider, evaluator, expiredAt, hook); ProviderSet; BudgetSet(jobId, amount);
JobFunded(jobId, client, amount); JobSubmitted(jobId, provider, deliverable); JobCompleted(jobId, evaluator, reason);
JobRejected(jobId, rejector, reason); JobExpired(jobId); PaymentReleased(jobId, provider, amount);
EvaluatorFeePaid(jobId, evaluator, amount); Refunded(jobId, client, amount).
Status enum: Open=0, Funded=1, Submitted=2, Completed=3, Rejected=4, Expired=5.
Fakta perilaku (dari spek): evaluator ≠ 0 dicek di createJob referensi, TAPI SDK default = sentinel 0x0 (skip evaluasi).
Tidak ada pembayaran parsial. Tidak ada dispute/bond/timeout evaluator. `expiredAt` ≥ now+5 menit.
Hook dipanggil di setBudget/fund/submit/complete/reject; TIDAK di setProvider/claimRefund; hook harus whitelisted.

## B. SDK `@virtuals-protocol/acp-node-v2` — sumber: README repo di atas
```ts
import { AcpAgent, AssetToken } from "@virtuals-protocol/acp-node-v2";   // peer deps: viem, @account-kit/infra
const agent = await AcpAgent.create({ /* CreateAcpClientInput + transport?, api? */ });
agent.getAddress(); agent.getSession(chainId, jobId);
agent.createJob(chainId, { providerAddress, evaluatorAddress, expiredAt /*unix s*/, description, hookAddress? }) // → bigint jobId
agent.createJobFromOffering(chainId, offering, providerAddress, requirementData, { evaluatorAddress?, hookAddress?, packageId? })
session.setBudget(assetToken); session.fund(assetToken?); session.submit(deliverable /*string*/, transferAmount?);
session.complete(reason /*string*/); session.reject(reason /*string*/); session.sendMessage(content, contentType?)
AssetToken.usdc(0.1, base.id); AssetToken.usdcFromRaw(100000n, base.id)
agent.on("entry", async (session, entry) => { if (entry.kind === "system") switch (entry.event.type) { case "job.created": case "budget.set": case "job.funded": case "job.submitted": case "job.completed": case "job.rejected": } })
session.availableTools(); session.toMessages(); session.executeTool(name, args)   // untuk agen LLM
```
### B.1 Konversi `reason`/`deliverable` string → bytes32 — DIVERIFIKASI 2026-09-02 (menutup lubang verifikasi terakhir §B)
Diperiksa pada paket NYATA `@virtuals-protocol/acp-node-v2@0.1.12` (registry: `dist.shasum c5342f3c…cb96`), diekstrak &
dipasang di direktori sementara DI LUAR repo dengan `npm pack @virtuals-protocol/acp-node-v2@0.1.12` + `npm i` pada
Node v24.15.0 / viem 2.55.19. Yang dikutip = artefak `dist/` yang benar-benar dieksekusi (sourcemap memetakannya ke
`src/clients/evmAcpClient.ts`). ABI dikonfirmasi ulang lewat `import { ACP_ABI }`: `submit(uint256,bytes32 deliverable,bytes)`,
`complete(uint256,bytes32 reason,bytes)`, `reject(uint256,bytes32 reason,bytes)`, event `JobSubmitted/JobCompleted/JobRejected`
membawa `bytes32` non-indexed → §A benar.

**TIDAK ada satu aturan tunggal: `deliverable` dan `reason` diperlakukan BERBEDA. Jangan disamakan.**

`deliverable` (submit) — SELALU keccak, tanpa cabang, tanpa batas panjang. `dist/clients/evmAcpClient.js:75-81`:
```js
async submit(chainId, params) {
    return this.wrap(chainId, this.buildContractCall(chainId, "submit", [
        BigInt(params.jobId), keccak256(toHex(params.deliverable)), params.optParams ?? "0x", ]));
}
```
`reason` (complete/reject) — 3 cabang, `dist/clients/evmAcpClient.js:152-159` (`private static toBytes32`; `private` hanya
TS, saat runtime ia static biasa dan bisa dipanggil):
```js
static toBytes32(value) {
    if (value.startsWith("0x") && value.length === 66) return value;    // 1. hex 32-byte → DITERUSKAN APA ADANYA
    const hex = toHex(value);                                           //    (utf8 → hex)
    if (hex.length <= 66) return pad(hex, { size: 32, dir: "right" });  // 2. utf8 ≤ 32 B → padding NOL DI KANAN
    return keccak256(hex);                                              // 3. utf8 > 32 B → keccak256
}
```
Alasan asimetri itu ditulis sendiri oleh SDK di `dist/core/solana/encoding.js:12-21` (encoder Solana yang sengaja
"mirror the EVM client"): *"Unlike the deliverable (which is always hashed because the full text is kept off-chain via
postDeliverable), the reason has no off-chain copy, so short reasons must remain readable rather than being hashed and lost."*

Contoh KONKRET (output apa adanya dari menjalankan `EvmAcpClient.toBytes32` milik SDK sendiri, bukan reimplementasi):
| Input | utf8 | Cabang | Hasil bytes32 |
|---|---|---|---|
| `reason` = `"quality below rubric"` | 20 B | 2 pad-kanan | `0x7175616c6974792062656c6f7720727562726963000000000000000000000000` (= teks itu sendiri, bisa dibaca balik) |
| `reason` = `"0123456789abcdef0123456789abcdef"` | 32 B | 2 pad-kanan (batas MASIH lolos) | `0x3031323334353637383961626364656630313233343536373839616263646566` |
| `reason` = `"0123456789abcdef0123456789abcdefg"` | 33 B | 3 keccak | `0xc4d96194ea8ab65ed426578ad730558133cd44216c70dd4d83505ba51942e674` |
| `reason` = `"0x9c22ff5f21f0b81b113e63f7db6da94fedef11b2119b4088b89664fb9a3cb658"` | 66 B | 1 passthrough | nilai yang sama persis, tidak di-hash |
| `reason` = `""` | 0 B | 2 pad-kanan | `0x0000…0000` (bytes32 nol — tidak dilarang SDK) |
| `deliverable` = `"ipfs://bafkreiabc123"` | 20 B | selalu keccak | `0xc08fd6cd378f3bf0b1474acb8c35171dbde09e82d09074a574fcb6c9db20d3bd` |
| `deliverable` = string 66-char `0x…` di atas | 66 B | selalu keccak (TIDAK passthrough) | `0x4c56cd21e4213617574aa7cf2009104176f4d4ff5463b4a90ee854da95420e31` |

Batas yang menggigit:
- Batas padding = **32 byte, bukan 31**. Ini BUKAN `formatBytes32String` ethers v5 (yang maks 31 B karena menyimpan panjang).
- Diukur dalam **byte UTF-8, bukan karakter**: `"putusan: ditolak — bukti kurang"` = 31 karakter tapi 33 byte (em-dash 3 B)
  → jatuh ke cabang keccak, bukan padding. Jangan pakai panjang string JS/Python sebagai penentu.
- **Tidak pernah throw dan tidak pernah memotong.** String panjang diam-diam berubah jadi hash — konsekuensinya
  `JobCompleted.reason` kadang teks terbaca, kadang komitmen hash, tergantung panjang input. UI/indexer harus menangani KEDUANYA.
- Cabang 1 hanya memeriksa prefix `0x` + panjang 66; **isinya tidak divalidasi hex**. `"0x" + "z"*64` diteruskan apa adanya
  dan viem `encodeFunctionData` TIDAK menolaknya. Jadi jangan menyuapkan string arbitrer sepanjang 66 karakter.
- Network call: `session.submit()` → `AcpAgent.internalSubmit` (`dist/acpAgent.js:601-604`, juga `:863-865` untuk varian
  transfer) menjalankan `await this.api.postDeliverable(chainId, jobId, deliverable)` **SEBELUM** tx on-chain →
  `POST <serverUrl>/jobs/<chainId>/<jobId>/deliverable` body `{"deliverable": "<teks penuh>"}` (`dist/events/acpApiClient.js:20-30`),
  melempar bila `!res.ok` sehingga submit gagal total. **Tetapi yang di-hash adalah string LOKAL, bukan id/URL/payload balasan API.**
  `complete`/`reject` TIDAK memposting `reason` ke API sama sekali (tidak ada salinan off-chain).

Konsekuensi untuk `agent/vault_client.py` + `EvaluatorVault.sol` (mengoreksi catatan lama yang menduga "simpan ke API lalu hash"):
- `reason = keccak256(bundel bukti)` kita **kompatibel, tidak perlu diubah**. Nilai itu berupa hex 66 karakter, jadi kalaupun
  suatu saat melewati SDK ia kena cabang 1 (passthrough) dan menghasilkan bytes32 yang identik dengan panggilan langsung web3.py.
- Untuk memverifikasi deliverable provider: ambil teks penuh dari API ACP, lalu bandingkan dengan slot on-chain memakai
  `Web3.keccak(text=<teks>)` — sudah dibuktikan cocok byte-per-byte dengan `keccak256(toHex(s))` SDK
  (`"ipfs://bafkreiabc123"` → `c08fd6cd…d3bd` di kedua sisi; `uv run --no-project --with 'web3==7.16.0'`, web3 7.16.0/py3.13.15).
  Awas: di web3 7.x `HexBytes.hex()` mengembalikan hex **tanpa** prefix `0x` → tambahkan sendiri saat membandingkan string.
- Karena `reason` kita selalu hash 32 byte, ia TIDAK akan terbaca sebagai teks di explorer — berbeda dari `reason` pendek
  buatan SDK. Kalau demo butuh alasan yang terbaca on-chain, pakai label ≤32 byte UTF-8; bila tidak, tetap hash + tampilkan
  bundel bukti dari memori.

## C. Sibyl Memory — paket `sibyl-memory-client 0.7.0` (satu-satunya paket Sibyl yang dipakai; pin di docs/versions.md)
## Diverifikasi 2026-09-02 dengan `inspect.signature` di venv sekali-pakai DI LUAR repo:
## `uv run --no-project --with 'sibyl-memory-client==0.7.0' python probe.py` → Python 3.13.15,
## `importlib.metadata.version("sibyl_memory_client")` → `0.7.0`. Repo sekunder: https://github.com/Sibyl-Labs/Sibyl-Memory ;
## https://docs.sibyllabs.org/memory/concepts
Signature NYATA (salinan `inspect.signature`, `self` dibuang; `*` = keyword-only). Bukan tulisan tangan dari README:
```python
from sibyl_memory_client import MemoryClient, NotFoundError
MemoryClient.local(path: str|Path = '~/.sibyl-memory/memory.db', *, tenant_id: str = '00000000-0000-0000-0000-000000000001',
    tier: str = 'free', account_id: str|None = None, session_token: str|None = None,
    credentials_claim: dict|None = None, credentials_signature: str|None = None) -> MemoryClient   # classmethod
                                       # offline, tanpa `sibyl init` — diverifikasi offline 2026-09-02, bukti di bawah
# HOT
set_state(key: str, body: dict|list) -> None
get_state(key: str) -> dict|None                  # → {'body':…, 'updated_at':…} atau None — BUKAN body mentah
# WARM
set_entity(category: str, name: str, body: dict|list, *, status: str|None = None) -> dict
get_entity(category: str, name: str) -> dict      # MELEMPAR NotFoundError bila tidak ada (bukan None)
list_entities(category: str|None = None, *, status: str|None = None, limit: int = 100) -> list[dict]
search_entities(query: str, *, limit: int = 20, prefix: bool = False, category: str|None = None) -> list[dict]
# COLD (journal, append-only)
write_event(*, evaluated=None, acted=None, forward=None, extra=None, ts: str|None = None) -> str   # → event id; SEMUA keyword-only
read_events(*, limit: int = 50, since: str|None = None, until: str|None = None) -> list[dict]
# REFERENCE
set_reference(key: str, body: str|dict|list, *, metadata: dict|None = None) -> None
get_reference(key: str) -> dict|None
# ARCHIVE / hapus permanen
archive_entity(category: str, name: str, reason: str|None = None) -> dict   # → {'archived_id','original_id'}; MELEMPAR NotFoundError
delete_entity(category: str, name: str) -> bool   # True bila terhapus, False bila tidak ada (idempoten, tidak melempar)
```
Bentuk baris: entity = `{id, tenant_id, category, name, status, body, created_at, updated_at}` (`body` sudah di-deserialize);
event = `{id, ts, evaluated, acted, forward, extra}`.

KOREKSI vs deskripsi lama (semua dibuktikan `inspect.signature` + smoke test pada DB sementara):
- Parameter pertama entity bernama **`category`**, BUKAN `kind`. Pemanggilan posisional aman; `kind=…` → `TypeError`.
- `get_entity`/`archive_entity` MELEMPAR `NotFoundError`; `get_state`/`get_reference` mengembalikan `None`. Jangan disamakan.
- `get_state` mengembalikan pembungkus → pakai `["body"]`. `set_state`/`set_reference` mengembalikan `None`, `set_entity` → row.
- `set_reference` menyimpan dict/list sebagai **string JSON kanonik**; `get_reference(k)["body"]` bertipe `str` → perlu `json.loads`.
- `search_entities` **hanya tier WARM**, BUKAN "lintas tier". Lintas tier = `search(query, *, limit=20, prefix=False,
  tiers: tuple|None)` dengan tier sah `("entity","state","reference","journal")` (`ValueError` bila nama lain).
- `list_entities` default `limit=100` → diam-diam memotong; set eksplisit saat menghitung statistik provider.
- `read_events` TIDAK punya filter per-job/aktor, hanya `limit/since/until` → penyaringan dilakukan di sisi kita.
- `set_entity(..., status=…)` + `list_entities(status=…)` ADA → dipakai untuk `suspicion` berstatus `pending` (spec §3).

Tier FLAGGED: `schema.sql` 0.7.0 memang memuat tabel `flagged_actors` (komentar "FLAGGED tier", rule 13/14/15), TAPI
`client.py`/`storage.py` tidak mengekspos satu pun metode baca/tulis untuknya (hanya `lint.py` membacanya read-only)
→ tidak bisa dipakai dari SDK. Karantina TETAP entity `category="suspicion"`.
Perintah: `grep -rn "flagged_actors" <site-packages>/sibyl_memory_client/client.py <…>/storage.py` → kosong.
Metode publik lain yang ADA di 0.7.0 tapi di luar cakupan verifikasi ini (jangan dipanggil sebelum diverifikasi):
`search, learn, learner, lint, free_tier_status, get/set_tenant, get/set_tier, schema_version, storage,
accept_skill_proposal, reject_skill_proposal, list_skill_proposals`.
Python ≥ 3.10 (`requires_python` di https://pypi.org/pypi/sibyl-memory-client/json). Tier plugin default `local()` = `free`
→ cap lokal 5 MB, `set_entity`/`archive_entity` bisa melempar `CapExceededError`.

### Klaim "offline, tanpa `sibyl init`" — diverifikasi offline 2026-09-02
Yang diuji: `MemoryClient.local(<path baru>)` membuat DB dari nol tanpa `sibyl init` dan tanpa jaringan, lalu
`set_entity → get_entity → delete_entity → get_entity` (alur tes destruktif spec §7 langkah 3) berhasil. Dua fase sengaja
dipisah: instalasi paket JELAS butuh jaringan; yang diklaim offline hanya runtime SDK-nya. `$SP` = direktori kerja
sementara DI LUAR repo.

Fase 1 — INSTALASI (boleh jaringan, DI LUAR netns; BUKAN bagian dari klaim):
```
uv venv --python 3.13 $SP/venv-offline
uv pip install --python $SP/venv-offline/bin/python 'sibyl-memory-client==0.7.0'
$SP/venv-offline/bin/python -c "import importlib.metadata as m; print(m.version('sibyl_memory_client'))"
# → Installed 1 package: + sibyl-memory-client==0.7.0 ; Python 3.13.15 ; versi 0.7.0
```
Fase 2 — KLAIM (tanpa jaringan sama sekali; HANYA interpreter venv yang dijalankan, tidak ada resolusi/unduh paket.
`env -i` + HOME kosong baru → dipastikan tidak ada state `~/.sibyl-memory` atau kredensial sisa):
```
unshare -rn env -i HOME=$SP/fresh-home PATH=/usr/bin:/bin TMPDIR=$SP/tmp \
  $SP/venv-offline/bin/python $SP/probe_offline.py
```
Output apa adanya (exit 0):
```
HOME/.sibyl-memory exists = False
db exists before = False
db exists after local() = True | size = 4096
set_entity keys  = ['body', 'category', 'created_at', 'id', 'name', 'status', 'tenant_id', 'updated_at']
get_entity body  = {"evidence": ["a", "b"], "job_id": 42, "verdict": "reject"} | status = pending
delete_entity    = True bool
get_entity after delete -> NotFoundError: entity provider/0xdead not found for tenant 00000000-0000-0000-0000-000000000001
delete_entity (ulang, idempoten) = False
network events captured = []
RESULT: OK — offline, no `sibyl init`, no outbound socket
EXIT=0
```
Bonus "tidak ada usaha koneksi keluar": `sys.addaudithook` merekam event `socket.connect` / `socket.getaddrinfo` /
`socket.gethostbyname` / `urllib.Request` selama SELURUH probe termasuk `import sibyl_memory_client` → daftar kosong,
jadi bukan exception jaringan yang ditelan diam-diam. Kontrol bahwa netns memang mati: di dalam `unshare -rn`,
`socket.create_connection(("151.101.0.223", 443))` (IP langsung, tanpa DNS) → `OSError [Errno 101] Network is unreachable`,
dan `ip -o addr` tidak mencetak apa pun.
Konsekuensi operasional: `local()` membuat direktori induk bila belum ada, dan menghasilkan `memory.db` (header
`SQLite format 3`) + `memory.db-wal` + `memory.db-shm` → tes destruktif "hapus memori" harus menghapus KETIGA file,
bukan `memory.db` saja.

## D. Hackathon Sibyl — sumber: https://hack.sibyllabs.org
Build 1–10 Sep; rubric: memori load-bearing 40 / inovasi 25 / teknis 20 / pitch 15 / PMF +10; multiplier ×1.15 (1 stack)
/ ×1.25 (Base+Virtuals) hanya jika integrasi "doing real work"; submission: repo MIT/Apache-2.0, video 2–5 mnt
fresh-session recall, README, 2 post build-in-public. Gate: "Delete the memory layer. If your project still does what it
claims, it is a wrapper and does not qualify."

## E. Jaringan
Base Sepolia chainId 84532, RPC publik `https://sepolia.base.org`. USDC Base Sepolia & mainnet: lihat `docs/versions.md`
(diverifikasi dari Circle). Explorer: https://sepolia.basescan.org
