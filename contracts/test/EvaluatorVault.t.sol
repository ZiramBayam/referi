// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Test, Vm} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {AgenticCommerce} from "./mocks/AgenticCommerce.sol";
import {ProxiableAgenticCommerce, PausedACPImpl} from "./mocks/ProxiedAgenticCommerce.sol";
import {MockUSDC} from "./mocks/MockUSDC.sol";
import {EvaluatorVault} from "../src/EvaluatorVault.sol";
import {IACP} from "../src/IACP.sol";

/// @dev Mengukur biaya gas `complete` DARI POSISI VAULT (kedalaman panggilan yang sama persis).
///      Dipakai `test_minAcpGas_isAtLeastThreeTimesMeasuredCost` untuk mengunci turunan angka
///      `MIN_ACP_GAS` ke pengukuran, bukan ke selera.
contract MeasuringEvaluator {
    uint256 public lastGas;

    function doComplete(address acp_, uint256 jobId, bytes32 reason) external {
        uint256 g0 = gasleft();
        IACP(acp_).complete(jobId, reason, "");
        lastGas = g0 - gasleft();
    }
}

/// @dev ACP palsu yang MEMBAKAR SELURUH gas yang diteruskan. BUKAN model perilaku ACP — satu-satunya
///      gunanya adalah membuktikan bahwa `catch` di `finalize` TIDAK PERNAH menutup verdict, bahkan
///      ketika kegagalannya berupa kehabisan gas di sisi callee. Model perilaku ACP tetap
///      `test/mocks/AgenticCommerce.sol` (salinan setia kontrak terverifikasi), dipasang di belakang
///      `ERC1967Proxy` seperti ACP nyata.
contract GasBurnerACP {
    uint256 public sink;

    function complete(uint256, bytes32, bytes calldata) external {
        while (true) {
            sink++;
        }
    }

    function reject(uint256, bytes32, bytes calldata) external {
        while (true) {
            sink++;
        }
    }
}

/// @dev ERC-20 yang MENGEMBALIKAN `false` alih-alih revert saat transfer gagal — pola lama yang
///      membuat `transfer` tanpa `SafeERC20` gagal DIAM-DIAM (fee dianggap keluar padahal masih di
///      vault). Hanya `transfer` yang berbohong; `balanceOf` jujur.
contract FalseReturningToken {
    mapping(address => uint256) public balanceOf;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transfer(address, uint256) external pure returns (bool) {
        return false;
    }
}

/// @dev ERC-20 gaya USDT: `transfer` TIDAK mengembalikan apa pun. Dengan `IERC20.transfer` biasa
///      pemanggilan ini revert saat mendekode return; `safeTransfer` OZ menerimanya.
contract NoReturnToken {
    mapping(address => uint256) public balanceOf;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transfer(address to, uint256 amount) external {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
    }
}

/// @dev ERC-20 dengan hook: `transfer` memanggil balik vault dari DALAM `sweepToken`. Dipakai untuk
///      membuktikan dua lapis pertahanan sekaligus terhadap token yang bertingkah (ERC-777 dsb.):
///      (1) `finalize` yang PERMISSIONLESS — satu-satunya fungsi vault yang bisa dipanggil siapa pun,
///          jadi satu-satunya jalur masuk-ulang yang nyata — ditolak guard transient OZ;
///      (2) `sweepToken` itu sendiri ditolak lebih awal lagi oleh `onlyArbiter`, karena pemanggil
///          masuk-ulang adalah kontrak token, bukan arbiter.
contract ReentrantToken {
    mapping(address => uint256) public balanceOf;

    EvaluatorVault public vault;
    address public target;
    uint256 public jobId;
    bytes public finalizeRevertData;
    bytes public sweepRevertData;
    bool public reentered;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function arm(EvaluatorVault vault_, address target_, uint256 jobId_) external {
        vault = vault_;
        target = target_;
        jobId = jobId_;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        if (address(vault) != address(0) && !reentered) {
            reentered = true;
            (bool okFinalize, bytes memory dataFinalize) =
                address(vault).call(abi.encodeCall(EvaluatorVault.finalize, (jobId)));
            require(!okFinalize, "masuk-ulang finalize seharusnya ditolak");
            finalizeRevertData = dataFinalize;

            (bool okSweep, bytes memory dataSweep) =
                address(vault).call(abi.encodeCall(EvaluatorVault.sweepToken, (address(this), target)));
            require(!okSweep, "masuk-ulang sweepToken seharusnya ditolak");
            sweepRevertData = dataSweep;
        }
        return true;
    }
}

