// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Test, Vm} from "forge-std/Test.sol";
import {AgenticCommerce} from "./mocks/AgenticCommerce.sol";

/// @dev ERC-20 6 desimal (salinan perilaku `MockUSDC`) yang MENGINTIP status job setiap kali ACP
///      memindahkan token keluar. Gunanya satu: mengunci urutan Checks-Effects-Interactions di mock.
///      `job.status` WAJIB sudah berpindah ke status akhir SEBELUM transfer keluar pertama, karena di
///      ACP nyata setiap fungsi alur job memegang kunci transient bersama dan satu-satunya pihak yang
///      bisa "melihat" state di tengah pembayaran adalah kontrak token itu sendiri.
///      Token ini TIDAK memanggil balik ACP — jalur itu diuji terpisah di `HookReentrancy.t.sol`.
contract ObservingUSDC {
    string public constant name = "Observing USD Coin";
    string public constant symbol = "USDC";
    uint8 public constant decimals = 6;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    error InsufficientBalance();
    error InsufficientAllowance();

    AgenticCommerce public acp;
    uint256 public watchedJobId;
    uint8[] internal observed;

    function watch(AgenticCommerce acp_, uint256 jobId) external {
        acp = acp_;
        watchedJobId = jobId;
        delete observed;
    }

    function observations() external view returns (uint8[] memory) {
        return observed;
    }

    function mint(address to, uint256 amount) external {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _observe();
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            if (allowed < amount) revert InsufficientAllowance();
            allowance[from][msg.sender] = allowed - amount;
        }
        _transfer(from, to, amount);
        return true;
    }

    function _observe() private {
        if (address(acp) == address(0) || watchedJobId == 0) return;
        if (msg.sender != address(acp)) return;
        observed.push(uint8(acp.getJob(watchedJobId).status));
    }

    function _transfer(address from, address to, uint256 amount) private {
        uint256 bal = balanceOf[from];
        if (bal < amount) revert InsufficientBalance();
        unchecked {
            balanceOf[from] = bal - amount;
        }
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}

