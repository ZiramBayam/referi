// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {ReentrancyGuardTransient} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IACP} from "./IACP.sol";

/// @title EvaluatorVault — wasit ERC-8183 dengan memori provider yang bisa diaudit
/// @notice Vault ini adalah `evaluator` di setiap job ACP (ADR-003): agen TIDAK PERNAH memanggil ACP
///         langsung. Agen mengumumkan verdict + akar memori di sini, siapa pun boleh mengeksekusinya
///         ke ACP setelah jendela challenge lewat.
/// @dev Acuan: `docs/spec.md` §4, ADR-001/003/007/011/013/014. Di luar lingkup dan sengaja TIDAK ADA:
///      proxy/upgradeable, pause, assembly, multi-arbiter, fee protokol (PRD §5).
///
/// ATURAN REENTRANCY (wajib dijaga saat menambah kode): vault memanggil ACP HANYA di dalam
/// `finalize`, dan hanya `complete`/`reject`. ACP asli sendiri ber-`ReentrancyGuardTransient` global
/// (selector `ReentrancyGuardReentrantCall()` `0x3ee5aeb5`), jadi memanggil balik ACP dari dalam
/// eksekusi ACP PASTI revert di jaringan nyata dan TIDAK akan pernah tertangkap tes lokal. Karena
/// itu `finalize` (satu-satunya jalur keluar) dan `deposit` (satu-satunya jalur ETH masuk) memakai
/// `nonReentrant` OZ 5.7.0. `sweepToken` menambah SATU panggilan keluar lagi — ke kontrak ERC-20
/// sembarang yang dipilih arbiter — jadi ia memakai guard yang SAMA: selama sapuan berlangsung,
/// token yang bertingkah (hook transfer, ERC-777) tidak bisa masuk kembali ke `finalize`,
/// `deposit`, maupun `sweepToken`.
contract EvaluatorVault is ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    // ------------------------------------------------------------------
    // Tipe
    // ------------------------------------------------------------------

    /// @param kind        1 = complete, 2 = reject (lihat `KIND_COMPLETE`/`KIND_REJECT`).
    /// @param reasonHash  keccak256 bundel bukti off-chain; diteruskan apa adanya ke ACP sebagai `reason`.
    /// @param memoryRoot  akar memori yang diumumkan bersama verdict (spec §3).
    /// @param readyAt     detik unix paling awal `finalize` boleh dieksekusi.
    /// @param finalized   true HANYA bila verdict BENAR-BENAR tereksekusi ke ACP (`Finalized`).
    ///                    Kegagalan ACP TIDAK menutup verdict (ADR-015): flag tetap `false`, `FinalizeFailed`
    ///                    diemit, dan `finalize` boleh diulang siapa pun kapan pun.
    /// @param challenger  DISEDIAKAN untuk mekanisme challenge; selama ADR-013 berlaku field ini
    ///                    tidak pernah ditulis maupun dibaca oleh logika apa pun.
    struct Verdict {
        uint8 kind;
        bytes32 reasonHash;
        bytes32 memoryRoot;
        uint64 readyAt;
        bool finalized;
        address challenger;
    }

    // ------------------------------------------------------------------
    // Konstanta
    // ------------------------------------------------------------------

    uint8 public constant KIND_COMPLETE = 1;
    uint8 public constant KIND_REJECT = 2;

    /// @notice Lama jendela challenge sesudah `postVerdict`.
    /// @dev ADR-014: `constant` biasa dan SENGAJA TIDAK settable/configurable. Angkanya dibatasi
    ///      anggaran waktu vault kasus terburuk `expiredAt + EVALUATOR_GRACE_PERIOD` = 901 detik
    ///      (api-facts §A): sesudah itu siapa pun boleh `claimRefund` job Submitted dan verdict kita
    ///      jadi yatim. Membesarkannya = memperbesar peluang verdict gugur.
    uint64 public constant CHALLENGE_WINDOW = 2 minutes;

    /// @notice Gas minimum yang harus TERSISA sebelum vault memanggil ACP.
    /// @dev ADR-015. `finalize` permissionless, jadi PEMANGGIL yang memilih gas limit. Tanpa ambang ini
    ///      pemanggil jahat bisa memangkas gas sampai panggilan ke ACP kehabisan gas, lalu `catch`
    ///      berjalan seolah-olah ACP menolak verdict yang sebenarnya sehat. Ambangnya dicek SEBELUM
    ///      `try` (bukan di dalam `catch`) supaya kehabisan gas itu tidak mungkin terjadi sama sekali —
    ///      penjaga berbasis RASIO sisa gas di dalam `catch` TERBUKTI TEMBUS, karena sisa EIP-150
    ///      menumpuk per kedalaman panggilan (1/64 → 127/4096 → ~4,6% pada kedalaman 3) sedangkan ACP
    ///      nyata SELALU >= kedalaman 3 dari vault (`vault → proxy ERC-1967 → implementasi
    ///      (DELEGATECALL) → paymentToken`).
    ///
    ///      ANGKANYA DIUKUR, BUKAN DIKARANG (perintah + hash tx lengkap di ADR-015):
    ///        - tx `complete` NYATA, EOA → ACP LANGSUNG, budget != 0, Base Sepolia
    ///          `0xa258c85c…3b849` / `0x817533707…82b32` / `0xfc8b36ba…d033e` / `0xaab5712e…5a361`
    ///          (blok 44.29xx.xxx): `gasUsed` = **89.628** (identik keempatnya; termasuk 21.000
    ///          intrinsik + calldata, jadi eksekusinya sendiri ~67k);
    ///        - `complete` berbudget 10 USDC atas mock salinan-setia DI BELAKANG `ERC1967Proxy`,
    ///          diukur dari posisi vault: **92.578** (tiga slot saldo ERC-20 dingin);
    ///        - pembanding: `complete` yang sama atas BYTECODE ASLI di fork Base Sepolia: 76.480;
    ///          tx budget-0 `0x9ef14777…1d09b`: 55.231.
    ///      `ceil25k(max(89.628, 92.578) * 3)` = `ceil25k(277.734)` = **300.000**.
    ///      TIDAK dihitung: tx `0x7b212fed…2670d` (`gasUsed` 192.163) — `to`-nya EntryPoint ERC-4337
    ///      `0x0000000071727De2…7da032`, jadi angkanya mengukur bundler + validasi smart account,
    ///      bukan `complete`. Vault memanggil ACP LANGSUNG, tanpa bundler. Bila angka itu tetap ingin
    ///      dipakai, konstanta ini menjadi 600.000 (ubah satu baris + `assertLe` di tes).
    ///      Faktor 3 menutup aturan 63/64, slot dingin, dan hook masa depan. Dikunci
    ///      `test_minAcpGas_isAtLeastThreeTimesMeasuredCost`.
    ///
    ///      Ambang ini adalah pertahanan BERLAPIS, bukan satu-satunya: sejak ADR-015 kegagalan ACP
    ///      apa pun — termasuk kehabisan gas — tidak lagi menutup verdict, jadi ambang yang meleset
    ///      hanya membuang satu transaksi, bukan membuat provider dibayar nol selamanya.
    uint256 public constant MIN_ACP_GAS = 300_000;

    // ------------------------------------------------------------------
    // Konfigurasi tetap
    // ------------------------------------------------------------------

    /// @notice Kontrak ACP tempat verdict dieksekusi.
    IACP public immutable acp;
    /// @notice Wallet agen evaluator (satu-satunya yang boleh `postVerdict`/`setProviderCap`).
    address public immutable agent;
    /// @notice Arbiter sengketa (MVP: multisig/juri; ADR-013 membuat perannya belum aktif).
    address public immutable arbiter;
    /// @notice Bond minimum yang harus tersedia sebelum agen boleh mengumumkan verdict.
    /// @dev Nilainya ditetapkan saat deploy, bukan dikarang di kode: `docs/spec.md` §4 hanya
    ///      menyebut adanya bond, tidak angkanya.
    uint256 public immutable MIN_BOND;

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------

    /// @notice Total ETH yang disetor sebagai bond evaluator (slot 0).
    /// @dev Sengaja akumulator eksplisit, bukan `address(this).balance`: ETH yang dipaksa masuk
    ///      (mis. `selfdestruct`) tidak boleh ikut memenuhi syarat bond.
    uint256 public bond;

    /// @notice Akar memori terakhir yang diumumkan (slot 1). UNTUK AUDITOR/UI SAJA.
    /// @dev ADR-011: nilai ini TIDAK PERNAH menjadi syarat eksekusi. Menjadikannya syarat
    ///      (`v.memoryRoot != lastMemoryRoot` → revert, spec §4 baris 138 yang SUDAH TIDAK BERLAKU)
    ///      mengunci verdict lama selamanya begitu verdict berikutnya diumumkan.
    bytes32 public lastMemoryRoot;

    /// @notice Verdict per jobId (slot 2).
    mapping(uint256 => Verdict) public verdicts;

    /// @notice Himpunan akar memori yang PERNAH diumumkan on-chain (slot 3).
    /// @dev ADR-011. Tidak ada fungsi penghapus: menghapus root = mengembalikan deadlock.
    mapping(bytes32 => bool) public knownRoots;

    /// @notice Batas budget (USDC, 6 desimal) yang dianggap aman untuk sebuah provider (slot 4).
    /// @dev **0 = TANPA BATAS**, bukan "diblokir" (ADR-001 + spec §3 aturan 4 `derive_cap`: risk 0 →
    ///      tanpa cap). Menurunkan cap ke 0 untuk "mengunci" provider justru MEMBUKA kuncinya.
    ///      Nilai ini tidak ditegakkan di kontrak; ia dibaca agen sebelum `postVerdict` (ADR-001).
    mapping(address => uint256) public providerCap;

    // ------------------------------------------------------------------
    // Event
    // ------------------------------------------------------------------

    event Deposited(address indexed from, uint256 amount, uint256 newBond);
    event ProviderCapSet(address indexed provider, uint256 capUsdc);
    event VerdictPosted(uint256 indexed jobId, uint8 kind, bytes32 reasonHash, bytes32 memoryRoot, uint64 readyAt);
    /// @dev Jangkar memori (spec §3). Dipakai agen saat start untuk fail-closed (spec §3 aturan 5).
    event MemoryRootUpdated(bytes32 indexed memoryRoot, uint256 indexed jobId);
    /// @notice Verdict berhasil dieksekusi ke ACP.
    event Finalized(uint256 indexed jobId, uint8 kind, bytes32 reasonHash);
    /// @notice Panggilan ke ACP GAGAL (mis. job sudah Expired karena `claimRefund` pihak ketiga, atau
    ///         ACP sedang `pause`). Verdict TIDAK ditutup: `finalized` tetap `false` dan `finalize`
    ///         boleh diulang siapa pun kapan pun (ADR-015). Tidak ada state yang deadlock karena
    ///         dananya ada di escrow ACP, bukan di vault.
    event FinalizeFailed(uint256 indexed jobId);
    /// @notice Fee evaluator (ERC-20) dikeluarkan dari vault oleh arbiter.
    /// @param token  kontrak ERC-20 yang disapu (token escrow ACP pada praktiknya).
    /// @param to     penerima; dipilih arbiter, tidak dibatasi kontrak.
    /// @param amount SELURUH saldo token itu pada saat sapuan.
    event TokenSwept(address indexed token, address indexed to, uint256 amount);

    // ------------------------------------------------------------------
    // Error
    // ------------------------------------------------------------------

    error NotAgent();
    error NotArbiter();
    error ZeroAddress();
    error ZeroDeposit();
    error ZeroMemoryRoot();
    error InvalidKind();
    error BondTooLow();
    error VerdictAlreadyPosted();
    error NoVerdict();
    error AlreadyFinalized();
    error ChallengeWindowOpen();
    error UnknownMemoryRoot();
    error InsufficientGasForAcpCall();
    /// @dev `sweepToken` dipanggil dengan alamat token yang tidak punya kode (EOA / salah ketik).
    ///      Tanpa cek ini `balanceOf` pada EOA merevert tanpa data sama sekali.
    error TokenNotContract();
    /// @dev Saldo token nol: tidak ada yang bisa disapu, jadi tx dibatalkan alih-alih mengemit
    ///      event sapuan palsu senilai 0.
    error NothingToSweep();
    /// @dev ADR-013: `challenge`/`resolve` sengaja belum diimplementasikan, tetapi TETAP ada di ABI
    ///      agar permukaan fungsi & otorisasinya terkunci tes sejak sekarang.
    error NotImplemented();

    // ------------------------------------------------------------------
    // Modifier
    // ------------------------------------------------------------------

    modifier onlyAgent() {
        if (msg.sender != agent) revert NotAgent();
        _;
    }

    modifier onlyArbiter() {
        if (msg.sender != arbiter) revert NotArbiter();
        _;
    }

    constructor(IACP acp_, address agent_, address arbiter_, uint256 minBond_) {
        if (address(acp_) == address(0) || agent_ == address(0) || arbiter_ == address(0)) revert ZeroAddress();
        acp = acp_;
        agent = agent_;
        arbiter = arbiter_;
        MIN_BOND = minBond_;
    }

    // ------------------------------------------------------------------
    // Bond
    // ------------------------------------------------------------------

    /// @notice Menyetor bond evaluator (ETH). HANYA agen.
    /// @dev ADR-015: `onlyAgent`, meskipun spec §4 menulis `deposit()` tanpa modifier. Alasannya
    ///      terukur, bukan selera: selama ADR-013 berlaku belum ada SATU PUN jalur ETH keluar dari
    ///      vault, jadi ETH dari alamat mana pun terkunci PERMANEN. Membiarkan fungsi ini terbuka
    ///      berarti mengundang orang asing mengunci dananya sendiri tanpa manfaat bagi siapa pun.
    ///      Agen tetap bisa mengunci ETH-nya sendiri — itu memang taruhan yang disengaja (bond).
    ///      Tidak ada `receive`/`fallback`, jadi ini satu-satunya jalur ETH masuk.
    function deposit() external payable onlyAgent nonReentrant {
        if (msg.value == 0) revert ZeroDeposit();
        uint256 newBond = bond + msg.value;
        bond = newBond;
        emit Deposited(msg.sender, msg.value, newBond);
    }

    // ------------------------------------------------------------------
    // Fee evaluator (ERC-20)
    // ------------------------------------------------------------------

    /// @notice Mengeluarkan SELURUH saldo sebuah token ERC-20 dari vault ke `to`. HANYA arbiter.
    /// @dev SEBABNYA TERUKUR, bukan antisipasi: `evaluatorFeeBP()` ACP di Base Sepolia = 500, jadi
    ///      setiap job yang `Completed` mengirim 5% budget ke alamat evaluator — yaitu vault ini
    ///      (ADR-003). Job 417 memindahkan 50.000 unit token escrow ke vault dan `docs/spec.md` §4
    ///      tidak punya satu pun jalur keluar untuknya; tiap job berikutnya menambah tumpukan itu.
    ///
    ///      HANYA ERC-20. `bond` adalah ETH, dan selama ADR-013 berlaku TIDAK BOLEH ada jalur ETH
    ///      keluar dari vault (bond evaluator harus tetap tersandera). Fungsi ini karena itu tidak
    ///      `payable`, tidak pernah menyentuh `bond`, tidak memakai `call`/`transfer` ETH, dan tidak
    ///      bisa dipakai untuk menyentuh saldo ETH vault dengan cara apa pun: satu-satunya panggilan
    ///      keluarnya adalah `transfer(address,uint256)` ke kontrak token.
    ///
    ///      Yang bisa disapu HANYA yang bukan bond: vault tidak menyimpan ERC-20 milik pihak lain —
    ///      escrow job ada di ACP, bukan di sini — jadi saldo ERC-20 vault menurut definisi adalah
    ///      fee evaluator (plus token nyasar, yang juga sah dikeluarkan). Karena itu tidak ada
    ///      "akuntansi fee" terpisah untuk dikurangi; saldo penuh yang disapu, dan ia dibaca dari
    ///      `balanceOf` pada saat panggilan, bukan dari angka yang disimpan dan bisa basi.
    ///
    ///      `onlyArbiter`, bukan `onlyAgent`: agen adalah pihak yang mengumumkan verdict, jadi
    ///      memberinya kunci ke hasil finansial dari verdictnya sendiri meniadakan pemisahan peran
    ///      yang justru dijaga guard `ArbiterEqualsAgent` di skrip deploy.
    ///
    ///      `safeTransfer` OZ 5.7.0 dipakai karena token escrow ACP tidak dijamin standar: token yang
    ///      MENGEMBALIKAN `false` alih-alih revert membuat tx revert `SafeERC20FailedOperation`,
    ///      sedangkan token gaya USDT yang tidak mengembalikan apa pun tetap diterima.
    /// @param token Kontrak ERC-20 yang disapu. WAJIB punya kode: tanpa cek itu `balanceOf` pada EOA
    ///              merevert tanpa data dan salah ketik alamat jadi sulit didiagnosis.
    /// @param to    Penerima. `address(0)` ditolak (banyak ERC-20 menerimanya = fee terbakar), begitu
    ///              pula vault sendiri (sapuan yang tidak memindahkan apa pun).
    /// @return amount Jumlah yang dipindahkan = seluruh saldo token itu sebelum sapuan.
    function sweepToken(address token, address to) external onlyArbiter nonReentrant returns (uint256 amount) {
        if (to == address(0)) revert ZeroAddress();
        if (to == address(this)) revert ZeroAddress();
        if (token.code.length == 0) revert TokenNotContract();

        amount = IERC20(token).balanceOf(address(this));
        if (amount == 0) revert NothingToSweep();

        // Checks-Effects-Interactions: vault tidak punya state akuntansi untuk token ini, jadi
        // "effects" yang ada hanyalah event — dan ia diemit SEBELUM panggilan keluar.
        emit TokenSwept(token, to, amount);
        IERC20(token).safeTransfer(to, amount);
    }

    // ------------------------------------------------------------------
    // Memori → gating (ADR-001)
    // ------------------------------------------------------------------

    /// @notice Menetapkan cap budget provider hasil `derive_cap` agen (spec §3 aturan 4).
    /// @param capUsdc Batas dalam satuan terkecil USDC (6 desimal). **0 = tanpa batas.**
    function setProviderCap(address provider, uint256 capUsdc) external onlyAgent {
        if (provider == address(0)) revert ZeroAddress();
        providerCap[provider] = capUsdc;
        emit ProviderCapSet(provider, capUsdc);
    }

    // ------------------------------------------------------------------
    // Verdict
    // ------------------------------------------------------------------

    /// @notice Agen mengumumkan verdict + akar memori. Belum mengeksekusi apa pun ke ACP.
    /// @dev ADR-011: root dicatat DUA kali — per job (`verdicts[jobId].memoryRoot`, yang mengikat
    ///      eksekusi nanti) dan sebagai himpunan (`knownRoots`, yang menjadi syarat `finalize`).
    ///      `lastMemoryRoot` hanya untuk auditor/UI.
    function postVerdict(uint256 jobId, uint8 kind, bytes32 reasonHash, bytes32 memoryRoot) external onlyAgent {
        if (kind != KIND_COMPLETE && kind != KIND_REJECT) revert InvalidKind();
        if (memoryRoot == bytes32(0)) revert ZeroMemoryRoot();
        if (bond < MIN_BOND) revert BondTooLow();

        Verdict storage v = verdicts[jobId];
        if (v.kind != 0) revert VerdictAlreadyPosted();

        uint64 readyAt = uint64(block.timestamp) + CHALLENGE_WINDOW;
        v.kind = kind;
        v.reasonHash = reasonHash;
        v.memoryRoot = memoryRoot;
        v.readyAt = readyAt;

        knownRoots[memoryRoot] = true;
        lastMemoryRoot = memoryRoot;

        emit VerdictPosted(jobId, kind, reasonHash, memoryRoot, readyAt);
        emit MemoryRootUpdated(memoryRoot, jobId);
    }

    /// @notice Menantang verdict sebelum `readyAt`, dengan bond penantang.
    /// @dev **STUB (ADR-013).** Fungsi tetap ada di ABI supaya permukaannya terkunci tes, tetapi
    ///      badannya selalu revert; `msg.value` otomatis kembali ke pemanggil karena tx dibatalkan.
    ///      Jangan "menghidupkan" ini tanpa sekaligus mengimplementasikan `resolve` — bond penantang
    ///      yang masuk tanpa jalur keluar = dana terjebak.
    function challenge(uint256 jobId, bytes32 counterEvidenceHash) external payable {
        jobId;
        counterEvidenceHash;
        revert NotImplemented();
    }

    /// @notice Arbiter memutus sengketa; bond pihak yang salah pindah ke pihak yang benar.
    /// @dev **STUB (ADR-013).** Cek peran SENGAJA dijalankan lebih dulu (modifier) supaya matriks
    ///      otorisasi sudah terkunci tes sebelum implementasinya ada: pihak asing menerima
    ///      `NotArbiter()`, arbiter menerima `NotImplemented()`.
    /// @dev solc memperingatkan "state mutability can be restricted to view" — DIABAIKAN dengan
    ///      sadar: `resolve` yang sebenarnya memindahkan bond antar pihak, jadi `stateMutability`
    ///      di ABI harus tetap `nonpayable`. Menuruti saran itu akan mengubah ABI yang sudah dipakai
    ///      watcher/UI dan memaksa perubahan ABI lagi saat ADR-013 dicabut.
    function resolve(uint256 jobId, bool evaluatorWasRight) external onlyArbiter {
        jobId;
        evaluatorWasRight;
        revert NotImplemented();
    }

    /// @notice Mengeksekusi verdict ke ACP. Permissionless (spec §4: "siapa pun, setelah readyAt").
    /// @dev Syarat root memakai `knownRoots`, BUKAN `lastMemoryRoot` (ADR-011). Tidak ada cabang
    ///      "challenge terbuka" selama ADR-013 berlaku.
    ///
    ///      Kegagalan ACP TIDAK direvert (temuan R1): siapa pun boleh membuat job jadi Expired lewat
    ///      `claimRefund` (dari Open/Funded sejak `expiredAt`, dari Submitted sejak
    ///      `expiredAt + EVALUATOR_GRACE_PERIOD`), dan sesudah itu `complete`/`reject` PASTI revert
    ///      `WrongStatus()`. Kalau kegagalan itu direvert, tx pemanggil gagal — jadi kegagalan hanya
    ///      diumumkan lewat `FinalizeFailed`.
    ///
    ///      KEGAGALAN TIDAK MENGGUGURKAN VERDICT (ADR-015, mengganti perilaku "gugur" yang lama):
    ///      `finalized` hanya menjadi `true` bila ACP benar-benar menerima eksekusi. Kegagalan yang
    ///      TEMPORER — ACP dipause lalu di-unpause, atau ambang gas belum terpenuhi — dengan begitu
    ///      bisa dicoba lagi. Menutup verdict pada percobaan pertama yang gagal berarti satu
    ///      transaksi murah dari orang asing bisa membuat provider dibayar NOL untuk pekerjaan yang
    ///      sudah dinyatakan lulus, tanpa jalur pemulihan.
    function finalize(uint256 jobId) external nonReentrant {
        Verdict storage v = verdicts[jobId];
        uint8 kind = v.kind;
        if (kind == 0) revert NoVerdict();
        if (v.finalized) revert AlreadyFinalized();
        if (block.timestamp < v.readyAt) revert ChallengeWindowOpen();
        if (!knownRoots[v.memoryRoot]) revert UnknownMemoryRoot();

        // Ambang gas dicek SEBELUM `try`: dengan begini panggilan ke ACP tidak mungkin kehabisan
        // gas, jadi `catch` hanya bisa berarti "ACP menolak", bukan "pemanggil pelit".
        if (gasleft() < MIN_ACP_GAS) revert InsufficientGasForAcpCall();

        bytes32 reasonHash = v.reasonHash;
        // Checks-Effects-Interactions: flag ditulis SEBELUM panggilan keluar, lalu DIKEMBALIKAN bila
        // ACP menolak. Selama panggilan berlangsung verdict tampak tertutup, sehingga jalur masuk
        // ulang mana pun (di luar `nonReentrant`) melihat `AlreadyFinalized`.
        v.finalized = true;

        if (kind == KIND_COMPLETE) {
            try acp.complete(jobId, reasonHash, "") {
                emit Finalized(jobId, kind, reasonHash);
            } catch {
                v.finalized = false;
                emit FinalizeFailed(jobId);
            }
        } else {
            try acp.reject(jobId, reasonHash, "") {
                emit Finalized(jobId, kind, reasonHash);
            } catch {
                v.finalized = false;
                emit FinalizeFailed(jobId);
            }
        }
    }
}
