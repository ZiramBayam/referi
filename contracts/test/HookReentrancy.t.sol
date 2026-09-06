// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Test, Vm} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {AgenticCommerce} from "./mocks/AgenticCommerce.sol";
import {ProxiableAgenticCommerce} from "./mocks/ProxiedAgenticCommerce.sol";
import {MockUSDC} from "./mocks/MockUSDC.sol";
import {EvaluatorVault} from "../src/EvaluatorVault.sol";
import {IACP} from "../src/IACP.sol";

/// @dev Hook job ACP yang JAHAT: dari dalam `beforeAction`/`afterAction` — yaitu dari dalam eksekusi
///      `complete` yang dipicu `EvaluatorVault.finalize` — ia memanggil balik `finalize(jobId LAIN
///      yang sehat)`.
///
///      EKSPLOITNYA (temuan review vault pass-2, SEDANG): tanpa `nonReentrant` di `finalize`,
///      panggilan balik itu MASUK, vault memanggil `acp.complete(job sehat)` selagi kunci transient
///      ACP masih dipegang oleh panggilan terluar, ACP merevert `ReentrancyGuardReentrantCall()`,
///      dan `catch` di `finalize` menerjemahkannya jadi `FinalizeFailed(job sehat)` — sebuah kegagalan
///      PALSU pada job yang tidak punya masalah apa pun. Job sehat itu tetap bisa di-`finalize` ulang,
///      tapi watcher/agen melihat sinyal gagal yang tidak pernah benar-benar terjadi.
///
///      `try/catch` di sini WAJIB: hook yang membiarkan revert-nya naik akan membatalkan seluruh
///      transaksi ACP (api-facts §A.2: hook dipanggil TANPA try/catch), sehingga eksploitnya tidak
///      bisa dibedakan dari "hook rusak".
contract ReenteringHook {
    EvaluatorVault public immutable vault;

    uint256 public targetJobId;

    bool public beforeTried;
    bool public beforeSucceeded;
    bytes public beforeRevertData;

    bool public afterTried;
    bool public afterSucceeded;
    bytes public afterRevertData;

    constructor(EvaluatorVault vault_) {
        vault = vault_;
    }

    function arm(uint256 targetJobId_) external {
        targetJobId = targetJobId_;
        beforeTried = false;
        afterTried = false;
        beforeSucceeded = false;
        afterSucceeded = false;
        beforeRevertData = "";
        afterRevertData = "";
    }

    function beforeAction(uint256, bytes4, bytes calldata) external {
        if (targetJobId == 0) return;
        beforeTried = true;
        (beforeSucceeded, beforeRevertData) = _reenter();
    }

    function afterAction(uint256, bytes4, bytes calldata) external {
        if (targetJobId == 0) return;
        afterTried = true;
        (afterSucceeded, afterRevertData) = _reenter();
    }

    /// @dev `IACPHook is IERC165` (api-facts §A.2). Mock belum menuntutnya, ACP nyata menuntut —
    ///      disediakan supaya hook ini tetap sah bila guard ERC-165 kelak ditambahkan ke mock.
    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x01ffc9a7 || interfaceId == 0x7ff6bc9e;
    }

    function _reenter() private returns (bool ok, bytes memory data) {
        (ok, data) = address(vault).call(abi.encodeCall(EvaluatorVault.finalize, (targetJobId)));
    }
}