/// @title FundConservationTest — invariant aliran dana escrow pada mock ACP (task 1.2d).
/// @notice Yang dibuktikan: token yang MASUK ke ACP = payout provider + evaluatorFee + platformFee +
///         refund, di SEMUA jalur akhir (Completed, auto-complete, Rejected, Expired lewat
///         `claimRefund`). Tidak ada satu wei pun yang hilang, tercipta, atau tertinggal di ACP.
/// @dev Jangkar realitas = job ACP 417 di Base Sepolia (`deployments/pipeline-84532.md`): budget
///      1.000.000 → provider 940.000 + evaluator 50.000 + platform 10.000, diukur dari `balanceOf`
///      sesudah `finalize`. `test_conservation_completed_matchesLivePipelineNumbers` menyalin angka
///      itu apa adanya; kalau mock tidak mereproduksinya, MOCK yang salah.
contract FundConservationTest is Test {
    AgenticCommerce internal acp;
    ObservingUSDC internal usdc;

    address internal constant CLIENT = address(0xC11E);
    address internal constant PROVIDER = address(0x9401);
    address internal constant EVALUATOR = address(0xE0A1);
    address internal constant TREASURY = address(0x77EA);
    address internal constant STRANGER = address(0x5748);

    bytes32 internal constant DELIVERABLE = keccak256("deliverable");
    bytes32 internal constant REASON = keccak256("bundel bukti");

    /// @dev Batas atas fuzz: jauh di atas budget nyata (1 USDC) tapi tetap jauh dari overflow
    ///      `budget * bp`. Batas bawahnya 0, karena budget nol adalah jalur NYATA (`fund(id, 0, "")`).
    uint256 internal constant MAX_BUDGET = 1e24;

    function setUp() public {
        vm.warp(1_000_000);
        usdc = new ObservingUSDC();
        acp = new AgenticCommerce(address(usdc), TREASURY);

        usdc.mint(CLIENT, type(uint128).max);
        vm.prank(CLIENT);
        usdc.approve(address(acp), type(uint256).max);
    }

    // ------------------------------------------------------------------
    // Helper
    // ------------------------------------------------------------------

    struct Ledger {
        uint256 client;
        uint256 provider;
        uint256 evaluator;
        uint256 treasury;
        uint256 acp;
        uint256 totalSupply;
    }

    function _ledger() internal view returns (Ledger memory l) {
        l.client = usdc.balanceOf(CLIENT);
        l.provider = usdc.balanceOf(PROVIDER);
        l.evaluator = usdc.balanceOf(EVALUATOR);
        l.treasury = usdc.balanceOf(TREASURY);
        l.acp = usdc.balanceOf(address(acp));
        l.totalSupply = usdc.totalSupply();
    }

    /// @dev Inti task 1.2d. `inflow` = token yang benar-benar ditarik ACP dari client saat `fund`.
    ///      Persamaan yang diuji: inflow = payout + evaluatorFee + platformFee + refund, DAN escrow
    ///      kembali persis ke saldo semula (tidak ada wei nyangkut), DAN total supply tidak berubah.
    function _assertConservation(Ledger memory before, uint256 inflow) internal view returns (Ledger memory nowL) {
        nowL = _ledger();

        uint256 payout = nowL.provider - before.provider;
        uint256 evaluatorFee = nowL.evaluator - before.evaluator;
        uint256 platformFee = nowL.treasury - before.treasury;
        // Client mengeluarkan `inflow` dan mungkin menerima refund.
        uint256 refund = nowL.client + inflow - before.client;

        assertEq(payout + evaluatorFee + platformFee + refund, inflow, "masuk != payout+evalFee+platformFee+refund");
        assertEq(nowL.acp, before.acp, "escrow ACP harus kembali ke saldo semula (tidak ada wei nyangkut)");
        assertEq(nowL.totalSupply, before.totalSupply, "tidak ada token tercipta/hilang");
    }

    function _createJob(address evaluator_) internal returns (uint256 jobId) {
        vm.prank(CLIENT);
        jobId = acp.createJob(PROVIDER, evaluator_, block.timestamp + 1 hours, "job", address(0));
    }

    function _fundedJob(address evaluator_, uint256 budget) internal returns (uint256 jobId) {
        jobId = _createJob(evaluator_);
        vm.prank(PROVIDER);
        acp.setBudget(jobId, budget, "");
        vm.prank(CLIENT);
        acp.fund(jobId, budget, "");
    }

    function _submittedJob(address evaluator_, uint256 budget) internal returns (uint256 jobId) {
        jobId = _fundedJob(evaluator_, budget);
        vm.prank(PROVIDER);
        acp.submit(jobId, DELIVERABLE, "");
    }

    function _expectedFees(uint256 budget) internal view returns (uint256 evaluatorFee, uint256 platformFee) {
        evaluatorFee = (budget * acp.evaluatorFeeBP()) / 10_000;
        platformFee = (budget * acp.platformFeeBP()) / 10_000;
    }

    // ------------------------------------------------------------------
    // Jangkar realitas: job ACP 417 (Base Sepolia)
    // ------------------------------------------------------------------

    /// @dev `deployments/pipeline-84532.md`: budget 1.000.000 → provider 940.000, vault/evaluator
    ///      50.000 (`evaluatorFeeBP()` = 500), platform 10.000 (`platformFeeBP()` = 100). Angka ini
    ///      TIDAK boleh disesuaikan ke mock; mock yang harus mereproduksinya.
    function test_conservation_completed_matchesLivePipelineNumbers() public {
        assertEq(acp.evaluatorFeeBP(), 500, "evaluatorFeeBP mock != nilai on-chain 500");
        assertEq(acp.platformFeeBP(), 100, "platformFeeBP mock != nilai on-chain 100");

        uint256 budget = 1_000_000; // 1 USDC, budget job 417
        Ledger memory before = _ledger();
        uint256 jobId = _submittedJob(EVALUATOR, budget);

        vm.prank(EVALUATOR);
        acp.complete(jobId, REASON, "");

        Ledger memory nowL = _assertConservation(before, budget);
        assertEq(nowL.provider - before.provider, 940_000, "payout provider job 417");
        assertEq(nowL.evaluator - before.evaluator, 50_000, "evaluatorFee job 417");
        assertEq(nowL.treasury - before.treasury, 10_000, "platformFee job 417");
        assertEq(uint8(acp.getJob(jobId).status), 3, "status akhir Completed");
    }

    // ------------------------------------------------------------------
    // Konservasi per jalur akhir (fuzz atas budget sembarang)
    // ------------------------------------------------------------------

    function testFuzz_conservation_completed(uint256 budget) public {
        budget = bound(budget, 0, MAX_BUDGET);
        Ledger memory before = _ledger();
        uint256 jobId = _submittedJob(EVALUATOR, budget);

        vm.prank(EVALUATOR);
        acp.complete(jobId, REASON, "");

        Ledger memory nowL = _assertConservation(before, budget);
        (uint256 evaluatorFee, uint256 platformFee) = _expectedFees(budget);
        assertEq(nowL.evaluator - before.evaluator, evaluatorFee, "evaluatorFee");
        assertEq(nowL.treasury - before.treasury, platformFee, "platformFee");
        assertEq(nowL.provider - before.provider, budget - evaluatorFee - platformFee, "payout = sisa, tanpa dust");
        assertEq(nowL.client, before.client - budget, "client tidak menerima apa pun di jalur Completed");
        assertEq(uint8(acp.getJob(jobId).status), 3, "Completed");
    }

    /// @dev `evaluator == address(0)`: `submit` langsung menyelesaikan job, fee evaluator NOL.
    function testFuzz_conservation_autoCompleted(uint256 budget) public {
        budget = bound(budget, 0, MAX_BUDGET);
        Ledger memory before = _ledger();
        uint256 jobId = _fundedJob(address(0), budget);

        vm.prank(PROVIDER);
        acp.submit(jobId, DELIVERABLE, "");

        Ledger memory nowL = _assertConservation(before, budget);
        (, uint256 platformFee) = _expectedFees(budget);
        assertEq(nowL.evaluator, before.evaluator, "tanpa evaluator tidak ada evaluatorFee");
        assertEq(nowL.treasury - before.treasury, platformFee, "platformFee tetap dipotong");
        assertEq(nowL.provider - before.provider, budget - platformFee, "payout = budget - platformFee");
        assertEq(uint8(acp.getJob(jobId).status), 3, "Completed");
    }

    function testFuzz_conservation_rejected(uint256 budget) public {
        budget = bound(budget, 0, MAX_BUDGET);
        Ledger memory before = _ledger();
        uint256 jobId = _submittedJob(EVALUATOR, budget);

        vm.prank(EVALUATOR);
        acp.reject(jobId, REASON, "");

        Ledger memory nowL = _assertConservation(before, budget);
        assertEq(nowL.client, before.client, "reject mengembalikan 100% budget ke client");
        assertEq(nowL.provider, before.provider, "provider nol di jalur Rejected");
        assertEq(nowL.evaluator, before.evaluator, "fee evaluator nol di jalur Rejected");
        assertEq(nowL.treasury, before.treasury, "platformFee nol di jalur Rejected");
        assertEq(uint8(acp.getJob(jobId).status), 4, "Rejected");
    }

    function testFuzz_conservation_expiredFromFunded(uint256 budget) public {
        budget = bound(budget, 0, MAX_BUDGET);
        Ledger memory before = _ledger();
        uint256 jobId = _fundedJob(EVALUATOR, budget);

        vm.warp(uint256(acp.getJob(jobId).expiredAt));
        vm.prank(STRANGER);
        acp.claimRefund(jobId);

        Ledger memory nowL = _assertConservation(before, budget);
        assertEq(nowL.client, before.client, "refund 100% ke client");
        assertEq(nowL.provider, before.provider, "provider nol");
        assertEq(uint8(acp.getJob(jobId).status), 5, "Expired");
    }

    function testFuzz_conservation_expiredFromSubmitted(uint256 budget) public {
        budget = bound(budget, 0, MAX_BUDGET);
        Ledger memory before = _ledger();
        uint256 jobId = _submittedJob(EVALUATOR, budget);

        vm.warp(uint256(acp.getJob(jobId).expiredAt) + acp.EVALUATOR_GRACE_PERIOD());
        vm.prank(STRANGER);
        acp.claimRefund(jobId);

        Ledger memory nowL = _assertConservation(before, budget);
        assertEq(nowL.client, before.client, "refund 100% ke client walau sudah Submitted");
        assertEq(nowL.provider, before.provider, "provider NOL sesudah griefing claimRefund");
        assertEq(uint8(acp.getJob(jobId).status), 5, "Expired");
    }

    /// @dev Dari Open belum ada escrow sama sekali, walau `setBudget` sudah dipanggil: inflow = 0.
    function testFuzz_conservation_expiredFromOpen(uint256 budget) public {
        budget = bound(budget, 0, MAX_BUDGET);
        Ledger memory before = _ledger();
        uint256 jobId = _createJob(EVALUATOR);
        vm.prank(PROVIDER);
        acp.setBudget(jobId, budget, "");

        vm.warp(uint256(acp.getJob(jobId).expiredAt));
        vm.prank(STRANGER);
        acp.claimRefund(jobId);

        _assertConservation(before, 0);
        assertEq(usdc.balanceOf(CLIENT), before.client, "tidak ada token yang pernah berpindah");
        assertEq(uint8(acp.getJob(jobId).status), 5, "Expired");
    }

    /// @dev Beberapa job berbudget berbeda menempuh KEEMPAT jalur akhir dalam satu escrow yang sama.
    ///      Membuktikan invariant tetap berlaku saat escrow bercampur, bukan hanya satu job terisolasi.
    function testFuzz_conservation_mixedPaths(uint256 b1, uint256 b2, uint256 b3, uint256 b4) public {
        b1 = bound(b1, 0, MAX_BUDGET);
        b2 = bound(b2, 0, MAX_BUDGET);
        b3 = bound(b3, 0, MAX_BUDGET);
        b4 = bound(b4, 0, MAX_BUDGET);
        uint256 inflow = b1 + b2 + b3 + b4;

        Ledger memory before = _ledger();

        uint256 completedJob = _submittedJob(EVALUATOR, b1);
        uint256 rejectedJob = _submittedJob(EVALUATOR, b2);
        uint256 expiredJob = _fundedJob(EVALUATOR, b3);
        uint256 autoJob = _fundedJob(address(0), b4);

        assertEq(usdc.balanceOf(address(acp)), before.acp + inflow, "escrow memegang seluruh inflow");

        vm.prank(EVALUATOR);
        acp.complete(completedJob, REASON, "");
        vm.prank(EVALUATOR);
        acp.reject(rejectedJob, REASON, "");
        vm.prank(PROVIDER);
        acp.submit(autoJob, DELIVERABLE, "");
        vm.warp(uint256(acp.getJob(expiredJob).expiredAt));
        vm.prank(STRANGER);
        acp.claimRefund(expiredJob);

        _assertConservation(before, inflow);
    }

    // ------------------------------------------------------------------
    // Budget NOL: nol transfer, nol event hantu
    // ------------------------------------------------------------------

    /// @dev Jalur NYATA dan GRATIS (api-facts §A): `Open` + `budget == 0` + `evaluator != 0` boleh
    ///      langsung di-`submit` → Submitted, lalu evaluator `complete`. Source `:527-537` menjaga
    ///      KETIGA transfer satu per satu (`platformFee > 0`, `evalFee > 0`, `net > 0`), jadi ACP asli
    ///      memancarkan NOL `Transfer` ERC-20 dan NOL `EvaluatorFeePaid`. Mock mencapai hal yang sama
    ///      lewat guard `amount != 0` di dalam `_push` (satu tempat, bukan tiga) — tes ini mengunci
    ///      HASIL yang teramati, bukan bentuk penulisannya, supaya penyimpangan "event hantu" tidak
    ///      bisa kembali diam-diam lewat perubahan di salah satu dari ketiga tempat itu.
    function test_zeroBudget_completeEmitsNoErc20TransferAtAll() public {
        uint256 jobId = _createJob(EVALUATOR); // TANPA setBudget, TANPA fund: escrow tidak pernah terisi
        vm.prank(PROVIDER);
        acp.submit(jobId, DELIVERABLE, "");
        assertEq(uint8(acp.getJob(jobId).status), 2, "Open + budget 0 + evaluator bukan nol jadi Submitted");

        Ledger memory before = _ledger();
        usdc.watch(acp, jobId);

        vm.recordLogs();
        vm.prank(EVALUATOR);
        acp.complete(jobId, REASON, "");
        Vm.Log[] memory logs = vm.getRecordedLogs();

        for (uint256 i = 0; i < logs.length; i++) {
            assertTrue(logs[i].emitter != address(usdc), "TIDAK boleh ada Transfer ERC-20 beramount nol");
        }
        assertEq(logs.length, 2, "hanya JobCompleted + PaymentReleased; EvaluatorFeePaid ada di dalam guard evalFee>0");
        assertEq(usdc.observations().length, 0, "nol transfer keluar: pengintip tidak pernah terpanggil");
        _assertConservation(before, 0);
        assertEq(uint8(acp.getJob(jobId).status), 3, "Completed");
    }

    /// @dev Varian berbudget nol yang MELALUI escrow: `fund(jobId, 0, "")` sah (api-facts §A).
    function test_zeroBudget_fundedThenComplete_emitsNoErc20Transfer() public {
        Ledger memory before = _ledger();
        uint256 jobId = _submittedJob(EVALUATOR, 0);

        vm.recordLogs();
        vm.prank(EVALUATOR);
        acp.complete(jobId, REASON, "");
        Vm.Log[] memory logs = vm.getRecordedLogs();

        for (uint256 i = 0; i < logs.length; i++) {
            assertTrue(logs[i].emitter != address(usdc), "TIDAK boleh ada Transfer ERC-20 beramount nol");
        }
        assertEq(logs.length, 2, "JobCompleted + PaymentReleased saja");
        _assertConservation(before, 0);
    }

    /// @dev Kontrol: pada budget > 0 memang ada TIGA `Transfer` ERC-20 + `EvaluatorFeePaid`. Tanpa
    ///      kontrol ini, kedua tes di atas bisa hijau hanya karena mock berhenti membayar sama sekali.
    function test_nonZeroBudget_completeEmitsThreeErc20Transfers() public {
        uint256 jobId = _submittedJob(EVALUATOR, 1_000_000);

        vm.recordLogs();
        vm.prank(EVALUATOR);
        acp.complete(jobId, REASON, "");
        Vm.Log[] memory logs = vm.getRecordedLogs();

        uint256 transfers;
        for (uint256 i = 0; i < logs.length; i++) {
            if (logs[i].emitter == address(usdc)) transfers++;
        }
        assertEq(transfers, 3, "treasury + evaluator + provider");
        assertEq(logs.length, 6, "3 Transfer + EvaluatorFeePaid + JobCompleted + PaymentReleased");
    }

    // ------------------------------------------------------------------
    // Checks-Effects-Interactions: status akhir ditulis SEBELUM transfer keluar
    // ------------------------------------------------------------------

    /// @dev MUTAN YANG HARUS DIGIGIT: memindahkan `job.status = Status.Completed` ke BAWAH `_push` di
    ///      `complete`. Tanpa tes ini mutan itu lolos, padahal ia membuka jendela di mana kontrak token
    ///      (satu-satunya pihak yang dipanggil di tengah `complete`) melihat job masih Submitted.
    function test_cei_complete_statusCompletedBeforeEveryPayout() public {
        uint256 jobId = _submittedJob(EVALUATOR, 1_000_000);
        usdc.watch(acp, jobId);

        vm.prank(EVALUATOR);
        acp.complete(jobId, REASON, "");

        uint8[] memory seen = usdc.observations();
        assertEq(seen.length, 3, "complete harus melakukan 3 transfer keluar (treasury, evaluator, provider)");
        for (uint256 i = 0; i < seen.length; i++) {
            assertEq(seen[i], 3, "status WAJIB sudah Completed pada setiap transfer keluar");
        }
    }

    function test_cei_autoComplete_statusCompletedBeforeEveryPayout() public {
        uint256 jobId = _fundedJob(address(0), 1_000_000);
        usdc.watch(acp, jobId);

        vm.prank(PROVIDER);
        acp.submit(jobId, DELIVERABLE, "");

        uint8[] memory seen = usdc.observations();
        assertEq(seen.length, 2, "auto-complete melakukan 2 transfer keluar (treasury, provider)");
        for (uint256 i = 0; i < seen.length; i++) {
            assertEq(seen[i], 3, "status WAJIB sudah Completed pada setiap transfer keluar");
        }
    }

    function test_cei_reject_statusRejectedBeforeRefund() public {
        uint256 jobId = _submittedJob(EVALUATOR, 1_000_000);
        usdc.watch(acp, jobId);

        vm.prank(EVALUATOR);
        acp.reject(jobId, REASON, "");

        uint8[] memory seen = usdc.observations();
        assertEq(seen.length, 1, "reject melakukan 1 transfer keluar (refund client)");
        assertEq(seen[0], 4, "status WAJIB sudah Rejected saat refund dikirim");
    }

    function test_cei_claimRefund_statusExpiredBeforeRefund() public {
        uint256 jobId = _fundedJob(EVALUATOR, 1_000_000);
        usdc.watch(acp, jobId);

        vm.warp(uint256(acp.getJob(jobId).expiredAt));
        vm.prank(STRANGER);
        acp.claimRefund(jobId);

        uint8[] memory seen = usdc.observations();
        assertEq(seen.length, 1, "claimRefund melakukan 1 transfer keluar (refund client)");
        assertEq(seen[0], 5, "status WAJIB sudah Expired saat refund dikirim");
    }

    /// @dev Kontrol untuk keempat tes CEI di atas: pengintip memang aktif dan memang melihat status
    ///      LEWAT `getJob`. Kalau `watch` lupa dipanggil, tes CEI akan hijau palsu dengan 0 observasi —
    ///      makanya semuanya meng-assert `seen.length` lebih dulu.
    function test_cei_observerIsActuallyWired() public {
        uint256 jobId = _submittedJob(EVALUATOR, 1_000_000);
        assertEq(usdc.observations().length, 0, "belum watch: tidak ada observasi");
        usdc.watch(acp, jobId);
        assertEq(usdc.watchedJobId(), jobId, "jobId yang diintip");

        vm.prank(EVALUATOR);
        acp.complete(jobId, REASON, "");
        assertGt(usdc.observations().length, 0, "pengintip harus benar-benar dieksekusi");
    }
}
