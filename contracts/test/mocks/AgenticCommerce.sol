// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

/// @dev Subset ERC-20 yang dipakai escrow. USDC (6 desimal) mengembalikan bool pada transfer/transferFrom.
interface IERC20Minimal {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @dev Hook job ACP. Signature APA ADANYA dari `docs/api-facts.md` §A.2, yang mengutip
///      `contracts/interfaces/IACPHook.sol` di paket Sourcify `exact_match` (sha256
///      `4491e3ab…77d3`): `beforeAction` selector `0xdc08fb1d`, `afterAction` `0xa3fe4783`,
///      `type(IACPHook).interfaceId` = `0x7ff6bc9e`. JANGAN mengarang metode tambahan di sini.
interface IACPHook {
    function beforeAction(uint256 jobId, bytes4 selector, bytes calldata data) external;
    function afterAction(uint256 jobId, bytes4 selector, bytes calldata data) external;
}

/// @title AgenticCommerce — mock ACP (implementasi ERC-8183 milik Virtuals) untuk tes lokal.
/// @notice Signature, struct, event (termasuk `indexed`), custom error, urutan emit, aritmetika fee dan
///         semua batas status/waktu MENGIKUT `docs/api-facts.md` §A, yang diverifikasi dengan MENJALANKAN
///         BYTECODE ASLI `0x0b93793923CD5De81850aF8604a233f3f24d461e` di fork Base Sepolia (2026-09-03).
///         Bukan dari teks EIP-8183. Perbedaan yang paling sering salah: `fund` punya parameter kedua
///         `expectedBudget`.
/// @dev Cakupan sengaja dibatasi ke task 1.1: siklus Open→Funded→Submitted→Completed plus jalur
///      Rejected/Expired. Yang TIDAK ada di sini dan memang tidak dipanggil kode kita:
///      - Pemanggilan hook `beforeAction/afterAction` DI LUAR `complete`. Sejak `docs/api-facts.md` §A.2
///        berubah dari "BELUM diverifikasi" menjadi TERVERIFIKASI (interface `IACPHook` dari paket
///        Sourcify `exact_match`), alasan lama untuk tidak pernah meng-invoke hook GUGUR. Yang di-invoke
///        di sini baru `complete` (lihat catatan di fungsi itu), karena di situlah kanal masuk-ulang yang
///        menyentuh vault berada. Fungsi hookable di kontrak asli ada LIMA (api-facts §A.2): `setBudget`,
///        `fund`, `submit`, `complete`, `reject` — `createJob` dan `claimRefund` TIDAK hookable. Empat
///        sisanya di mock menyimpan `hook` tanpa memanggilnya —
///        MENYIMPANG dari kontrak asli, dan disengaja: mock TIDAK punya guard ERC-165 `createJob` milik
///        kontrak asli, jadi ia menerima alamat hook TANPA kode, dan meng-invoke alamat tanpa kode akan
///        merevert (solc menyisipkan cek `extcodesize` untuk panggilan tanpa return data). Menambahkan
///        guard ERC-165 + invocation penuh adalah perubahan tersendiri, bukan bagian task tes ini.
///      - Guard ERC-165 di `createJob` (kontrak asli: hook non-nol WAJIB `supportsInterface(0x7ff6bc9e)`,
///        kalau tidak `InvalidJob()`). Mock hanya mengecek `whitelistedHooks` → LEBIH PERMISIF dari asli.
///      - `setHookWhitelist/setEvaluatorFee/setPlatformFee` milik admin Virtuals. Parameternya tidak tercatat
///        di api-facts, jadi mock memakai setter bernama `mockSet*` supaya tidak bisa tertukar dengan ABI asli.
///      - AccessControl/UUPS/ERC1967: kontrak asli adalah proxy upgradeable; mock tidak, dan tidak perlu.
///      - Pausable: kontrak asli `whenNotPaused` di seluruh alur job (admin Virtuals). Mock tidak punya
///        `pause()`; konsekuensinya mock TIDAK bisa dipakai menguji cabang `EnforcedPause()`.
/// @dev URUTAN LOG MENTAH. `docs/api-facts.md` §A hanya mencatat urutan event ACP-SAJA (hasil
///      `vm.recordLogs` di fork yang disaring per emitter); ia TIDAK mengikat posisi `Transfer` ERC-20
///      di antara event ACP. Untuk itu mock mengikuti source terverifikasi Sourcify `AgenticCommerceV3.sol`
///      (sha256 `3b47cdbc…cddb`, `match=exact_match`): `complete` `:530-542` = Transfer→treasury,
///      Transfer→evaluator, EvaluatorFeePaid, Transfer→provider, JobCompleted, PaymentReleased;
///      auto-complete `:469-483` = JobSubmitted, Transfer→treasury, Transfer→provider, JobCompleted,
///      PaymentReleased. Dikunci `test_complete_rawLogOrder_matchesSource` dan
///      `test_autoComplete_rawLogOrder_matchesSource` atas log MENTAH (tanpa filter emitter).
///      Konsumen yang mengaitkan `Transfer` ke event ACP lewat kedekatan log-index bergantung pada ini.
/// @dev REENTRANCY: kontrak asli mewarisi `ReentrancyGuardTransient` OpenZeppelin (api-facts §A) — SATU slot
///      transient dipakai bersama, jadi guard-nya berlaku LINTAS FUNGSI dalam satu transaksi, dan
///      `createJob/setBudget/fund/submit/complete/reject/claimRefund` semuanya `nonReentrant`.
///      `setProvider` adalah SATU-SATUNYA fungsi alur job yang TIDAK `nonReentrant`. Mock meniru itu dengan
///      modifier `nonReentrant` di bawah (bukan OZ, karena lib OZ belum terpasang) yang merevert dengan
///      selector OZ yang sama, `ReentrancyGuardReentrantCall()` `0x3ee5aeb5` — selector itu memang ada di
///      bytecode implementasi. Tanpa ini, tes vault (task 1.2) bisa saja lulus dengan mengandalkan
///      reentrancy yang di produksi MUSTAHIL.
contract AgenticCommerce {
    /// @dev Nilai NUMERIK wajib sama dengan source terverifikasi (AgenticCommerceV3.sol:44-51) dan
    ///      api-facts §A: Open=0, Funded=1, Submitted=2, Completed=3, Rejected=4, Expired=5. `status`
    ///      menyeberangi ABI sebagai `uint8`; vault dan watcher membandingkannya sebagai ANGKA, jadi
    ///      menukar dua anggota di sini adalah perubahan yang MEMECAH kedua konsumen itu.
    ///      Dikunci `test_statusEnum_numericValuesMatchAcpAbi`.
    enum Status {
        Open,
        Funded,
        Submitted,
        Completed,
        Rejected,
        Expired
    }

    /// @dev Urutan field = tuple ABI asli `(address,uint8,address,uint48,address,address,uint256,string)`.
    ///      TIDAK ada field `id` (keberadaan job ditentukan `jobId < nextJobId`), dan `expiredAt` = uint48.
    struct Job {
        address client;
        Status status;
        address provider;
        uint48 expiredAt;
        address evaluator;
        address hook;
        uint256 budget;
        string description;
    }

    uint256 internal constant BP_DENOMINATOR = 10_000;
    /// @dev api-facts §A: `expiredAt` harus **>** now + 300 detik. `now+300` revert, `now+301` sukses.
    ///      BERPREFIKS `mock` DENGAN SENGAJA: kontrak asli TIDAK mengekspos konstanta ini — ambang 300
    ///      detik hanya terbaca dari PERILAKU di fork, bukan dari sebuah view publik. Kalau mock
    ///      menamainya `MIN_EXPIRY_DELAY`, kode yang membacanya hijau di lokal lalu REVERT di Sepolia —
    ///      cacat yang sama dengan `treasury` vs `platformTreasury`, cuma terbalik arahnya. Ketiadaan
    ///      `MIN_EXPIRY_DELAY()` (0xa2fe1c9a) di runtime code dikunci
    ///      `test_mockOnlyGetters_useMockPrefix_notAcpNames`.
    // forge-lint: disable-next-line(screaming-snake-case-const)
    uint256 public constant mockMinExpiryDelay = 5 minutes;
    /// @dev Konstanta PUBLIK kontrak asli, nama persis (`cast call <ACP> "EVALUATOR_GRACE_PERIOD()(uint256)"`
    ///      → 900). Tenggang `claimRefund` dari status Submitted, dihitung dari `expiredAt` — BUKAN dari waktu
    ///      submit. Bisection di fork: `expiredAt+899` revert `WrongStatus()`, `expiredAt+900` SUKSES.
    ///      Konstanta ini TIDAK ada di ABI paket SDK acp-node-v2 (ABI itu subset basi); jangan menyimpulkan
    ///      ketiadaannya dari sana. Jangan berasumsi angkanya sama di Base mainnet.
    uint256 public constant EVALUATOR_GRACE_PERIOD = 15 minutes;

    IERC20Minimal public immutable paymentToken;
    /// @dev BERPREFIKS `mock`: kontrak asli memakai AccessControl (`hasRole`/`grantRole`, api-facts §A.1)
    ///      dan TIDAK punya `admin()`. Hanya dipakai setter `mockSet*` di bawah.
    address public immutable mockAdmin;
    /// @dev NAMA ACP NYATA. View publik kontrak asli bernama `platformTreasury()` (api-facts §A;
    ///      Base Sepolia → 0xb3bdEdda2050a3615B73bB9a2684946eC38B5375), BUKAN `treasury()`. Mock yang
    ///      menyimpang di nama ini membuat pemanggil `platformTreasury()` hijau melawan chain nyata dan
    ///      REVERT melawan mock (atau sebaliknya) — mekanisme kegagalan yang identik dengan `jobs` yang
    ///      pernah `internal`. Dikunci `test_selectors_matchAcpAbi` atas RUNTIME CODE (selector
    ///      0xe138818c ADA, nama lama 0x61d027b3 TIDAK ADA).
    address public platformTreasury;

    /// @dev `cast call <ACP> "evaluatorFeeBP()(uint256)"` Base Sepolia 2026-09-03 = 500 (5%).
    uint256 public evaluatorFeeBP = 500;
    /// @dev `cast call <ACP> "platformFeeBP()(uint256)"` Base Sepolia 2026-09-03 = 100 (1%).
    uint256 public platformFeeBP = 100;

    mapping(address => bool) public whitelistedHooks;
    /// @dev PUBLIK, bukan `internal`: kontrak asli mengekspos getter `jobs(uint256)` (api-facts §A,
    ///      selector `0x180aedf3`) yang mengembalikan DELAPAN nilai
    ///      `(address,uint8,address,uint48,address,address,uint256,string)`, dan agen memanggilnya persis
    ///      begitu (`agent/agent/vault_client.py`, fragmen `ACP_ABI`). Saat mapping ini `internal`, mock
    ///      TIDAK punya getter itu, mock tidak punya fallback, dan agen REVERT di Anvil — mock gagal
    ///      sebagai harness tepat di titik yang dipakai. Dikunci `test_selectors_matchAcpAbi`
    ///      (keberadaan selector atas runtime code) dan `test_jobsGetter_returndataLayout_matchesAcpTuple`
    ///      (urutan + tipe tiap field). Perhatikan: keluaran getter mapping TIDAK dibungkus offset tuple
    ///      seperti `getJob`, karena ia delapan nilai terpisah, bukan satu struct.
    mapping(uint256 => Job) public jobs;
    /// @dev Job pertama ber-id 1.
    ///
    ///      `jobCounter()` SENGAJA TIDAK DIIMPLEMENTASIKAN di mock ini, dan itu bukan kelalaian —
    ///      jangan "melengkapi"nya tanpa membaca dua alasan di bawah. Kontrak asli mengekspos
    ///      `jobCounter()` (`docs/api-facts.md` §A, nilai 408 pada 3 Sep 2026); mock hanya punya
    ///      `nextJobId`, dan NAMANYA memang dibuat berbeda supaya tidak ada yang mengira
    ///      semantiknya identik:
    ///      1. SEMANTIK BERBEDA. `jobCounter()` = id job TERAKHIR yang dibuat; `nextJobId` = id
    ///         BERIKUTNYA yang akan dipakai (lihat `createJob`: `jobId = nextJobId++`).
    ///      2. `nextJobId - 1` ADALAH TEBAKAN, BUKAN FAKTA. Kesetaraan itu tidak pernah kami
    ///         verifikasi terhadap bytecode ACP asli; ia hanya kesimpulan dari nama. Dan pada mock
    ///         yang belum membuat job (`nextJobId == 1`) atau varian yang mulai dari 0, ekspresi itu
    ///         underflow/merevert. Menaruhnya di harness berarti mock BERBOHONG dengan angka yang
    ///         terlihat masuk akal — kegagalan yang jauh lebih mahal daripada mock yang absen.
    ///      KONSEKUENSI yang harus disadari: kode produksi yang memanggil `jobCounter()` HIJAU
    ///      melawan Base Sepolia tapi REVERT melawan mock ini di Anvil (mock tidak punya fallback),
    ///      yaitu tepat saat `make demo`. Karena itu larangannya dijaga MEKANIS di luar Foundry —
    ///      `agent/tests/test_acp_mock_divergence.py` memindai `agent/agent/` dan `sim/src/` dan
    ///      MERAH saat pemanggil pertama muncul. Kalau getter ini kelak memang dibutuhkan:
    ///      mintalah api-verifier mencatat semantiknya dari ACP nyata lebih dulu, baru
    ///      tambahkan ke sini — jangan hapus penjaganya.
    uint256 public nextJobId = 1;

    /// @dev Daftar `indexed` PERSIS ABI asli (api-facts §A), dikonfirmasi ke log nyata job #403.
    ///      `evaluator` di `JobCreated` sengaja TIDAK indexed — watcher tidak bisa memfilter lewat topic.
    event JobCreated(
        uint256 indexed jobId,
        address indexed client,
        address indexed provider,
        address evaluator,
        uint256 expiredAt,
        address hook
    );
    event ProviderSet(uint256 indexed jobId, address indexed provider);
    event BudgetSet(uint256 indexed jobId, uint256 amount);
    event JobFunded(uint256 indexed jobId, address indexed client, uint256 amount);
    event JobSubmitted(uint256 indexed jobId, address indexed provider, bytes32 deliverable);
    event JobCompleted(uint256 indexed jobId, address indexed evaluator, bytes32 reason);
    event JobRejected(uint256 indexed jobId, address indexed rejector, bytes32 reason);
    event JobExpired(uint256 indexed jobId);
    event PaymentReleased(uint256 indexed jobId, address indexed provider, uint256 amount);
    event EvaluatorFeePaid(uint256 indexed jobId, address indexed evaluator, uint256 amount);
    event Refunded(uint256 indexed jobId, address indexed client, uint256 amount);

    /// @dev Error PROYEK milik kontrak asli (api-facts §A): ada SEBELAS, bukan sembilan. Angka sembilan
    ///      berasal dari ABI paket SDK acp-node-v2 yang ternyata SUBSET BASI (21 error vs 25 di ABI
    ///      terverifikasi Sourcify) — `ClientIsProvider`/`EvaluatorIsProvider` hilang di sana tetapi ADA dan
    ///      DIPAKAI di kontrak. Yang tetap TIDAK ada: `PastExpiry`/`NotYetExpired`/`UnknownJob`/`NotClient`/
    ///      `NotProvider`/`NotEvaluator`/`BudgetNotSet`/`ZeroAmount`; `BudgetMismatch` TANPA argumen.
    ///      Sisanya (di luar 11 ini) milik OpenZeppelin: AccessControl*, ERC1967*, UUPS*, Pausable
    ///      (`EnforcedPause`/`ExpectedPause`), SafeERC20FailedOperation, FailedCall,
    ///      `ReentrancyGuardReentrantCall` (yang satu ini ikut dideklarasikan di bawah karena dipakai mock).
    error WrongStatus(); // 0x8e78f0cb
    error ExpiryTooShort(); // 0xf7a0748c
    error BudgetMismatch(); // 0x99b0fc87
    error InvalidJob(); // 0x71c8f460
    error Unauthorized(); // 0x82b42900
    error ProviderNotSet(); // 0xa9456d43
    error HookNotWhitelisted(); // 0xa04b28ec
    error ZeroAddress(); // 0xd92e233d
    error FeesTooHigh(); // 0xc9034e18
    error ClientIsProvider(); // 0x332ff0f9
    error EvaluatorIsProvider(); // 0xc7b4e9eb

    /// @dev Nama + selector PERSIS milik OpenZeppelin `ReentrancyGuardTransient`, karena kontrak asli
    ///      mewarisinya. `cast sig "ReentrancyGuardReentrantCall()"` → 0x3ee5aeb5.
    error ReentrancyGuardReentrantCall(); // 0x3ee5aeb5

    /// @dev Error KHUSUS MOCK, sengaja berawalan `Mock` supaya tidak pernah disangka bagian ABI asli.
    ///      Kontrak asli memakai AccessControl (admin) dan SafeERC20FailedOperation (transfer gagal).
    error MockNotAdmin();
    error MockTransferFailed();

    /// @dev Satu slot transient dipakai BERSAMA semua fungsi ber-`nonReentrant` → guard lintas fungsi,
    ///      persis semantik `ReentrancyGuardTransient`. Transient storage otomatis nol di akhir tx.
    bool private transient reentrancyLock;

    modifier nonReentrant() {
        if (reentrancyLock) revert ReentrancyGuardReentrantCall();
        reentrancyLock = true;
        _;
        reentrancyLock = false;
    }

    constructor(address paymentToken_, address treasury_) {
        if (paymentToken_ == address(0) || treasury_ == address(0)) revert ZeroAddress();
        paymentToken = IERC20Minimal(paymentToken_);
        platformTreasury = treasury_;
        mockAdmin = msg.sender;
    }

    // --------------------------------------------------------------------
    // Alur job (ABI acp-node-v2)
    // --------------------------------------------------------------------

    /// @notice Client membuat job. `evaluator` boleh `address(0)` (sentinel SDK = lewati evaluasi) dan
    ///         boleh berupa KONTRAK (ADR-003) — tidak ada asumsi EOA di mana pun.
    /// @dev `expiredAt` tetap `uint256` di signature (selector 0x41528812) tetapi disimpan `uint48`.
    ///      Batas atas DIBUKTIKAN di fork 2026-09-03: `expiredAt > type(uint48).max` → revert
    ///      `ExpiryTooShort()` (BUKAN truncation diam-diam seperti dugaan lama); tepat `type(uint48).max`
    ///      SUKSES, `2**48` dan `type(uint256).max` revert. Guard yang SAMA menolak `expiredAt <= now + 300`.
    ///      Guard identitas (api-facts §A, keduanya dibuktikan di fork): `msg.sender == provider` →
    ///      `ClientIsProvider()`; `evaluator != 0 && evaluator == provider` → `EvaluatorIsProvider()`.
    ///      BELUM DIVERIFIKASI: urutan relatif antara guard expiry dan guard identitas bila KEDUANYA
    ///      dilanggar sekaligus — tes sengaja tidak pernah melanggar keduanya bersamaan.
    function createJob(
        address provider,
        address evaluator,
        uint256 expiredAt,
        string calldata description,
        address hook
    ) external nonReentrant returns (uint256 jobId) {
        if (expiredAt <= block.timestamp + mockMinExpiryDelay || expiredAt > type(uint48).max) {
            revert ExpiryTooShort();
        }
        if (msg.sender == provider) revert ClientIsProvider();
        if (evaluator != address(0) && evaluator == provider) revert EvaluatorIsProvider();
        if (hook != address(0) && !whitelistedHooks[hook]) revert HookNotWhitelisted();

        jobId = nextJobId++;
        jobs[jobId] = Job({
            client: msg.sender,
            status: Status.Open,
            provider: provider,
            // casting to 'uint48' is safe because guard di atas sudah menolak expiredAt > type(uint48).max.
            // forge-lint: disable-next-line(unsafe-typecast)
            expiredAt: uint48(expiredAt),
            evaluator: evaluator,
            hook: hook,
            budget: 0,
            description: description
        });

        emit JobCreated(jobId, msg.sender, provider, evaluator, expiredAt, hook);
    }

    /// @notice Client menetapkan provider selagi job Open, belum lewat `expiredAt`, dan provider masih nol.
    /// @dev URUTAN CEK APA ADANYA dari sumber terverifikasi + fork 2026-09-03 (api-facts §A). Catatan lama
    ///      "tidak ada cek status" SALAH: job Open tanpa provider yang sudah di-`reject` (status 4) membuat
    ///      `setProvider` revert `WrongStatus()`, dan pada `now == expiredAt` (masih Open) juga `WrongStatus()`.
    ///      Kedua cek itu ada SEBELUM cek `msg.sender != client`, jadi pihak asing pun menerima
    ///      `WrongStatus()` (bukan `Unauthorized()`) pada job yang sudah lewat waktu/berstatus salah.
    ///      Ini SATU-SATUNYA fungsi alur job yang TIDAK `nonReentrant` di kontrak asli — sengaja ditiru.
    function setProvider(uint256 jobId, address provider_) external {
        Job storage job = _job(jobId);
        if (job.status != Status.Open) revert WrongStatus();
        if (block.timestamp >= job.expiredAt) revert WrongStatus();
        if (msg.sender != job.client) revert Unauthorized();
        if (job.provider != address(0)) revert WrongStatus();
        if (provider_ == address(0)) revert ZeroAddress();
        if (provider_ == job.client) revert ClientIsProvider();
        if (provider_ == job.evaluator) revert EvaluatorIsProvider();

        job.provider = provider_;
        emit ProviderSet(jobId, provider_);
    }

    /// @notice Provider menetapkan harga selagi job masih Open DAN `now < expiredAt`. Boleh BERULANG (menimpa).
    /// @dev `amount == 0` DITERIMA (api-facts §A) — jangan tambahkan guard ZeroAmount.
    ///      Guard waktu dibuktikan di fork 2026-09-03: pada `now == expiredAt` revert `WrongStatus()`.
    /// @dev URUTAN CEK APA ADANYA dari source terverifikasi (AgenticCommerceV3.sol:396-399):
    ///      status → expiry → OTORISASI TERAKHIR. Pihak asing pada job berstatus salah / lewat waktu
    ///      menerima `WrongStatus()`, BUKAN `Unauthorized()`.
    function setBudget(uint256 jobId, uint256 amount, bytes calldata optParams) external nonReentrant {
        Job storage job = _job(jobId);
        if (job.status != Status.Open) revert WrongStatus();
        if (block.timestamp >= job.expiredAt) revert WrongStatus();
        if (msg.sender != job.provider) revert Unauthorized();
        optParams; // hook payload; hook tidak di-invoke di mock (lihat catatan kontrak)

        job.budget = amount;
        emit BudgetSet(jobId, amount);
    }

    /// @notice Client mendanai escrow: Open→Funded. Memindahkan `budget` USDC dari client ke kontrak.
    /// @dev Selector kanonik acp-node-v2: `function fund(uint256,uint256,bytes)`. Parameter kedua adalah
    ///      `expectedBudget` (pengaman selip harga) — ini BERBEDA dari teks EIP-8183 yang hanya punya jobId.
    ///      `fund(jobId, 0, "")` pada job yang belum pernah `setBudget` DITERIMA (budget 0 sah).
    /// @dev URUTAN CEK APA ADANYA dari source terverifikasi (AgenticCommerceV3.sol:419-425):
    ///      `InvalidJob` → status != Open `WrongStatus()` → bukan client `Unauthorized()` → provider nol
    ///      `ProviderNotSet()` → `now >= expiredAt` `WrongStatus()` → budget beda `BudgetMismatch()`.
    ///      DUA hal yang dulu salah di mock: (1) otorisasi dicek sebelum status, sehingga pihak asing
    ///      menerima `Unauthorized()` di tempat ACP asli menjawab `WrongStatus()`; (2) guard expiry
    ///      `:424` HILANG, sehingga mock mendanai job kedaluwarsa dan mengunci USDC yang tak akan pernah
    ///      bisa di-`submit`.
    /// @param expectedBudget Budget yang dilihat client saat menandatangani; harus sama persis dengan budget on-chain.
    function fund(uint256 jobId, uint256 expectedBudget, bytes calldata optParams) external nonReentrant {
        Job storage job = _job(jobId);
        if (job.status != Status.Open) revert WrongStatus();
        if (msg.sender != job.client) revert Unauthorized();
        if (job.provider == address(0)) revert ProviderNotSet();
        if (block.timestamp >= job.expiredAt) revert WrongStatus();

        uint256 amount = job.budget;
        if (expectedBudget != amount) revert BudgetMismatch();
        optParams;

        job.status = Status.Funded;
        // Source `:431`: transfer HANYA bila `budget > 0`. Menarik 0 token tetap memancarkan
        // `Transfer` ERC-20 yang tidak pernah ada di ACP asli dan menuntut allowance yang tak diminta.
        _pull(job.client, amount);

        emit JobFunded(jobId, job.client, amount);
    }

    /// @notice Provider menyerahkan hasil: Funded→Submitted (atau →Completed bila tanpa evaluator).
    ///         Job **Open BERBUDGET NOL** juga boleh langsung di-submit. `deliverable` = keccak256 teks
    ///         penuh (api-facts §B.1).
    /// @dev Tiga hal yang terbukti dan mudah salah:
    ///      (1) status yang diterima BUKAN hanya Funded. Source terverifikasi (AgenticCommerceV3.sol:456-459):
    ///          `if (job.status != Funded && (job.status != Open || job.budget > 0)) revert WrongStatus();`
    ///          — job Open dengan `budget == 0` sah di-submit TANPA escrow sepeser pun (api-facts §A
    ///          "juga menerima Open→Completed bila budget == 0 & evaluator == 0"). Mock yang hanya
    ///          menerima Funded menyembunyikan kanal memory-poisoning berbiaya nol dari vault (task 1.2):
    ///          siapa pun yang jadi provider bisa membawa job ke Submitted/Completed gratis.
    ///      (2) submit DILARANG saat `now >= expiredAt` (tepat di `expiredAt` pun revert) → `WrongStatus()`,
    ///          bukan error waktu tersendiri. Source `:460` menjaga `expiredAt != 0` lebih dulu; di mock
    ///          `expiredAt` job yang ada selalu != 0 (`createJob` menolak nilai kecil), tapi cabangnya
    ///          tetap ditulis apa adanya agar tidak ada penyimpangan diam-diam.
    ///      (3) bila `evaluator == address(0)`, submit LANGSUNG menyelesaikan job: status → Completed,
    ///          provider menerima budget − platformFee SAJA (fee evaluator 0), `JobCompleted.reason` =
    ///          nilai `deliverable`, dan `complete()` sesudahnya revert `WrongStatus()`.
    /// @dev URUTAN CEK APA ADANYA (source `:455-461`): status → expiry → OTORISASI TERAKHIR.
    function submit(uint256 jobId, bytes32 deliverable, bytes calldata optParams) external nonReentrant {
        Job storage job = _job(jobId);
        if (job.status != Status.Funded && (job.status != Status.Open || job.budget > 0)) revert WrongStatus();
        if (job.expiredAt != 0 && block.timestamp >= job.expiredAt) revert WrongStatus();
        if (msg.sender != job.provider) revert Unauthorized();
        optParams;

        if (job.evaluator == address(0)) {
            uint256 budget = job.budget;
            uint256 platformFee = (budget * platformFeeBP) / BP_DENOMINATOR;
            uint256 providerAmount = budget - platformFee;

            job.status = Status.Completed;

            // Urutan log MENTAH source `:469-483`: JobSubmitted, Transfer→treasury, Transfer→provider,
            // JobCompleted, PaymentReleased. KEDUA transfer mendahului `JobCompleted`.
            emit JobSubmitted(jobId, job.provider, deliverable);
            _push(platformTreasury, platformFee);
            _push(job.provider, providerAmount);
            emit JobCompleted(jobId, address(0), deliverable);
            emit PaymentReleased(jobId, job.provider, providerAmount);
            return;
        }

        job.status = Status.Submitted;
        emit JobSubmitted(jobId, job.provider, deliverable);
    }

    /// @notice Evaluator meluluskan: Submitted→Completed. 100% budget cair dikurangi kedua fee; tidak ada
    ///         pembayaran parsial. TIDAK ada guard expiry — terbukti sukses pada `expiredAt + 1`.
    /// @dev Urutan event ACP terbukti di fork (`vm.recordLogs`): EvaluatorFeePaid, JobCompleted,
    ///      PaymentReleased. Itu urutan ACP-SAJA dan TIDAK menentukan posisi `Transfer` ERC-20 di
    ///      antaranya; urutan log MENTAH diambil dari source terverifikasi `:530-542` dan dikunci
    ///      `test_complete_rawLogOrder_matchesSource`.
    /// @dev URUTAN CEK: STATUS DULU, BARU OTORISASI (dibuktikan di fork 2026-09-03).
    ///      `complete(non-evaluator, status=Funded)` → `WrongStatus()`, BUKAN `Unauthorized()`;
    ///      `complete(evaluator, status=Funded)` → `WrongStatus()`;
    ///      `complete(non-evaluator, status=Submitted)` → `Unauthorized()` (kontrol: sama di kedua urutan).
    ///      Mock yang mengecek otorisasi lebih dulu akan menyimpang dari ACP asli di kasus pertama.
    /// @dev HOOK. `_beforeHook`/`_afterHook` di-invoke DI DALAM badan ber-`nonReentrant`, jadi hook
    ///      berjalan SELAGI kunci transient ACP dipegang — persis kontrak asli (api-facts §A.2:
    ///      `_beforeHook`/`_afterHook` `:293-301`/`:305-314` memanggil `IACPHook(hook).beforeAction/
    ///      afterAction(jobId, msg.sig, data)` TANPA try/catch; §A: semua fungsi alur job `nonReentrant`
    ///      dengan SATU slot transient bersama). Inilah kanal yang membuat "vault memanggil balik ACP dari
    ///      dalam eksekusi ACP" bisa diuji lokal. Nilainya BUKAN "satu-satunya tes yang menggigit mutan
    ///      `nonReentrant`" — `test_sweepToken_reentrantTokenIsRejected` (1.2c) juga menggigitnya —
    ///      melainkan bahwa kanal ACP→hook TIDAK butuh aksi arbiter: siapa pun yang memasang hook
    ///      whitelisted pada job-nya sendiri sudah cukup, jauh lebih realistis daripada arbiter yang
    ///      menyapu token jahat lewat `sweepToken`.
    ///      Tiga detail berikut TERVERIFIKASI (api-facts §A.2, source Sourcify `exact_match`
    ///      `AgenticCommerceV3.sol`), bukan tebakan:
    ///      (1) `complete` MEMANG hookable — `:521` (`_beforeHook`) dan `:544` (`_afterHook`).
    ///          Daftar lengkap fungsi hookable ada LIMA: `setBudget`, `fund`, `submit`, `complete`,
    ///          `reject`; `createJob` dan `claimRefund` TIDAK hookable;
    ///      (2) isi `data` = `abi.encode(msg.sender, reason, optParams)` — `:520` verbatim;
    ///      (3) `_beforeHook` berada SESUDAH cek status & otorisasi: `:515` InvalidJob → `:516`
    ///          WrongStatus → `:517` Unauthorized → `:520-521`. Panggilan yang ditolak tidak pernah
    ///          menyentuh hook. Selector rute hook untuk `complete` = `0xd75bbdf3`.
    function complete(uint256 jobId, bytes32 reason, bytes calldata optParams) external nonReentrant {
        Job storage job = _job(jobId);
        if (job.status != Status.Submitted) revert WrongStatus();
        if (msg.sender != job.evaluator) revert Unauthorized();

        _beforeHook(job.hook, jobId, msg.sig, abi.encode(msg.sender, reason, optParams));

        uint256 budget = job.budget;
        uint256 evaluatorFee = (budget * evaluatorFeeBP) / BP_DENOMINATOR;
        uint256 platformFee = (budget * platformFeeBP) / BP_DENOMINATOR;
        uint256 providerAmount = budget - evaluatorFee - platformFee;

        job.status = Status.Completed;

        // Urutan log MENTAH source `:530-542`: Transfer→treasury, Transfer→evaluator, EvaluatorFeePaid,
        // Transfer→provider, JobCompleted, PaymentReleased. Treasury dibayar DULU, dan KETIGA transfer
        // mendahului `JobCompleted`.
        // Source `:527-537` menjaga KETIGA transfer dengan `> 0`; di sini guard itu ada SATU kali, di
        // dalam `_push` — jadi `platformFee == 0` dan `net == 0` sama-sama tidak memancarkan `Transfer`.
        // Hanya cabang evaluator yang butuh `if` EKSPLISIT, karena yang dijaga bukan cuma transfernya
        // melainkan juga `emit EvaluatorFeePaid` (source `:533-536`, satu guard yang sama).
        // Dikunci `test_zeroAmountPaths_emitNoErc20Transfer` + `FundConservation.t.sol` (budget nol).
        _push(platformTreasury, platformFee);
        // TERVERIFIKASI (source `:533-536`): transfer fee evaluator DAN `EvaluatorFeePaid` berada di
        // dalam guard `evalFee > 0` yang SAMA — pada budget nol keduanya dilewati, jadi tidak ada
        // event fee beramount nol. Jalur berbudget nol NYATA (Open+budget 0+evaluator != 0 boleh
        // langsung di-`submit`), jadi ini bukan cabang teoretis.
        if (evaluatorFee != 0) {
            _push(job.evaluator, evaluatorFee);
            emit EvaluatorFeePaid(jobId, job.evaluator, evaluatorFee);
        }
        _push(job.provider, providerAmount);
        emit JobCompleted(jobId, job.evaluator, reason);
        emit PaymentReleased(jobId, job.provider, providerAmount);

        _afterHook(job.hook, jobId, msg.sig, abi.encode(msg.sender, reason, optParams));
    }

    /// @notice Menolak job. Refund 100% ke client (fee evaluator 0). TIDAK ada guard expiry — terbukti
    ///         sukses pada `expiredAt + 1`.
    /// @dev MATRIKS OTORISASI LENGKAP (fork 2026-09-03, api-facts §A). Catatan lama "saat Open hanya client"
    ///      SALAH — provider berhasil menolak job Open:
    ///        - Open                              → client ATAU provider;
    ///        - Funded/Submitted, `evaluator == 0` → client ATAU provider (pihak asing `Unauthorized()`);
    ///        - Funded/Submitted, `evaluator != 0` → HANYA evaluator (client/pihak asing `Unauthorized()`);
    ///        - status lain                       → `WrongStatus()`.
    ///      Catatan: kombinasi "Submitted + evaluator == 0" TIDAK bisa dicapai lewat alur normal, karena
    ///      `submit` pada job tanpa evaluator langsung menyelesaikan job (Completed).
    /// @dev Urutan emit `reject` BELUM diverifikasi di fork (yang terbukti hanya `complete` dan
    ///      `claimRefund`); mock memakai Refunded lalu JobRejected. Jangan jadikan urutan ini sebagai
    ///      fakta ACP di indexer.
    /// @dev `Refunded` hanya diemit bila `prev ∈ {Funded, Submitted}` **DAN `budget > 0`** — source
    ///      terverifikasi `:584-590`. Jalur berbudget nol NYATA karena `fund(jobId, 0, "")` sah, jadi
    ///      mengemit `Refunded(jobId, client, 0)` tanpa syarat akan melatih indexer pada event hantu.
    ///      Ini aturan yang SAMA dengan `claimRefund`.
    /// @dev HOOK. `reject` termasuk LIMA fungsi hookable kontrak asli (api-facts §A.2): `_beforeHook`
    ///      `:579`, `_afterHook` `:594`. Ini KANAL VAULT KEDUA — `EvaluatorVault.finalize` dengan
    ///      `kind = KIND_REJECT` menempuh jalur ini di produksi, jadi ia butuh cakupan masuk-ulang yang
    ///      sama dengan `complete`. Payload mengikuti bentuk yang diverifikasi untuk `complete` (`:520`
    ///      verbatim `abi.encode(msg.sender, reason, optParams)`); hook dipanggil SESUDAH cek
    ///      status/otorisasi dan DI DALAM badan ber-`nonReentrant`, sama seperti `complete`.
    function reject(uint256 jobId, bytes32 reason, bytes calldata optParams) external nonReentrant {
        Job storage job = _job(jobId);
        bytes memory hookData = abi.encode(msg.sender, reason, optParams);

        Status status = job.status;
        if (status == Status.Open) {
            if (msg.sender != job.client && msg.sender != job.provider) revert Unauthorized();

            _beforeHook(job.hook, jobId, msg.sig, hookData);

            job.status = Status.Rejected;
            emit JobRejected(jobId, msg.sender, reason);

            _afterHook(job.hook, jobId, msg.sig, hookData);
            return;
        }

        if (status != Status.Funded && status != Status.Submitted) revert WrongStatus();
        if (job.evaluator == address(0)) {
            if (msg.sender != job.client && msg.sender != job.provider) revert Unauthorized();
        } else if (msg.sender != job.evaluator) {
            revert Unauthorized();
        }

        _beforeHook(job.hook, jobId, msg.sig, hookData);

        uint256 amount = job.budget;
        job.status = Status.Rejected;

        if (amount != 0) {
            _push(job.client, amount);
            emit Refunded(jobId, job.client, amount);
        }
        emit JobRejected(jobId, msg.sender, reason);

        _afterHook(job.hook, jobId, msg.sig, hookData);
    }

    /// @notice SIAPA PUN boleh mengakhiri job yang lewat waktu: Open/Funded/Submitted → Expired.
    /// @dev KOREKSI 2026-09-03 (sumber terverifikasi Sourcify + bisection fork). Klaim lama
    ///      "HANYA dari Funded" dan "tidak ada griefing setelah submit" KEDUANYA SALAH dan sudah dihapus.
    ///      Tabel yang berlaku sekarang:
    ///        | status    | syarat waktu                    | transfer                    |
    ///        | Open      | `now >= expiredAt`              | tidak ada (belum ada escrow)|
    ///        | Funded    | `now >= expiredAt`              | 100% budget ke client       |
    ///        | Submitted | `now >= expiredAt + 900` (grace)| 100% budget, provider NOL   |
    ///        | Completed/Rejected/Expired | —              | selalu `WrongStatus()`      |
    ///      Anchor tenggang = `expiredAt`, BUKAN waktu submit: bisection `-1,0,+1,+100,+600,+898,+899` →
    ///      `WrongStatus()`; `+900,+901,+1800,…` → SUKSES. Dari Open/Funded TIDAK ada tenggang sama sekali.
    ///      MODEL ANCAMAN: griefing `claimRefund` sesudah `submit` BUKAN mustahil, hanya TERTUNDA 900 detik;
    ///      sesudahnya `complete`/`reject` evaluator revert `WrongStatus()` → verdict vault jadi YATIM.
    ///      Anggaran waktu vault kasus terburuk = `expiredAt + 900`.
    ///      Urutan emit terbukti (jalur Funded): Refunded, JobExpired.
    ///      TERVERIFIKASI (api-facts §A, tabel event `claimRefund`, dari source Sourcify `exact_match`
    ///      `:615-620` + fork): syarat emit `Refunded` adalah **`budget > 0` DAN status ∈ {Funded,
    ///      Submitted}**, bukan status saja. `Refunded` beramount NOL TIDAK PERNAH DIEMIT — termasuk
    ///      dari Funded/Submitted berbudget nol (jalur nyata: `fund(jobId, 0, "")` sah). `JobExpired`
    ///      adalah satu-satunya event yang PASTI ada di semua jalur refund; watcher harus memakainya
    ///      sebagai pemicu dan memperlakukan `Refunded` sebagai opsional.
    function claimRefund(uint256 jobId) external nonReentrant {
        Job storage job = _job(jobId);
        Status prev = job.status;
        if (prev != Status.Open && prev != Status.Funded && prev != Status.Submitted) revert WrongStatus();

        uint256 deadline = uint256(job.expiredAt);
        if (prev == Status.Submitted) deadline += EVALUATOR_GRACE_PERIOD;
        if (block.timestamp < deadline) revert WrongStatus();

        // Escrow hanya terisi sejak `fund`. Dari Open tidak ada apa pun untuk dikembalikan, walaupun
        // `setBudget` sudah pernah dipanggil (budget != 0 tidak berarti uang sudah masuk).
        uint256 amount = (prev == Status.Funded || prev == Status.Submitted) ? job.budget : 0;

        job.status = Status.Expired;

        if (amount != 0) {
            _push(job.client, amount);
            emit Refunded(jobId, job.client, amount);
        }
        emit JobExpired(jobId);
    }

    /// @notice Baca job. TIDAK revert untuk id tak dikenal — mengembalikan struct nol (api-facts §A).
    /// @dev Jangan pakai revert sebagai deteksi "job tidak ada"; bandingkan `job.client`/`job.evaluator`.
    function getJob(uint256 jobId) external view returns (Job memory) {
        return jobs[jobId];
    }

    // --------------------------------------------------------------------
    // Setter khusus MOCK. Sengaja TIDAK memakai nama fungsi admin ACP asli
    // (`setEvaluatorFee`/`setPlatformFee`/`setHookWhitelist`) karena parameternya
    // belum tercatat di api-facts §A dan kode kita tidak pernah memanggilnya.
    // --------------------------------------------------------------------

    function mockSetEvaluatorFeeBP(uint256 bp) external {
        if (msg.sender != mockAdmin) revert MockNotAdmin();
        if (bp + platformFeeBP > BP_DENOMINATOR) revert FeesTooHigh();
        evaluatorFeeBP = bp;
    }

    function mockSetPlatformFeeBP(uint256 bp) external {
        if (msg.sender != mockAdmin) revert MockNotAdmin();
        if (bp + evaluatorFeeBP > BP_DENOMINATOR) revert FeesTooHigh();
        platformFeeBP = bp;
    }

    function mockSetHookWhitelist(address hook, bool allowed) external {
        if (msg.sender != mockAdmin) revert MockNotAdmin();
        whitelistedHooks[hook] = allowed;
    }

    // --------------------------------------------------------------------

    /// @dev Hanya untuk fungsi yang MENGUBAH state: id tak dikenal → `InvalidJob()`.
    ///      Tidak ada field `id` di struct, jadi keberadaan diuji lewat rentang id.
    function _job(uint256 jobId) private view returns (Job storage) {
        if (jobId == 0 || jobId >= nextJobId) revert InvalidJob();
        return jobs[jobId];
    }

    function _pull(address from, uint256 amount) private {
        if (amount != 0 && !paymentToken.transferFrom(from, address(this), amount)) revert MockTransferFailed();
    }

    /// @dev Guard `amount != 0` bukan optimasi: source menjaga SETIAP transfer keluar dengan
    ///      `platformFee > 0` / `evalFee > 0` / `net > 0` (`:475-480`, `:530-539`), jadi job berbudget
    ///      nol tidak memancarkan `Transfer` sama sekali. Tanpa guard ini mock akan memancarkan
    ///      `Transfer(..., 0)` hantu yang meracuni watcher. Sama seperti `_pull`; dikunci
    ///      `test_zeroAmountPaths_emitNoErc20Transfer`.
    function _push(address to, uint256 amount) private {
        if (amount != 0 && !paymentToken.transfer(to, amount)) revert MockTransferFailed();
    }

    /// @dev No-op saat `hook == address(0)` (api-facts §A.2 `:293-301`), selain itu memanggil hook
    ///      TANPA try/catch: hook yang revert MEMBATALKAN seluruh transaksi ACP.
    function _beforeHook(address hook, uint256 jobId, bytes4 selector, bytes memory data) private {
        if (hook == address(0)) return;
        IACPHook(hook).beforeAction(jobId, selector, data);
    }

    /// @dev Pasangan `_beforeHook` (api-facts §A.2 `:305-314`), aturan revert sama.
    function _afterHook(address hook, uint256 jobId, bytes4 selector, bytes memory data) private {
        if (hook == address(0)) return;
        IACPHook(hook).afterAction(jobId, selector, data);
    }
}