/// @dev Hook PENGINTIP: tidak menyerang apa pun, hanya merekam APA yang dilihatnya. Ia yang mengunci
///      fakta yang baru diverifikasi api-verifier (api-facts §A.2, source `AgenticCommerceV3.sol`):
///      `complete` hookable (`:521`/`:544`), `data` = `abi.encode(msg.sender, reason, optParams)`
///      (`:520` verbatim), dan `_beforeHook` berjalan SESUDAH cek status/otorisasi tetapi SEBELUM
///      state berubah. `beforeAction` dan `afterAction` direkam TERPISAH: tanpa itu, menghapus salah
///      satunya dari mock tidak akan membuat satu tes pun merah.
contract SpyHook {
    AgenticCommerce public immutable acp;
    MockUSDC public immutable token;

    bool public beforeCalled;
    bool public afterCalled;
    uint256 public beforeJobId;
    uint256 public afterJobId;
    bytes4 public beforeSelector;
    bytes4 public afterSelector;
    bytes public beforeData;
    bytes public afterData;
    uint8 public statusInBefore;
    uint8 public statusInAfter;
    uint256 public providerBalanceInBefore;
    uint256 public providerBalanceInAfter;
    uint256 public clientBalanceInAfter;
    address public provider;
    address public client;

    constructor(AgenticCommerce acp_, MockUSDC token_) {
        acp = acp_;
        token = token_;
    }

    function beforeAction(uint256 jobId, bytes4 selector, bytes calldata data) external {
        beforeCalled = true;
        beforeJobId = jobId;
        beforeSelector = selector;
        beforeData = data;
        AgenticCommerce.Job memory job = acp.getJob(jobId);
        statusInBefore = uint8(job.status);
        provider = job.provider;
        client = job.client;
        providerBalanceInBefore = token.balanceOf(job.provider);
    }

    function afterAction(uint256 jobId, bytes4 selector, bytes calldata data) external {
        afterCalled = true;
        afterJobId = jobId;
        afterSelector = selector;
        afterData = data;
        AgenticCommerce.Job memory job = acp.getJob(jobId);
        statusInAfter = uint8(job.status);
        providerBalanceInAfter = token.balanceOf(job.provider);
        clientBalanceInAfter = token.balanceOf(job.client);
    }

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x01ffc9a7 || interfaceId == 0x7ff6bc9e;
    }
}

/// @dev Hook yang SELALU revert. api-facts §A.2: hook dipanggil TANPA try/catch, jadi ia membatalkan
///      seluruh transaksi ACP. Ini DoS verdict: pemilik job bisa memasang hook seperti ini dan membuat
///      `complete`/`reject` mustahil sampai `expiredAt + EVALUATOR_GRACE_PERIOD` lewat, lalu siapa pun
///      `claimRefund` dan provider dibayar NOL. Yang dikunci tes: vault tidak deadlock, tidak
///      kehilangan dana, dan verdict tidak pernah tertutup diam-diam (ADR-015).
contract RevertingHook {
    error HookRefuses();

    function beforeAction(uint256, bytes4, bytes calldata) external pure {
        revert HookRefuses();
    }

    function afterAction(uint256, bytes4, bytes calldata) external pure {
        revert HookRefuses();
    }

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x01ffc9a7 || interfaceId == 0x7ff6bc9e;
    }
}

/// @dev Hook yang MEMBAKAR gas dalam jumlah yang ditentukan tes. Gunanya membuktikan klaim yang
///      DIKOREKSI di `src/EvaluatorVault.sol`: `MIN_ACP_GAS` TIDAK membuat kehabisan gas mustahil,
///      karena biaya `complete` di ACP nyata memuat kode hook yang arbitrer. Yang menyelamatkan
///      verdict bukan ambang gas melainkan ADR-015 (kegagalan tidak menutup verdict).
contract GasBurningHook {
    uint256 public gasToBurn;
    uint256 public sink;

    function setGasToBurn(uint256 gasToBurn_) external {
        gasToBurn = gasToBurn_;
    }

    function beforeAction(uint256, bytes4, bytes calldata) external {
        uint256 target = gasleft() > gasToBurn ? gasleft() - gasToBurn : 0;
        while (gasleft() > target) {
            sink++;
        }
    }

    function afterAction(uint256, bytes4, bytes calldata) external {}

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x01ffc9a7 || interfaceId == 0x7ff6bc9e;
    }
}