contract EvaluatorVaultTest is Test {
    /// @dev `acp` menunjuk ke ALAMAT PROXY (seperti ACP nyata), diketik sebagai mock supaya view-nya
    ///      bisa dibaca. `acpImpl` = alamat implementasi di baliknya.
    AgenticCommerce internal acp;
    address internal acpImpl;
    PausedACPImpl internal pausedImpl;
    MockUSDC internal usdc;
    EvaluatorVault internal vault;

    address internal constant AGENT = address(0xA6E7);
    address internal constant ARBITER = address(0xA981);
    address internal constant CHALLENGER = address(0xC4A1);
    address internal constant STRANGER = address(0x5748);
    address internal constant CLIENT = address(0xC11E);
    address internal constant PROVIDER = address(0x9401);
    address internal constant TREASURY = address(0x77EA);

    uint256 internal constant BUDGET = 10_000_000; // 10 USDC (6 desimal)
    uint256 internal constant MIN_BOND = 0.1 ether;
    bytes32 internal constant DELIVERABLE = keccak256("deliverable");
    bytes32 internal constant REASON = keccak256("bundel bukti");
    bytes32 internal constant ROOT_A = keccak256("root A");
    bytes32 internal constant ROOT_B = keccak256("root B");
    bytes32 internal constant ROOT_C = keccak256("root C");

    /// @dev Slot mapping `verdicts` di `EvaluatorVault` (bond=0, lastMemoryRoot=1, verdicts=2).
    ///      Dipakai HANYA oleh `test_finalize_unknownRoot_reverts`, dan tes itu memverifikasi ulang
    ///      asumsi layout ini lewat getter publik sebelum meng-assert apa pun.
    uint256 internal constant VERDICTS_SLOT = 2;

    /// @dev Slot implementasi ERC-1967 (`keccak256("eip1967.proxy.implementation") - 1`), nilai yang
    ///      sama dengan yang dipakai `docs/api-facts.md` §A untuk membaca implementasi ACP nyata.
    bytes32 internal constant ERC1967_IMPL_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    // Event vault (disalin agar `expectEmit` mengecek signature yang sama persis).
    event Deposited(address indexed from, uint256 amount, uint256 newBond);
    event ProviderCapSet(address indexed provider, uint256 capUsdc);
    event VerdictPosted(uint256 indexed jobId, uint8 kind, bytes32 reasonHash, bytes32 memoryRoot, uint64 readyAt);
    event MemoryRootUpdated(bytes32 indexed memoryRoot, uint256 indexed jobId);
    event Finalized(uint256 indexed jobId, uint8 kind, bytes32 reasonHash);
    event FinalizeFailed(uint256 indexed jobId);
    event TokenSwept(address indexed token, address indexed to, uint256 amount);

    // Event ACP (untuk membuktikan finalize benar-benar mengeksekusi ke ACP).
    event JobCompleted(uint256 indexed jobId, address indexed evaluator, bytes32 reason);
    event JobRejected(uint256 indexed jobId, address indexed rejector, bytes32 reason);

    function setUp() public {
        vm.warp(1_000_000);
        usdc = new MockUSDC();
        acp = _deployProxiedAcp();
        pausedImpl = new PausedACPImpl();
        vault = new EvaluatorVault(IACP(address(acp)), AGENT, ARBITER, MIN_BOND);

        usdc.mint(CLIENT, 1_000_000_000);
        vm.prank(CLIENT);
        usdc.approve(address(acp), type(uint256).max);

        vm.deal(AGENT, 10 ether);
        vm.deal(ARBITER, 10 ether);
        vm.deal(CHALLENGER, 10 ether);
        vm.deal(STRANGER, 10 ether);

        vm.prank(AGENT);
        vault.deposit{value: MIN_BOND}();
    }

    // ------------------------------------------------------------------
    // Harness topologi ACP nyata (task 1.2b)
    // ------------------------------------------------------------------

    /// @dev ACP nyata = proxy ERC-1967 (`docs/api-facts.md` §A). Setiap panggilan vault menempuh
    ///      `vault → proxy (CALL) → implementasi (DELEGATECALL) → paymentToken (CALL)`, yaitu
    ///      kedalaman >= 3. Sisa gas EIP-150 menumpuk per level, jadi harness kedalaman-1 memberi
    ///      angka sisa gas yang SALAH pada jalur kehabisan gas. Semua tes di file ini karena itu
    ///      memakai mock DI BELAKANG proxy, bukan mock telanjang.
    function _deployProxiedAcp() internal returns (AgenticCommerce proxied) {
        ProxiableAgenticCommerce impl = new ProxiableAgenticCommerce(address(usdc), TREASURY);
        acpImpl = address(impl);
        ERC1967Proxy proxy = new ERC1967Proxy(
            address(impl),
            abi.encodeCall(
                ProxiableAgenticCommerce.initProxyState,
                (TREASURY, impl.evaluatorFeeBP(), impl.platformFeeBP(), impl.nextJobId())
            )
        );
        proxied = AgenticCommerce(address(proxy));
        // State proxy WAJIB identik dengan state hasil-konstruktor implementasi. Kalau mock berubah
        // (mis. fee default lain), assert ini yang gagal — bukan puluhan tes lain secara misterius.
        assertEq(proxied.evaluatorFeeBP(), impl.evaluatorFeeBP(), "evaluatorFeeBP proxy != impl");
        assertEq(proxied.platformFeeBP(), impl.platformFeeBP(), "platformFeeBP proxy != impl");
        assertEq(proxied.nextJobId(), impl.nextJobId(), "nextJobId proxy != impl");
        assertEq(proxied.platformTreasury(), impl.platformTreasury(), "platformTreasury proxy != impl");
        assertEq(address(proxied.paymentToken()), address(impl.paymentToken()), "paymentToken proxy != impl");
        assertEq(proxied.EVALUATOR_GRACE_PERIOD(), impl.EVALUATOR_GRACE_PERIOD());
    }

    /// @dev "pause" ACP dengan menukar implementasi di balik proxy ke `PausedACPImpl` (semua entry
    ///      point revert `EnforcedPause()`). Storage proxy tidak disentuh, jadi `_unpauseAcp`
    ///      memulihkan seluruh state job apa adanya.
    function _pauseAcp() internal {
        vm.store(address(acp), ERC1967_IMPL_SLOT, bytes32(uint256(uint160(address(pausedImpl)))));
    }

    function _unpauseAcp() internal {
        vm.store(address(acp), ERC1967_IMPL_SLOT, bytes32(uint256(uint160(acpImpl))));
    }

    function _implOf(address proxy) internal view returns (address) {
        return address(uint160(uint256(vm.load(proxy, ERC1967_IMPL_SLOT))));
    }

    /// @dev Kunci topologi harness: kalau seseorang mengembalikan `acp` ke mock telanjang, tes ini
    ///      yang gagal lebih dulu.
    function test_harness_acpIsBehindErc1967Proxy() public view {
        assertTrue(acpImpl != address(0), "implementasi harus ada");
        assertTrue(acpImpl != address(acp), "acp harus PROXY, bukan implementasi telanjang");
        assertEq(_implOf(address(acp)), acpImpl, "slot ERC-1967 harus menunjuk ke implementasi");
        assertGt(address(acp).code.length, 0);
    }

    // ------------------------------------------------------------------
    // Helper alur ACP
    // ------------------------------------------------------------------

    function _createJob() internal returns (uint256 jobId) {
        vm.prank(CLIENT);
        jobId = acp.createJob(PROVIDER, address(vault), block.timestamp + 1 hours, "tulis laporan riset", address(0));
    }

    function _fundedJob() internal returns (uint256 jobId) {
        jobId = _createJob();
        vm.prank(PROVIDER);
        acp.setBudget(jobId, BUDGET, "");
        vm.prank(CLIENT);
        acp.fund(jobId, BUDGET, "");
    }

    function _submittedJob() internal returns (uint256 jobId) {
        jobId = _fundedJob();
        vm.prank(PROVIDER);
        acp.submit(jobId, DELIVERABLE, "");
    }

    function _post(uint256 jobId, uint8 kind, bytes32 root) internal {
        vm.prank(AGENT);
        vault.postVerdict(jobId, kind, REASON, root);
    }

    function _status(uint256 jobId) internal view returns (uint8) {
        return uint8(acp.getJob(jobId).status);
    }

    function _readyAt(uint256 jobId) internal view returns (uint64 readyAt) {
        (,,, readyAt,,) = vault.verdicts(jobId);
    }

    function _finalizedFlag(uint256 jobId) internal view returns (bool finalized) {
        (,,,, finalized,) = vault.verdicts(jobId);
    }

    // ------------------------------------------------------------------
    // Konstanta & konstruktor
    // ------------------------------------------------------------------

    /// @dev ADR-014: 2 menit, `constant`, TIDAK settable. Anggaran waktu vault kasus terburuk =
    ///      `expiredAt + EVALUATOR_GRACE_PERIOD` = 901 detik.
    function test_challengeWindow_isTwoMinutes() public view {
        assertEq(vault.CHALLENGE_WINDOW(), 120, "CHALLENGE_WINDOW harus 2 menit");
        assertLt(uint256(vault.CHALLENGE_WINDOW()), acp.EVALUATOR_GRACE_PERIOD(), "window harus muat di tenggang ACP");
    }

    function test_constructor_wiring() public view {
        assertEq(address(vault.acp()), address(acp));
        assertEq(vault.agent(), AGENT);
        assertEq(vault.arbiter(), ARBITER);
        assertEq(vault.MIN_BOND(), MIN_BOND);
        assertEq(vault.KIND_COMPLETE(), 1);
        assertEq(vault.KIND_REJECT(), 2);
    }

    function test_constructor_zeroAddress_reverts() public {
        vm.expectRevert(EvaluatorVault.ZeroAddress.selector);
        new EvaluatorVault(IACP(address(0)), AGENT, ARBITER, 0);
        vm.expectRevert(EvaluatorVault.ZeroAddress.selector);
        new EvaluatorVault(IACP(address(acp)), address(0), ARBITER, 0);
        vm.expectRevert(EvaluatorVault.ZeroAddress.selector);
        new EvaluatorVault(IACP(address(acp)), AGENT, address(0), 0);
    }

    /// @dev Vault TIDAK punya `receive`/`fallback`: ETH hanya masuk lewat `deposit()`.
    function test_plainEthTransfer_reverts() public {
        vm.prank(STRANGER);
        (bool ok,) = address(vault).call{value: 1 ether}("");
        assertFalse(ok, "transfer ETH polos harus gagal");
        assertEq(address(vault).balance, MIN_BOND);
    }

    // ------------------------------------------------------------------
    // deposit
    // ------------------------------------------------------------------

    function test_deposit_accountsAndEmits() public {
        vm.expectEmit(true, false, false, true, address(vault));
        emit Deposited(AGENT, 1 ether, MIN_BOND + 1 ether);
        vm.prank(AGENT);
        vault.deposit{value: 1 ether}();

        assertEq(vault.bond(), MIN_BOND + 1 ether);
        assertEq(address(vault).balance, MIN_BOND + 1 ether);
    }

    function test_deposit_zeroValue_reverts() public {
        vm.expectRevert(EvaluatorVault.ZeroDeposit.selector);
        vm.prank(AGENT);
        vault.deposit{value: 0}();
    }

    /// @dev ADR-015. Selama ADR-013 berlaku TIDAK ADA jalur ETH keluar dari vault, jadi setoran dari
    ///      alamat acak = dana terkunci permanen tanpa manfaat bagi siapa pun. Cek peran menutupnya.
    function test_deposit_stranger_reverts() public {
        uint256 balBefore = STRANGER.balance;
        vm.expectRevert(EvaluatorVault.NotAgent.selector);
        vm.prank(STRANGER);
        vault.deposit{value: 5 ether}();

        assertEq(STRANGER.balance, balBefore, "ETH orang asing harus kembali utuh");
        assertEq(vault.bond(), MIN_BOND, "bond tidak boleh berubah");
        assertEq(address(vault).balance, MIN_BOND, "vault tidak boleh menahan ETH orang asing");
    }

    // ------------------------------------------------------------------
    // setProviderCap
    // ------------------------------------------------------------------

    function test_setProviderCap_onlyAgent_happy() public {
        vm.expectEmit(true, false, false, true, address(vault));
        emit ProviderCapSet(PROVIDER, 5_000_000);
        vm.prank(AGENT);
        vault.setProviderCap(PROVIDER, 5_000_000);
        assertEq(vault.providerCap(PROVIDER), 5_000_000);
    }

    /// @dev Cap 0 = TANPA BATAS (bukan "diblokir"). Dikunci di sini supaya semantiknya tidak
    ///      diam-diam terbalik: menurunkan cap ke 0 justru MEMBUKA kunci provider.
    function test_setProviderCap_zeroMeansNoLimit() public {
        vm.prank(AGENT);
        vault.setProviderCap(PROVIDER, 5_000_000);
        vm.prank(AGENT);
        vault.setProviderCap(PROVIDER, 0);
        assertEq(vault.providerCap(PROVIDER), 0, "cap 0 = tanpa batas");
    }

    function test_setProviderCap_zeroProvider_reverts() public {
        vm.expectRevert(EvaluatorVault.ZeroAddress.selector);
        vm.prank(AGENT);
        vault.setProviderCap(address(0), 1);
    }

    function test_providerCap_defaultsToZero() public view {
        assertEq(vault.providerCap(PROVIDER), 0);
        assertEq(vault.providerCap(address(0)), 0);
    }

    // ------------------------------------------------------------------
    // postVerdict
    // ------------------------------------------------------------------

    function test_postVerdict_happy_emitsAndStores() public {
        uint256 jobId = _submittedJob();
        uint64 expectedReadyAt = uint64(block.timestamp) + vault.CHALLENGE_WINDOW();

        vm.expectEmit(true, false, false, true, address(vault));
        emit VerdictPosted(jobId, 1, REASON, ROOT_A, expectedReadyAt);
        vm.expectEmit(true, true, false, false, address(vault));
        emit MemoryRootUpdated(ROOT_A, jobId);
        vm.prank(AGENT);
        vault.postVerdict(jobId, 1, REASON, ROOT_A);

        (uint8 kind, bytes32 reasonHash, bytes32 memoryRoot, uint64 readyAt, bool finalized, address challenger) =
            vault.verdicts(jobId);
        assertEq(kind, 1);
        assertEq(reasonHash, REASON);
        assertEq(memoryRoot, ROOT_A);
        assertEq(readyAt, expectedReadyAt);
        assertFalse(finalized);
        assertEq(challenger, address(0));

        assertTrue(vault.knownRoots(ROOT_A), "root harus tercatat di knownRoots");
        assertEq(vault.lastMemoryRoot(), ROOT_A);
    }

    /// @dev `readyAt` = now + CHALLENGE_WINDOW, PERSIS. Mengunci mutan `readyAt = now`.
    function test_postVerdict_readyAtIsNowPlusWindow() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        assertEq(_readyAt(jobId), uint64(block.timestamp) + 120);
        assertGt(_readyAt(jobId), uint64(block.timestamp), "readyAt harus di masa depan");
    }

    /// @dev ADR-011 / task 1.2a (c).
    function test_postVerdict_zeroRoot_reverts() public {
        uint256 jobId = _submittedJob();
        vm.expectRevert(EvaluatorVault.ZeroMemoryRoot.selector);
        vm.prank(AGENT);
        vault.postVerdict(jobId, 1, REASON, bytes32(0));

        assertFalse(vault.knownRoots(bytes32(0)), "root nol tidak boleh pernah dikenal");
        assertEq(_readyAt(jobId), 0, "verdict tidak boleh tercatat");
    }

    function test_postVerdict_invalidKind_reverts() public {
        uint256 jobId = _submittedJob();
        vm.expectRevert(EvaluatorVault.InvalidKind.selector);
        vm.prank(AGENT);
        vault.postVerdict(jobId, 0, REASON, ROOT_A);

        vm.expectRevert(EvaluatorVault.InvalidKind.selector);
        vm.prank(AGENT);
        vault.postVerdict(jobId, 3, REASON, ROOT_A);
    }

    function test_postVerdict_twice_reverts() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        vm.expectRevert(EvaluatorVault.VerdictAlreadyPosted.selector);
        vm.prank(AGENT);
        vault.postVerdict(jobId, 2, REASON, ROOT_B);
    }

    /// @dev Bond evaluator = syarat mengeluarkan verdict (spec §4 `deposit()`).
    function test_postVerdict_withoutBond_reverts() public {
        EvaluatorVault bare = new EvaluatorVault(IACP(address(acp)), AGENT, ARBITER, MIN_BOND);
        uint256 jobId = _submittedJob();

        vm.expectRevert(EvaluatorVault.BondTooLow.selector);
        vm.prank(AGENT);
        bare.postVerdict(jobId, 1, REASON, ROOT_A);

        vm.prank(AGENT);
        bare.deposit{value: MIN_BOND - 1}();
        vm.expectRevert(EvaluatorVault.BondTooLow.selector);
        vm.prank(AGENT);
        bare.postVerdict(jobId, 1, REASON, ROOT_A);

        vm.prank(AGENT);
        bare.deposit{value: 1}();
        vm.prank(AGENT);
        bare.postVerdict(jobId, 1, REASON, ROOT_A);
        assertTrue(bare.knownRoots(ROOT_A));
    }

    // ------------------------------------------------------------------
    // finalize — happy path
    // ------------------------------------------------------------------

    /// @dev AC (g): argumen yang dikirim ke ACP di-assert, bukan cuma status akhir.
    function test_finalize_complete_happyPath() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        vm.warp(_readyAt(jobId));

        vm.expectCall(address(acp), abi.encodeCall(IACP.complete, (jobId, REASON, "")));
        vm.expectEmit(true, true, false, true, address(acp));
        emit JobCompleted(jobId, address(vault), REASON);
        vm.expectEmit(true, false, false, true, address(vault));
        emit Finalized(jobId, 1, REASON);
        vm.prank(STRANGER); // finalize permissionless
        vault.finalize(jobId);

        assertEq(_status(jobId), 3, "job harus Completed");
        assertTrue(_finalizedFlag(jobId));
        // 5% fee evaluator mendarat di vault, 1% platform, sisanya provider.
        assertEq(usdc.balanceOf(PROVIDER), 9_400_000);
        assertEq(usdc.balanceOf(address(vault)), 500_000);
        assertEq(usdc.balanceOf(TREASURY), 100_000);
    }

    function test_finalize_reject_happyPath() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 2, ROOT_B);
        vm.warp(_readyAt(jobId));

        uint256 clientBefore = usdc.balanceOf(CLIENT);
        vm.expectCall(address(acp), abi.encodeCall(IACP.reject, (jobId, REASON, "")));
        vm.expectEmit(true, true, false, true, address(acp));
        emit JobRejected(jobId, address(vault), REASON);
        vm.expectEmit(true, false, false, true, address(vault));
        emit Finalized(jobId, 2, REASON);
        vm.prank(STRANGER);
        vault.finalize(jobId);

        assertEq(_status(jobId), 4, "job harus Rejected");
        assertEq(usdc.balanceOf(CLIENT) - clientBefore, BUDGET, "refund 100% ke client");
        assertEq(usdc.balanceOf(PROVIDER), 0);
    }

    /// @dev ADR-001: gating memori = reject saat Funded (provider belum submit).
    function test_finalize_rejectWhileFunded_gatingMilestone() public {
        uint256 jobId = _fundedJob();
        _post(jobId, 2, ROOT_A);
        vm.warp(_readyAt(jobId));

        uint256 clientBefore = usdc.balanceOf(CLIENT);
        vm.prank(AGENT);
        vault.finalize(jobId);

        assertEq(_status(jobId), 4);
        assertEq(usdc.balanceOf(CLIENT) - clientBefore, BUDGET);
    }

    // ------------------------------------------------------------------
    // finalize — jalur revert
    // ------------------------------------------------------------------

    function test_finalize_beforeReadyAt_reverts() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);

        vm.expectRevert(EvaluatorVault.ChallengeWindowOpen.selector);
        vault.finalize(jobId);

        vm.warp(_readyAt(jobId) - 1);
        vm.expectRevert(EvaluatorVault.ChallengeWindowOpen.selector);
        vault.finalize(jobId);

        // Batas: TEPAT di readyAt sudah boleh.
        vm.warp(_readyAt(jobId));
        vault.finalize(jobId);
        assertEq(_status(jobId), 3);
    }

    function test_finalize_twice_reverts() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        vm.warp(_readyAt(jobId));
        vault.finalize(jobId);

        vm.expectRevert(EvaluatorVault.AlreadyFinalized.selector);
        vault.finalize(jobId);
    }

    function test_finalize_noVerdict_reverts() public {
        uint256 jobId = _submittedJob();
        vm.expectRevert(EvaluatorVault.NoVerdict.selector);
        vault.finalize(jobId);

        vm.expectRevert(EvaluatorVault.NoVerdict.selector);
        vault.finalize(999_999);
    }

    /// @dev ADR-011 / task 1.2a (b). Root yang TIDAK pernah diumumkan lewat `postVerdict` tidak boleh
    ///      bisa dieksekusi. Karena `postVerdict` selalu mendaftarkan root (dan tidak ada penghapus),
    ///      satu-satunya cara membuat keadaan ini adalah menulis storage langsung.
    function test_finalize_unknownRoot_reverts() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);

        bytes32 unknownRoot = keccak256("root yang tidak pernah diumumkan");
        bytes32 base = keccak256(abi.encode(jobId, VERDICTS_SLOT));
        vm.store(address(vault), bytes32(uint256(base) + 2), unknownRoot);

        // Verifikasi asumsi layout: HANYA memoryRoot yang berubah.
        (uint8 kind, bytes32 reasonHash, bytes32 memoryRoot, uint64 readyAt, bool finalized,) = vault.verdicts(jobId);
        assertEq(memoryRoot, unknownRoot, "slot verdicts salah: perbarui VERDICTS_SLOT");
        assertEq(kind, 1);
        assertEq(reasonHash, REASON);
        assertEq(readyAt, uint64(block.timestamp) + 120);
        assertFalse(finalized);
        assertFalse(vault.knownRoots(unknownRoot));

        vm.warp(readyAt);
        vm.expectRevert(EvaluatorVault.UnknownMemoryRoot.selector);
        vault.finalize(jobId);
        assertEq(_status(jobId), 2, "job harus tetap Submitted");
    }

    // ------------------------------------------------------------------
    // 1.2a / ADR-011 — verdict lama tetap bisa difinalisasi
    // ------------------------------------------------------------------

    /// @dev Task 1.2a (a). Inti ADR-011: root berubah tiap `postVerdict`, jadi syarat
    ///      `memoryRoot == lastMemoryRoot` akan mengunci verdict A selamanya. Di sini KETIGA verdict
    ///      difinalisasi SETELAH root yang lebih baru diumumkan.
    function test_finalize_afterNewerVerdict_stillWorks() public {
        uint256 jobA = _submittedJob();
        uint256 jobB = _submittedJob();
        uint256 jobC = _submittedJob();

        _post(jobA, 1, ROOT_A);
        _post(jobB, 2, ROOT_B);
        _post(jobC, 1, ROOT_C);

        assertEq(vault.lastMemoryRoot(), ROOT_C, "lastMemoryRoot = root TERBARU");
        assertTrue(vault.knownRoots(ROOT_A));
        assertTrue(vault.knownRoots(ROOT_B));
        assertTrue(vault.knownRoots(ROOT_C));

        vm.warp(_readyAt(jobC));

        vault.finalize(jobA); // root A sudah "basi" — tetap harus jalan
        assertEq(_status(jobA), 3);
        vault.finalize(jobB);
        assertEq(_status(jobB), 4);
        vault.finalize(jobC);
        assertEq(_status(jobC), 3);

        assertEq(vault.lastMemoryRoot(), ROOT_C, "finalize tidak mengubah lastMemoryRoot");
    }

    /// @dev Root yang sama boleh dipakai ulang oleh verdict berikutnya (memori tidak berubah).
    function test_postVerdict_sameRootTwice_isAllowed() public {
        uint256 jobA = _submittedJob();
        uint256 jobB = _submittedJob();
        _post(jobA, 1, ROOT_A);
        _post(jobB, 1, ROOT_A);
        vm.warp(_readyAt(jobB));
        vault.finalize(jobA);
        vault.finalize(jobB);
        assertEq(_status(jobA), 3);
        assertEq(_status(jobB), 3);
    }

    // ------------------------------------------------------------------
    // R1 — verdict yatim (griefing claimRefund). Vault tidak boleh terkunci.
    // ------------------------------------------------------------------

    /// @dev AC (d). Varian **Submitted**: `claimRefund` sah dari Submitted pada `expiredAt + 900`
    ///      (api-facts §A, bisection fork). Sesudahnya `complete` PASTI revert `WrongStatus`.
    function test_A3_submittedGrace() public {
        uint256 jobId = _submittedJob();
        uint48 expiredAt = acp.getJob(jobId).expiredAt;
        _post(jobId, 1, ROOT_A);

        vm.warp(uint256(expiredAt) + acp.EVALUATOR_GRACE_PERIOD());
        vm.prank(STRANGER);
        acp.claimRefund(jobId);
        assertEq(_status(jobId), 5, "job harus Expired");

        // finalize TIDAK boleh revert dan TIDAK boleh mengunci vault.
        vm.expectEmit(true, false, false, false, address(vault));
        emit FinalizeFailed(jobId);
        vm.prank(STRANGER);
        vault.finalize(jobId);

        // ADR-015: kegagalan TIDAK menggugurkan verdict.
        assertFalse(_finalizedFlag(jobId), "verdict harus tetap hidup");
        assertEq(_status(jobId), 5, "status ACP tidak berubah");
        assertEq(usdc.balanceOf(CLIENT), 1_000_000_000, "client menerima refund penuh");
        assertEq(usdc.balanceOf(PROVIDER), 0);

        // Percobaan KEDUA tetap tidak revert (dan tetap tidak menutup verdict).
        vm.expectEmit(true, false, false, false, address(vault));
        emit FinalizeFailed(jobId);
        vm.prank(CHALLENGER);
        vault.finalize(jobId);
        assertFalse(_finalizedFlag(jobId), "percobaan kedua juga tidak boleh menutup verdict");

        uint256 next = _submittedJob();
        _post(next, 1, ROOT_B);
        vm.warp(_readyAt(next));
        vault.finalize(next);
        assertEq(_status(next), 3, "vault tidak terkunci");
    }

    /// @dev Varian TAMBAHAN (bukan pengganti): dari Funded tidak ada tenggang sama sekali.
    function test_A3_fundedNoGrace() public {
        uint256 jobId = _fundedJob();
        uint48 expiredAt = acp.getJob(jobId).expiredAt;
        _post(jobId, 2, ROOT_A);

        vm.warp(uint256(expiredAt));
        vm.prank(STRANGER);
        acp.claimRefund(jobId);
        assertEq(_status(jobId), 5);

        vm.expectEmit(true, false, false, false, address(vault));
        emit FinalizeFailed(jobId);
        vault.finalize(jobId);
        assertFalse(_finalizedFlag(jobId), "kegagalan ACP tidak menutup verdict (ADR-015)");

        // Diulang: tetap tidak revert.
        vault.finalize(jobId);
        assertFalse(_finalizedFlag(jobId));
    }

    function _isFinalized(EvaluatorVault v, uint256 jobId) internal view returns (bool finalized) {
        (,,,, finalized,) = v.verdicts(jobId);
    }

    // ------------------------------------------------------------------
    // 1.2b — penjaga gas ABSOLUT di topologi ACP nyata (ADR-015)
    // ------------------------------------------------------------------

    /// @dev AC 1.2b (a). Rentang 74.500–86.500 adalah pita yang DIBUKTIKAN bocor oleh penjaga RASIO
    ///      lama (`gasleft() < gasBefore / 32` di dalam `catch`): pada kedalaman 3 sisa gas saat OOG
    ///      ~46‰, jauh di atas ambang 31,25‰, sehingga 25 dari 51 sampel menggugurkan verdict SEHAT.
    ///      Dengan `require(gasleft() >= MIN_ACP_GAS)` SEBELUM `try`, seluruh pita itu WAJIB revert
    ///      bersih — nol `FinalizeFailed`, nol perubahan state — dan `finalize` ulang dengan gas
    ///      cukup WAJIB sukses. Mutan `MIN_ACP_GAS = 0` membuat tes ini merah.
    function test_finalize_gasSweep_leakBandRevertsCleanly() public {
        bytes32 finalizeFailedTopic = keccak256("FinalizeFailed(uint256)");
        uint256 voided = 0;

        for (uint256 i = 0; i < 51; i++) {
            uint256 gasLimit = 74_500 + i * 240; // 74.500 … 86.500, 51 sampel
            uint256 jobId = _submittedJob();
            _post(jobId, 1, ROOT_A);
            vm.warp(_readyAt(jobId));

            vm.recordLogs();
            vm.prank(STRANGER);
            (bool ok,) = address(vault).call{gas: gasLimit}(abi.encodeCall(EvaluatorVault.finalize, (jobId)));
            Vm.Log[] memory logs = vm.getRecordedLogs();
            for (uint256 j = 0; j < logs.length; j++) {
                if (logs[j].topics[0] == finalizeFailedTopic) voided++;
            }

            assertFalse(ok, "gas di pita bocor harus REVERT, bukan sukses dengan FinalizeFailed");
            assertFalse(_finalizedFlag(jobId), "verdict harus utuh");
            assertEq(_status(jobId), 2, "job harus tetap Submitted");

            // Percobaan ulang dengan gas cukup: SUKSES, provider dibayar.
            vault.finalize(jobId);
            assertTrue(_finalizedFlag(jobId), "finalize ulang harus menutup verdict");
            assertEq(_status(jobId), 3, "job harus Completed");
        }

        assertEq(voided, 0, "tidak boleh ada satu pun FinalizeFailed di pita 74.500-86.500");
        assertEq(usdc.balanceOf(PROVIDER), 51 * 9_400_000, "51 provider payout penuh");
    }

    /// @dev Batas ambang diuji di titiknya, bukan di sekitarnya. `MIN_ACP_GAS` diukur dari `gasleft()`
    ///      DI DALAM `finalize`, jadi gas yang harus diberikan pemanggil = ambang + biaya cek awal;
    ///      yang dikunci di sini adalah SIFATNYA: ada satu titik potong, di bawahnya revert
    ///      `InsufficientGasForAcpCall`, di atasnya sukses.
    function test_finalize_gasThreshold_isAbsoluteNotRatio() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        vm.warp(_readyAt(jobId));

        // Tepat MIN_ACP_GAS sebagai gas limit: cek awal sudah memakan sebagian, jadi PASTI kurang.
        (bool ok, bytes memory ret) =
            address(vault).call{gas: vault.MIN_ACP_GAS()}(abi.encodeCall(EvaluatorVault.finalize, (jobId)));
        assertFalse(ok);
        assertEq(bytes4(ret), EvaluatorVault.InsufficientGasForAcpCall.selector, "harus revert eksplisit, bukan OOG");
        assertFalse(_finalizedFlag(jobId));

        // Cukup longgar: sukses.
        (ok,) =
            address(vault).call{gas: vault.MIN_ACP_GAS() + 100_000}(abi.encodeCall(EvaluatorVault.finalize, (jobId)));
        assertTrue(ok);
        assertTrue(_finalizedFlag(jobId));
        assertEq(_status(jobId), 3);
    }

    /// @dev AC 1.2b (b). ACP nyata `Pausable` (api-facts §A: saat paused `complete`/`claimRefund`
    ///      revert `EnforcedPause()`). Di sini implementasi di balik proxy ditukar ke `PausedACPImpl`.
    ///      Yang dikunci: kegagalan TEMPORER tidak boleh membakar verdict — sesudah `unpause`,
    ///      `finalize` ulang harus SUKSES dan provider dibayar PENUH.
    function test_finalize_acpPaused_thenUnpaused_paysProviderInFull() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        vm.warp(_readyAt(jobId));

        _pauseAcp();
        vm.expectEmit(true, false, false, false, address(vault));
        emit FinalizeFailed(jobId);
        vm.prank(STRANGER);
        vault.finalize(jobId);
        assertFalse(_finalizedFlag(jobId), "ACP dipause TIDAK boleh menutup verdict");
        assertEq(usdc.balanceOf(PROVIDER), 0, "belum ada pembayaran saat paused");

        _unpauseAcp();
        assertEq(_status(jobId), 2, "state job utuh sesudah unpause");

        vm.expectEmit(true, true, false, true, address(acp));
        emit JobCompleted(jobId, address(vault), REASON);
        vm.expectEmit(true, false, false, true, address(vault));
        emit Finalized(jobId, 1, REASON);
        vm.prank(STRANGER);
        vault.finalize(jobId);

        assertTrue(_finalizedFlag(jobId));
        assertEq(_status(jobId), 3, "job harus Completed");
        assertEq(usdc.balanceOf(PROVIDER), 9_400_000, "provider dibayar PENUH");
        assertEq(usdc.balanceOf(address(vault)), 500_000);
        assertEq(usdc.balanceOf(TREASURY), 100_000);

        // Sesudah benar-benar tereksekusi, percobaan berikutnya baru ditutup.
        vm.expectRevert(EvaluatorVault.AlreadyFinalized.selector);
        vault.finalize(jobId);
    }

    /// @dev Sisi lain dari ambang gas: bahkan ketika callee membakar SELURUH gas yang diteruskan,
    ///      `catch` tidak boleh menutup verdict. Ini yang membuat ambang gas berlapis, bukan tunggal.
    function test_finalize_acpBurnsAllGas_doesNotCloseVerdict() public {
        EvaluatorVault burnerVault = new EvaluatorVault(IACP(address(new GasBurnerACP())), AGENT, ARBITER, 0);
        uint256 jobId = 1;
        vm.prank(AGENT);
        burnerVault.postVerdict(jobId, 1, REASON, ROOT_A);
        vm.warp(block.timestamp + 120);

        vm.prank(STRANGER);
        (bool ok,) = address(burnerVault).call{gas: 2_000_000}(abi.encodeCall(EvaluatorVault.finalize, (jobId)));
        assertTrue(ok, "kegagalan ACP tidak merevert finalize");
        assertFalse(_isFinalized(burnerVault, jobId), "verdict harus tetap hidup");

        // Gas tipis: ditolak SEBELUM `try`, jadi tidak ada pembakaran gas sama sekali.
        (bool ok2, bytes memory ret) =
            address(burnerVault).call{gas: 100_000}(abi.encodeCall(EvaluatorVault.finalize, (jobId)));
        assertFalse(ok2);
        assertEq(bytes4(ret), EvaluatorVault.InsufficientGasForAcpCall.selector);
        assertFalse(_isFinalized(burnerVault, jobId));
    }

    /// @dev Mengunci TURUNAN angka `MIN_ACP_GAS` ke pengukuran (ADR-015): >= 3x biaya `complete`
    ///      berbudget nyata yang diukur dari posisi vault, di belakang `ERC1967Proxy`, dengan slot
    ///      saldo ERC-20 penerima masih dingin.
    function test_minAcpGas_isAtLeastThreeTimesMeasuredCost() public {
        MeasuringEvaluator ev = new MeasuringEvaluator();
        vm.prank(CLIENT);
        uint256 jobId = acp.createJob(PROVIDER, address(ev), block.timestamp + 1 hours, "ukur gas", address(0));
        vm.prank(PROVIDER);
        acp.setBudget(jobId, BUDGET, "");
        vm.prank(CLIENT);
        acp.fund(jobId, BUDGET, "");
        vm.prank(PROVIDER);
        acp.submit(jobId, DELIVERABLE, "");

        ev.doComplete(address(acp), jobId, REASON);
        uint256 measured = ev.lastGas();

        assertGt(measured, 60_000, "pengukuran terlalu murah: slot penerima pasti sudah hangat");
        assertGe(vault.MIN_ACP_GAS(), 3 * measured, "MIN_ACP_GAS harus >= 3x biaya complete terukur");
        assertLe(vault.MIN_ACP_GAS(), 3 * measured + 25_000, "ambang dibulatkan ke 25k, bukan dikarang besar");
        assertEq(usdc.balanceOf(PROVIDER), 9_400_000);
    }

    // ------------------------------------------------------------------
    // challenge / resolve — stub ADR-013
    // ------------------------------------------------------------------

    /// @dev AC (f): siapa pun, dengan DAN tanpa `msg.value`; ETH harus kembali utuh.
    function test_challenge_reverts() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        bytes32 counter = keccak256("bukti tandingan");

        address[4] memory who = [AGENT, ARBITER, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            uint256 balBefore = who[i].balance;

            vm.expectRevert(EvaluatorVault.NotImplemented.selector);
            vm.prank(who[i]);
            vault.challenge(jobId, counter);

            vm.expectRevert(EvaluatorVault.NotImplemented.selector);
            vm.prank(who[i]);
            vault.challenge{value: 1 ether}(jobId, counter);

            assertEq(who[i].balance, balBefore, "ETH penantang harus kembali utuh");
        }
        assertEq(address(vault).balance, MIN_BOND, "vault tidak boleh menahan bond penantang");
    }

    function test_resolve_arbiter_reverts_notImplemented() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        vm.expectRevert(EvaluatorVault.NotImplemented.selector);
        vm.prank(ARBITER);
        vault.resolve(jobId, true);

        vm.expectRevert(EvaluatorVault.NotImplemented.selector);
        vm.prank(ARBITER);
        vault.resolve(jobId, false);
    }

    /// @dev Cek peran dijalankan SEBELUM revert stub: permukaan otorisasi terkunci sejak sekarang.
    function test_resolve_stranger_reverts_unauthorized() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);

        address[3] memory who = [AGENT, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            vm.expectRevert(EvaluatorVault.NotArbiter.selector);
            vm.prank(who[i]);
            vault.resolve(jobId, true);
        }
    }

    // ------------------------------------------------------------------
    // Matriks otorisasi PER-PERAN (AC e)
    // ------------------------------------------------------------------

    /// @dev ADR-015 mengubah baris ini: `deposit` dulu TERBUKA untuk semua peran (spec §4 memang
    ///      tidak memberinya modifier), sekarang `onlyAgent` karena belum ada jalur ETH keluar.
    function test_authMatrix_deposit_onlyAgent() public {
        address[3] memory who = [ARBITER, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            uint256 balBefore = who[i].balance;
            vm.expectRevert(EvaluatorVault.NotAgent.selector);
            vm.prank(who[i]);
            vault.deposit{value: 1 ether}();
            assertEq(who[i].balance, balBefore);
        }
        assertEq(vault.bond(), MIN_BOND, "tidak satu pun setoran asing masuk");

        vm.prank(AGENT);
        vault.deposit{value: 1 wei}();
        assertEq(vault.bond(), MIN_BOND + 1);
    }

    function test_authMatrix_setProviderCap_onlyAgent() public {
        address[3] memory who = [ARBITER, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            vm.expectRevert(EvaluatorVault.NotAgent.selector);
            vm.prank(who[i]);
            vault.setProviderCap(PROVIDER, 1);
        }
        vm.prank(AGENT);
        vault.setProviderCap(PROVIDER, 1);
        assertEq(vault.providerCap(PROVIDER), 1);
    }

    function test_authMatrix_postVerdict_onlyAgent() public {
        uint256 jobId = _submittedJob();
        address[3] memory who = [ARBITER, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            vm.expectRevert(EvaluatorVault.NotAgent.selector);
            vm.prank(who[i]);
            vault.postVerdict(jobId, 1, REASON, ROOT_A);
        }
        assertFalse(vault.knownRoots(ROOT_A));
        vm.prank(AGENT);
        vault.postVerdict(jobId, 1, REASON, ROOT_A);
        assertTrue(vault.knownRoots(ROOT_A));
    }

    function test_authMatrix_challenge_allRolesRevert() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        address[4] memory who = [AGENT, ARBITER, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            vm.expectRevert(EvaluatorVault.NotImplemented.selector);
            vm.prank(who[i]);
            vault.challenge(jobId, bytes32(0));
        }
    }

    function test_authMatrix_resolve_onlyArbiterReachesStub() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);

        address[3] memory who = [AGENT, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            vm.expectRevert(EvaluatorVault.NotArbiter.selector);
            vm.prank(who[i]);
            vault.resolve(jobId, true);
        }
        vm.expectRevert(EvaluatorVault.NotImplemented.selector);
        vm.prank(ARBITER);
        vault.resolve(jobId, true);
    }

    /// @dev `finalize` memang permissionless (spec §4 "siapa pun"): keempat peran berhasil.
    function test_authMatrix_finalize_openToAllRoles() public {
        address[4] memory who = [AGENT, ARBITER, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            uint256 jobId = _submittedJob();
            _post(jobId, 1, i == 0 ? ROOT_A : i == 1 ? ROOT_B : ROOT_C);
            vm.warp(_readyAt(jobId));
            vm.prank(who[i]);
            vault.finalize(jobId);
            assertEq(_status(jobId), 3);
        }
    }

    // ------------------------------------------------------------------
    // sweepToken — jalan keluar fee evaluator (task 1.2c)
    // ------------------------------------------------------------------

    /// @dev Jalur yang menjadi SEBAB fungsi ini ada: job Completed mengirim 5% budget ke vault
    ///      (job 417 di Base Sepolia: 50.000 unit), dan sebelum `sweepToken` tidak ada jalan keluar.
    function test_sweepToken_arbiter_withdrawsFull() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        vm.warp(_readyAt(jobId));
        vault.finalize(jobId);

        uint256 fee = (BUDGET * 500) / 10_000;
        assertEq(usdc.balanceOf(address(vault)), fee, "prasyarat: fee evaluator ada di vault");
        uint256 beforeBal = usdc.balanceOf(TREASURY);

        vm.expectEmit(true, true, false, true, address(vault));
        emit TokenSwept(address(usdc), TREASURY, fee);
        vm.prank(ARBITER);
        uint256 swept = vault.sweepToken(address(usdc), TREASURY);

        assertEq(swept, fee, "return value = jumlah yang dipindahkan");
        assertEq(usdc.balanceOf(address(vault)), 0, "vault harus kosong");
        assertEq(usdc.balanceOf(TREASURY) - beforeBal, fee, "penerima menerima penuh");
    }

    /// @dev Matriks per-peran: siapa pun selain arbiter ditolak, dan saldo TIDAK bergerak sedikit pun.
    function test_sweepToken_nonArbiter_reverts() public {
        usdc.mint(address(vault), 500_000);

        address[3] memory who = [AGENT, CHALLENGER, STRANGER];
        for (uint256 i = 0; i < who.length; i++) {
            vm.expectRevert(EvaluatorVault.NotArbiter.selector);
            vm.prank(who[i]);
            vault.sweepToken(address(usdc), who[i]);
            assertEq(usdc.balanceOf(address(vault)), 500_000, "saldo vault tidak boleh bergerak");
            assertEq(usdc.balanceOf(who[i]), 0, "pemanggil non-arbiter tidak menerima apa pun");
        }

        // Kontrol positif: token yang sama BISA keluar, jadi kegagalan di atas benar karena peran.
        vm.prank(ARBITER);
        vault.sweepToken(address(usdc), TREASURY);
        assertEq(usdc.balanceOf(address(vault)), 0);
    }

    function test_sweepToken_zeroRecipientReverts() public {
        usdc.mint(address(vault), 1);
        vm.expectRevert(EvaluatorVault.ZeroAddress.selector);
        vm.prank(ARBITER);
        vault.sweepToken(address(usdc), address(0));
    }

    function test_sweepToken_toVaultItselfReverts() public {
        usdc.mint(address(vault), 1);
        vm.expectRevert(EvaluatorVault.ZeroAddress.selector);
        vm.prank(ARBITER);
        vault.sweepToken(address(usdc), address(vault));
    }

    function test_sweepToken_nothingToSweepReverts() public {
        assertEq(usdc.balanceOf(address(vault)), 0);
        vm.expectRevert(EvaluatorVault.NothingToSweep.selector);
        vm.prank(ARBITER);
        vault.sweepToken(address(usdc), TREASURY);
    }

    /// @dev Alamat tanpa kode (salah ketik / EOA): ditolak dengan error bernama, bukan revert kosong.
    function test_sweepToken_tokenWithoutCodeReverts() public {
        vm.expectRevert(EvaluatorVault.TokenNotContract.selector);
        vm.prank(ARBITER);
        vault.sweepToken(STRANGER, TREASURY);
    }

    /// @dev ETH bond TIDAK boleh punya jalur keluar (ADR-013): `sweepToken` hanya memindahkan ERC-20.
    function test_sweepToken_doesNotTouchEthBond() public {
        usdc.mint(address(vault), 250_000);
        uint256 bondBefore = vault.bond();
        uint256 ethBefore = address(vault).balance;
        assertEq(bondBefore, MIN_BOND);
        assertEq(ethBefore, MIN_BOND);

        vm.prank(ARBITER);
        vault.sweepToken(address(usdc), ARBITER);

        assertEq(vault.bond(), bondBefore, "bond tidak boleh berubah");
        assertEq(address(vault).balance, ethBefore, "saldo ETH vault tidak boleh berubah");
        assertEq(usdc.balanceOf(ARBITER), 250_000);
    }

    /// @dev Token yang mengembalikan `false` alih-alih revert: tanpa `SafeERC20` sapuan akan tampak
    ///      SUKSES padahal tidak ada yang pindah. Harus revert.
    function test_sweepToken_falseReturningTokenReverts() public {
        FalseReturningToken bad = new FalseReturningToken();
        bad.mint(address(vault), 1_000);

        vm.expectRevert(abi.encodeWithSignature("SafeERC20FailedOperation(address)", address(bad)));
        vm.prank(ARBITER);
        vault.sweepToken(address(bad), TREASURY);

        assertEq(bad.balanceOf(address(vault)), 1_000, "saldo tetap di vault");
    }

    /// @dev Token gaya USDT tanpa nilai balik tetap harus bisa disapu.
    function test_sweepToken_noReturnValueTokenSucceeds() public {
        NoReturnToken quirky = new NoReturnToken();
        quirky.mint(address(vault), 7_777);

        vm.prank(ARBITER);
        uint256 swept = vault.sweepToken(address(quirky), TREASURY);

        assertEq(swept, 7_777);
        assertEq(quirky.balanceOf(address(vault)), 0);
        assertEq(quirky.balanceOf(TREASURY), 7_777);
    }

    /// @dev Token dengan hook yang memanggil balik vault dari DALAM `transfer`. Jalur masuk-ulang
    ///      yang nyata adalah `finalize` (permissionless): ia ditolak `nonReentrant`. `sweepToken`
    ///      sendiri ditolak lebih dulu oleh `onlyArbiter`. Sapuan luar tetap tuntas satu kali.
    function test_sweepToken_reentrantTokenIsRejected() public {
        uint256 jobId = _submittedJob();
        _post(jobId, 1, ROOT_A);
        vm.warp(_readyAt(jobId));

        ReentrantToken evil = new ReentrantToken();
        evil.mint(address(vault), 3_000);
        evil.arm(vault, TREASURY, jobId);

        vm.prank(ARBITER);
        vault.sweepToken(address(evil), TREASURY);

        assertTrue(evil.reentered(), "hook token harus benar-benar dieksekusi");
        assertEq(
            bytes4(evil.finalizeRevertData()),
            bytes4(keccak256("ReentrancyGuardReentrantCall()")),
            "finalize masuk-ulang harus ditolak guard transient"
        );
        assertEq(bytes4(evil.sweepRevertData()), EvaluatorVault.NotArbiter.selector, "sweep masuk-ulang ditolak peran");
        assertEq(evil.balanceOf(address(vault)), 0);
        assertEq(evil.balanceOf(TREASURY), 3_000);
        assertFalse(_finalizedFlag(jobId), "verdict tetap terbuka: masuk-ulang tidak mengeksekusi apa pun");

        // Sesudah sapuan selesai, finalize normal tetap jalan.
        vault.finalize(jobId);
        assertTrue(_finalizedFlag(jobId));
    }

    /// @dev Sapuan berulang: setiap job Completed menambah fee baru, dan tiap kali bisa dikeluarkan.
    function test_sweepToken_repeatedSweepsAfterMoreJobs() public {
        uint256 fee = (BUDGET * 500) / 10_000;
        bytes32[3] memory roots = [ROOT_A, ROOT_B, ROOT_C];
        for (uint256 i = 0; i < roots.length; i++) {
            uint256 jobId = _submittedJob();
            _post(jobId, 1, roots[i]);
            vm.warp(_readyAt(jobId));
            vault.finalize(jobId);

            assertEq(usdc.balanceOf(address(vault)), fee);
            vm.prank(ARBITER);
            assertEq(vault.sweepToken(address(usdc), TREASURY), fee);
            assertEq(usdc.balanceOf(address(vault)), 0);
        }
    }
}