/// @title HookReentrancyTest — kanal ACP → hook → vault (task 1.2d).
/// @notice Mock ACP dulu TIDAK PERNAH meng-invoke hook, sehingga kanal masuk-ulang yang benar-benar
///         ada di ACP nyata tidak pernah dieksekusi tes mana pun. `test/mocks/AgenticCommerce.sol`
///         kini meng-invoke `beforeAction`/`afterAction` di dalam `complete` DAN `reject` — dua fungsi
///         yang dipanggil vault — DI DALAM badan ber-`nonReentrant`, persis kontrak asli.
///
///         KOREKSI atas catatan lama di berkas ini: mutan "hapus `nonReentrant` dari `finalize`"
///         BUKAN lolos 112/112 lagi; sejak 1.2c ia juga digigit
///         `test_sweepToken_reentrantTokenIsRejected`. Nilai berkas ini terletak di tempat lain:
///         kanal ACP→hook TIDAK butuh aksi arbiter sama sekali (cukup pemilik job memasang hook
///         whitelisted pada job-nya sendiri), jadi ia jauh lebih realistis daripada kanal
///         "arbiter menyapu token jahat lewat `sweepToken`". Ia juga satu-satunya tempat di mana
///         perilaku vault terhadap hook pihak ketiga (revert, pembakar gas) benar-benar dieksekusi.
/// @dev Ini BUKAN "memanggil `finalize` dua kali berurutan": panggilan kedua berasal dari DALAM
///      `acp.complete`/`acp.reject`, saat kunci transient ACP masih dipegang.
contract HookReentrancyTest is Test {
    AgenticCommerce internal acp;
    address internal acpImpl;
    MockUSDC internal usdc;
    EvaluatorVault internal vault;
    ReenteringHook internal hook;

    address internal constant AGENT = address(0xA6E7);
    address internal constant ARBITER = address(0xA981);
    address internal constant STRANGER = address(0x5748);
    address internal constant CLIENT = address(0xC11E);
    address internal constant PROVIDER = address(0x9401);
    address internal constant TREASURY = address(0x77EA);

    uint256 internal constant BUDGET = 1_000_000; // 1 USDC — budget job 417 (pipa hidup)
    uint256 internal constant MIN_BOND = 0.1 ether;
    bytes32 internal constant DELIVERABLE = keccak256("deliverable");
    bytes32 internal constant REASON = keccak256("bundel bukti");
    bytes32 internal constant ROOT = keccak256("root A");

    bytes32 internal constant ERC1967_IMPL_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    event Finalized(uint256 indexed jobId, uint8 kind, bytes32 reasonHash);
    event FinalizeFailed(uint256 indexed jobId);

    function setUp() public {
        vm.warp(1_000_000);
        usdc = new MockUSDC();

        // Topologi ACP nyata: mock DI BELAKANG ERC1967Proxy (lihat ProxiedAgenticCommerce).
        ProxiableAgenticCommerce impl = new ProxiableAgenticCommerce(address(usdc), TREASURY);
        acpImpl = address(impl);
        ERC1967Proxy proxy = new ERC1967Proxy(
            address(impl),
            abi.encodeCall(
                ProxiableAgenticCommerce.initProxyState,
                (TREASURY, impl.evaluatorFeeBP(), impl.platformFeeBP(), impl.nextJobId())
            )
        );
        acp = AgenticCommerce(address(proxy));

        vault = new EvaluatorVault(IACP(address(acp)), AGENT, ARBITER, MIN_BOND);
        hook = new ReenteringHook(vault);
        // `mockAdmin` = deployer implementasi = kontrak tes ini (immutable, terbaca lewat delegatecall).
        acp.mockSetHookWhitelist(address(hook), true);

        usdc.mint(CLIENT, 1_000_000_000);
        vm.prank(CLIENT);
        usdc.approve(address(acp), type(uint256).max);

        vm.deal(AGENT, 10 ether);
        vm.prank(AGENT);
        vault.deposit{value: MIN_BOND}();
    }

    // ------------------------------------------------------------------
    // Helper
    // ------------------------------------------------------------------

    function _submittedJob(address hook_) internal returns (uint256 jobId) {
        vm.prank(CLIENT);
        jobId = acp.createJob(PROVIDER, address(vault), block.timestamp + 1 hours, "job", hook_);
        vm.prank(PROVIDER);
        acp.setBudget(jobId, BUDGET, "");
        vm.prank(CLIENT);
        acp.fund(jobId, BUDGET, "");
        vm.prank(PROVIDER);
        acp.submit(jobId, DELIVERABLE, "");
    }

    function _post(uint256 jobId) internal {
        _post(jobId, vault.KIND_COMPLETE());
    }

    function _post(uint256 jobId, uint8 kind) internal {
        vm.prank(AGENT);
        vault.postVerdict(jobId, kind, REASON, ROOT);
    }

    function _finalizedFlag(uint256 jobId) internal view returns (bool finalized) {
        (,,,, finalized,) = vault.verdicts(jobId);
    }

    function _status(uint256 jobId) internal view returns (uint8) {
        return uint8(acp.getJob(jobId).status);
    }

    // ------------------------------------------------------------------
    // Prasyarat: hook memang di-invoke dari DALAM `complete`
    // ------------------------------------------------------------------

    /// @dev Kalau tes ini merah, seluruh berkas ini kehilangan makna: hook tidak pernah dieksekusi dan
    ///      "masuk-ulang ditolak" jadi hijau palsu.
    function test_hookIsActuallyInvokedFromInsideComplete() public {
        uint256 healthy = _submittedJob(address(0));
        uint256 hooked = _submittedJob(address(hook));
        _post(healthy);
        _post(hooked);
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        hook.arm(healthy);
        vm.prank(STRANGER);
        vault.finalize(hooked);

        assertTrue(hook.beforeTried(), "beforeAction WAJIB dieksekusi dari dalam acp.complete");
        assertTrue(hook.afterTried(), "afterAction WAJIB dieksekusi dari dalam acp.complete");
    }

    /// @dev Kunci topologi: hook benar-benar terpasang di job, dan ACP tetap di balik proxy.
    function test_harness_hookIsAttachedAndAcpIsProxied() public {
        uint256 hooked = _submittedJob(address(hook));
        assertEq(acp.getJob(hooked).hook, address(hook), "hook terpasang di job");
        assertTrue(acp.whitelistedHooks(address(hook)), "hook di-whitelist");
        assertEq(address(uint160(uint256(vm.load(address(acp), ERC1967_IMPL_SLOT)))), acpImpl, "ACP harus proxy");
    }

    // ------------------------------------------------------------------
    // Eksploit: hook memanggil balik finalize(job LAIN yang sehat)
    // ------------------------------------------------------------------

    /// @dev INI mutan yang harus digigit: hapus `nonReentrant` dari `EvaluatorVault.finalize`.
    ///      Dengan guard: panggilan balik ditolak `ReentrancyGuardReentrantCall()` `0x3ee5aeb5`,
    ///      job sehat TIDAK tersentuh, dan TIDAK ada `FinalizeFailed` palsu.
    ///      Tanpa guard: panggilan balik masuk, ACP merevert karena kunci transient-nya sendiri, dan
    ///      vault mengemit `FinalizeFailed(job sehat)`.
    function test_reentrantFinalizeFromHook_isRejected_andHealthyJobUntouched() public {
        uint256 healthy = _submittedJob(address(0));
        uint256 hooked = _submittedJob(address(hook));
        _post(healthy);
        _post(hooked);
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        hook.arm(healthy);

        vm.recordLogs();
        vm.prank(STRANGER);
        vault.finalize(hooked);
        Vm.Log[] memory logs = vm.getRecordedLogs();

        // KEDUA titik hook diuji TERPISAH. `afterAction` adalah kasus yang paling halus: kunci
        // transient ACP masih dipegang, tetapi SELURUH pembayaran sudah terjadi.
        assertTrue(hook.beforeTried(), "beforeAction harus benar-benar dieksekusi");
        assertTrue(hook.afterTried(), "afterAction harus benar-benar dieksekusi");
        assertFalse(hook.beforeSucceeded(), "masuk-ulang dari beforeAction WAJIB ditolak");
        assertFalse(hook.afterSucceeded(), "masuk-ulang dari afterAction WAJIB ditolak");
        // `0x3ee5aeb5` = `ReentrancyGuardReentrantCall()`. Selector ini dipakai OZ DAN ditiru mock,
        // jadi ia sendiri tidak menunjukkan SIAPA yang menolak; yang membedakan adalah bahwa job
        // sehat tetap perawan (assert di bawah) — pada mutan tanpa guard, penolakan datang dari ACP
        // SESUDAH vault sempat menulis state dan mengemit `FinalizeFailed`.
        assertEq(bytes4(hook.beforeRevertData()), bytes4(0x3ee5aeb5), "beforeAction: ReentrancyGuardReentrantCall()");
        assertEq(bytes4(hook.afterRevertData()), bytes4(0x3ee5aeb5), "afterAction: ReentrancyGuardReentrantCall()");

        // Job sehat tidak boleh tersentuh sama sekali.
        assertFalse(_finalizedFlag(healthy), "job sehat tidak boleh ikut difinalisasi");
        assertEq(_status(healthy), 2, "job sehat harus tetap Submitted");
        for (uint256 i = 0; i < logs.length; i++) {
            if (logs[i].emitter != address(vault)) continue;
            assertTrue(
                logs[i].topics[0] != FinalizeFailed.selector || uint256(logs[i].topics[1]) != healthy,
                "FinalizeFailed PALSU pada job sehat"
            );
        }

        // Job berhook tetap selesai normal: guard tidak boleh merusak jalur bahagia.
        assertTrue(_finalizedFlag(hooked), "job berhook harus tetap terfinalisasi");
        assertEq(_status(hooked), 3, "job berhook Completed");
        assertEq(usdc.balanceOf(PROVIDER), 940_000, "payout provider job berhook (pipa hidup 417)");

        // Dan job sehat masih bisa difinalisasi sesudahnya, oleh siapa pun.
        vm.expectEmit(true, false, false, true, address(vault));
        emit Finalized(healthy, vault.KIND_COMPLETE(), REASON);
        vm.prank(STRANGER);
        vault.finalize(healthy);
        assertTrue(_finalizedFlag(healthy), "job sehat akhirnya terfinalisasi");
        assertEq(_status(healthy), 3, "job sehat Completed");
    }

    /// @dev Varian: hook memanggil balik `finalize` untuk JOB YANG SAMA. Dua lapis harus menolak —
    ///      `nonReentrant` (yang diuji di sini) dan, seandainya guard hilang, `AlreadyFinalized`
    ///      karena CEI menulis flag sebelum panggilan keluar. Karena itu tes ini SENDIRI tidak cukup
    ///      untuk menggigit mutan `nonReentrant`; ia hanya mengunci bahwa jalur ini tidak
    ///      menggandakan pembayaran.
    function test_reentrantFinalizeSameJobFromHook_isRejected() public {
        uint256 hooked = _submittedJob(address(hook));
        _post(hooked);
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        hook.arm(hooked);
        vm.prank(STRANGER);
        vault.finalize(hooked);

        assertTrue(hook.beforeTried() && hook.afterTried(), "kedua titik hook harus dieksekusi");
        assertFalse(hook.beforeSucceeded(), "masuk-ulang job yang sama dari beforeAction WAJIB ditolak");
        assertFalse(hook.afterSucceeded(), "masuk-ulang job yang sama dari afterAction WAJIB ditolak");
        assertTrue(_finalizedFlag(hooked), "job tetap terfinalisasi sekali");
        assertEq(_status(hooked), 3, "Completed");
        assertEq(usdc.balanceOf(PROVIDER), 940_000, "provider dibayar TEPAT sekali");
        assertEq(usdc.balanceOf(address(vault)), 50_000, "evaluatorFee tepat sekali");
        assertEq(usdc.balanceOf(TREASURY), 10_000, "platformFee tepat sekali");
        assertEq(usdc.balanceOf(address(acp)), 0, "escrow kosong: tidak ada wei nyangkut");
    }

    /// @dev Kontrol negatif untuk kesimpulan di atas: kalau hook memanggil balik ACP LANGSUNG
    ///      (bukan lewat vault), ACP sendiri yang menolak dengan selector yang sama. Ini yang membuat
    ///      `FinalizeFailed` palsu mungkin terjadi pada mutan — bukan bug vault, tapi konsekuensi
    ///      `catch` yang tidak bisa membedakan sebab kegagalan.
    function test_acpRejectsReentrancyIntoItself() public {
        uint256 healthy = _submittedJob(address(0));
        uint256 hooked = _submittedJob(address(hook));
        _post(healthy);
        _post(hooked);
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        DirectAcpReenteringHook direct = new DirectAcpReenteringHook(address(acp));
        // Job baru dengan hook yang menyerang ACP langsung.
        acp.mockSetHookWhitelist(address(direct), true);
        uint256 jobId = _submittedJob(address(direct));
        _post(jobId);
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());
        direct.arm(healthy);

        vm.prank(STRANGER);
        vault.finalize(jobId);

        assertTrue(direct.called(), "hook harus dieksekusi");
        assertFalse(direct.reentrySucceeded(), "ACP menolak masuk-ulang ke dirinya sendiri");
        assertEq(bytes4(direct.reentryRevertData()), bytes4(0x3ee5aeb5), "ReentrancyGuardReentrantCall() dari ACP");
    }

    // ------------------------------------------------------------------
    // Payload & titik hook (mengunci fakta terverifikasi api-facts §A.2)
    // ------------------------------------------------------------------

    /// @dev Mengunci EMPAT hal sekaligus untuk jalur `complete`, semuanya dari source terverifikasi:
    ///      (1) `_beforeHook` DAN `_afterHook` dipanggil — direkam terpisah, jadi menghapus salah
    ///          satunya membuat tes ini merah;
    ///      (2) `selector` yang diteruskan = `msg.sig` fungsi ACP, `complete(uint256,bytes32,bytes)`
    ///          = `0xd75bbdf3` (`cast sig`);
    ///      (3) `data` = `abi.encode(msg.sender, reason, optParams)` (`:520` verbatim) — `msg.sender`
    ///          dari sudut pandang ACP adalah VAULT, bukan pemanggil `finalize`;
    ///      (4) `_beforeHook` berjalan SESUDAH cek status/otorisasi tetapi SEBELUM state berubah:
    ///          hook melihat job masih Submitted(2) dan provider belum dibayar; `_afterHook` melihat
    ///          Completed(3) dan provider SUDAH dibayar penuh.
    function test_completeHookPayload_matchesVerifiedSource() public {
        SpyHook spy = new SpyHook(acp, usdc);
        acp.mockSetHookWhitelist(address(spy), true);
        uint256 jobId = _submittedJob(address(spy));
        _post(jobId);
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        vm.prank(STRANGER);
        vault.finalize(jobId);

        assertTrue(spy.beforeCalled(), "beforeAction WAJIB dipanggil (source :521)");
        assertTrue(spy.afterCalled(), "afterAction WAJIB dipanggil (source :544)");
        assertEq(spy.beforeJobId(), jobId, "jobId di beforeAction");
        assertEq(spy.afterJobId(), jobId, "jobId di afterAction");
        assertEq(spy.beforeSelector(), bytes4(0xd75bbdf3), "selector = complete(uint256,bytes32,bytes)");
        assertEq(spy.afterSelector(), bytes4(0xd75bbdf3), "selector afterAction = complete");

        // Panjang dicek dulu supaya payload yang dikarang gagal dengan pesan yang bisa dibaca, bukan
        // sekadar "EvmError: Revert" dari `abi.decode`.
        assertEq(spy.beforeData().length, 128, "payload = abi.encode(address,bytes32,bytes kosong)");
        (address sender, bytes32 reason, bytes memory optParams) =
            abi.decode(spy.beforeData(), (address, bytes32, bytes));
        assertEq(sender, address(vault), "data word0 = msg.sender ACP = VAULT (bukan pemanggil finalize)");
        assertEq(reason, REASON, "data word1 = reason yang diumumkan vault");
        assertEq(optParams.length, 0, "data word2 = optParams, vault selalu mengirim kosong");
        assertEq(keccak256(spy.afterData()), keccak256(spy.beforeData()), "payload after == before");

        // Titik pemanggilan, bukan sekadar isi payload.
        assertEq(spy.statusInBefore(), 2, "beforeAction melihat job masih Submitted");
        assertEq(spy.statusInAfter(), 3, "afterAction melihat job sudah Completed");
        assertEq(spy.providerBalanceInBefore(), 0, "beforeAction: provider BELUM dibayar");
        assertEq(spy.providerBalanceInAfter(), 940_000, "afterAction: provider SUDAH dibayar penuh");
    }

    /// @dev Cabang `KIND_REJECT` — kanal vault KEDUA, dan jalur produksi nyata `finalize(kind=2)`.
    ///      `reject(uint256,bytes32,bytes)` = `0x41dd26f5`; hook melihat Submitted(2) sebelum dan
    ///      Rejected(4) sesudah, dengan client sudah menerima refund 100% pada `afterAction`.
    function test_rejectHookPayload_matchesVerifiedSource() public {
        SpyHook spy = new SpyHook(acp, usdc);
        acp.mockSetHookWhitelist(address(spy), true);
        uint256 jobId = _submittedJob(address(spy));
        uint256 clientBefore = usdc.balanceOf(CLIENT);
        _post(jobId, vault.KIND_REJECT());
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        vm.prank(STRANGER);
        vault.finalize(jobId);

        assertTrue(spy.beforeCalled(), "beforeAction WAJIB dipanggil di reject (source :579)");
        assertTrue(spy.afterCalled(), "afterAction WAJIB dipanggil di reject (source :594)");
        assertEq(spy.beforeSelector(), bytes4(0x41dd26f5), "selector = reject(uint256,bytes32,bytes)");
        assertEq(spy.afterSelector(), bytes4(0x41dd26f5), "selector afterAction = reject");

        (address sender, bytes32 reason,) = abi.decode(spy.beforeData(), (address, bytes32, bytes));
        assertEq(sender, address(vault), "msg.sender ACP = vault");
        assertEq(reason, REASON, "reason vault");

        assertEq(spy.statusInBefore(), 2, "beforeAction melihat Submitted");
        assertEq(spy.statusInAfter(), 4, "afterAction melihat Rejected");
        assertEq(spy.clientBalanceInAfter(), clientBefore + BUDGET, "afterAction: client sudah menerima refund 100%");
        assertEq(usdc.balanceOf(PROVIDER), 0, "provider tidak dibayar di jalur reject");
        assertEq(usdc.balanceOf(address(vault)), 0, "reject: fee evaluator NOL");
    }

    /// @dev Masuk-ulang lewat cabang `reject`, bukan `complete`. Tanpa ini, separuh jalur produksi
    ///      vault (`kind = KIND_REJECT`) tidak punya cakupan masuk-ulang sama sekali.
    function test_reentrantFinalizeFromHook_onRejectPath_isRejected() public {
        uint256 healthy = _submittedJob(address(0));
        uint256 hooked = _submittedJob(address(hook));
        _post(healthy);
        _post(hooked, vault.KIND_REJECT());
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        hook.arm(healthy);

        vm.recordLogs();
        vm.prank(STRANGER);
        vault.finalize(hooked);
        Vm.Log[] memory logs = vm.getRecordedLogs();

        assertTrue(hook.beforeTried() && hook.afterTried(), "kedua titik hook `reject` dieksekusi");
        assertFalse(hook.beforeSucceeded(), "masuk-ulang dari beforeAction(reject) WAJIB ditolak");
        assertFalse(hook.afterSucceeded(), "masuk-ulang dari afterAction(reject) WAJIB ditolak");
        _assertNoFinalizeFailedFor(logs, healthy);

        assertFalse(_finalizedFlag(healthy), "job sehat tidak tersentuh");
        assertEq(_status(healthy), 2, "job sehat tetap Submitted");
        assertTrue(_finalizedFlag(hooked), "job berhook tetap ter-reject");
        assertEq(_status(hooked), 4, "job berhook Rejected");
    }

    // ------------------------------------------------------------------
    // Hook pihak ketiga yang bermusuhan: revert & pembakar gas
    // ------------------------------------------------------------------

    /// @dev ANCAMAN: hook dipanggil TANPA try/catch (api-facts §A.2), jadi hook yang selalu revert
    ///      membuat `complete` MUSTAHIL. Yang dikunci di sini adalah perilaku VAULT, bukan nasib job:
    ///      `finalize` tidak revert, verdict TIDAK tertutup (ADR-015), boleh diulang siapa pun berapa
    ///      kali pun, dan tidak ada dana vault yang hilang. Nasib job memang buruk dan itu di luar
    ///      kendali kita: sesudah `expiredAt + EVALUATOR_GRACE_PERIOD` siapa pun boleh `claimRefund`,
    ///      provider dibayar NOL dan verdict jadi yatim permanen. Bukan skenario teoretis — admin
    ///      Virtuals bahkan bisa melepas hook lewat `batchDetachHook` TANPA `pause` (api-facts §A.1).
    function test_revertingHook_dosesVerdict_butVaultStaysSafeAndRetryable() public {
        RevertingHook bad = new RevertingHook();
        acp.mockSetHookWhitelist(address(bad), true);
        uint256 jobId = _submittedJob(address(bad));
        _post(jobId);
        uint256 expiredAt = uint256(acp.getJob(jobId).expiredAt);
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        uint256 vaultEthBefore = address(vault).balance;

        for (uint256 i = 0; i < 3; i++) {
            vm.expectEmit(true, false, false, false, address(vault));
            emit FinalizeFailed(jobId);
            vm.prank(STRANGER);
            vault.finalize(jobId); // TIDAK revert
            assertFalse(_finalizedFlag(jobId), "verdict tidak boleh tertutup oleh kegagalan (ADR-015)");
            assertEq(_status(jobId), 2, "job tetap Submitted");
        }

        // Nasib job sesudah tenggang: siapa pun boleh membatalkannya.
        vm.warp(expiredAt + acp.EVALUATOR_GRACE_PERIOD());
        vm.prank(STRANGER);
        acp.claimRefund(jobId); // `claimRefund` TIDAK hookable → hook jahat tidak bisa menghalanginya
        assertEq(_status(jobId), 5, "Expired");
        assertEq(usdc.balanceOf(PROVIDER), 0, "provider dibayar NOL: verdict yatim");
        assertEq(usdc.balanceOf(address(vault)), 0, "vault tidak menerima fee evaluator");
        assertEq(usdc.balanceOf(address(acp)), 0, "escrow kosong: dana kembali ke client, tidak ada yang nyangkut");

        // Vault tetap sehat: `finalize` sesudahnya masih tidak revert, dan bond ETH utuh.
        vm.expectEmit(true, false, false, false, address(vault));
        emit FinalizeFailed(jobId);
        vm.prank(STRANGER);
        vault.finalize(jobId);
        assertFalse(_finalizedFlag(jobId), "verdict tetap terbuka, tidak pernah berbohong 'selesai'");
        assertEq(address(vault).balance, vaultEthBefore, "bond ETH vault tidak tersentuh");
    }

    /// @dev KOREKSI KLAIM (review pass-3): `MIN_ACP_GAS` TIDAK membuat kehabisan gas mustahil, karena
    ///      sejak `complete` terbukti hookable biaya ACP memuat kode arbitrer milik pemilik job. Tes
    ///      ini mengeksekusi persis kasus itu — gas DI ATAS ambang, tetap habis di dalam hook — dan
    ///      mengunci perilaku yang benar-benar berlaku: `FinalizeFailed`, verdict TETAP terbuka, dan
    ///      percobaan ulang dengan gas cukup BERHASIL membayar provider.
    function test_gasBurningHook_finalizeFailsAboveThreshold_thenSucceedsWithMoreGas() public {
        GasBurningHook burner = new GasBurningHook();
        acp.mockSetHookWhitelist(address(burner), true);
        burner.setGasToBurn(400_000); // > MIN_ACP_GAS, jadi 330k tidak cukup
        uint256 jobId = _submittedJob(address(burner));
        _post(jobId);
        vm.warp(block.timestamp + vault.CHALLENGE_WINDOW());

        assertGt(330_000, vault.MIN_ACP_GAS(), "gas percobaan pertama harus DI ATAS ambang");

        vm.expectEmit(true, false, false, false, address(vault));
        emit FinalizeFailed(jobId);
        vm.prank(STRANGER);
        vault.finalize{gas: 330_000}(jobId);
        assertFalse(_finalizedFlag(jobId), "verdict tetap terbuka sesudah kehabisan gas di dalam hook");
        assertEq(_status(jobId), 2, "job masih Submitted");
        assertEq(usdc.balanceOf(PROVIDER), 0, "belum ada pembayaran");

        // Percobaan ulang dengan gas jauh lebih besar: hook membakar 400k lalu selesai.
        vm.expectEmit(true, false, false, true, address(vault));
        emit Finalized(jobId, vault.KIND_COMPLETE(), REASON);
        vm.prank(STRANGER);
        vault.finalize{gas: 5_000_000}(jobId);
        assertTrue(_finalizedFlag(jobId), "verdict akhirnya tereksekusi");
        assertEq(_status(jobId), 3, "Completed");
        assertEq(usdc.balanceOf(PROVIDER), 940_000, "provider dibayar penuh pada percobaan kedua");
    }

    function _assertNoFinalizeFailedFor(Vm.Log[] memory logs, uint256 jobId) internal view {
        for (uint256 i = 0; i < logs.length; i++) {
            if (logs[i].emitter != address(vault)) continue;
            assertTrue(
                logs[i].topics[0] != FinalizeFailed.selector || uint256(logs[i].topics[1]) != jobId,
                "FinalizeFailed PALSU pada job sehat"
            );
        }
    }
}

/// @dev Hook yang memanggil balik ACP LANGSUNG (bukan lewat vault). Dipakai kontrol negatif.
contract DirectAcpReenteringHook {
    address public immutable acp;

    uint256 public targetJobId;
    bool public armed;
    bool public called;
    bool public reentrySucceeded;
    bytes public reentryRevertData;

    constructor(address acp_) {
        acp = acp_;
    }

    function arm(uint256 targetJobId_) external {
        targetJobId = targetJobId_;
        armed = true;
    }

    function beforeAction(uint256, bytes4, bytes calldata) external {
        _reenter();
    }

    function afterAction(uint256, bytes4, bytes calldata) external {
        _reenter();
    }

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x01ffc9a7 || interfaceId == 0x7ff6bc9e;
    }

    function _reenter() private {
        if (!armed) return;
        armed = false;
        called = true;
        (bool ok, bytes memory data) =
            acp.call(abi.encodeCall(IACP.complete, (targetJobId, keccak256("bundel bukti"), "")));
        reentrySucceeded = ok;
        reentryRevertData = data;
    }
}
