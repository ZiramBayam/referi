// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Test, Vm} from "forge-std/Test.sol";
import {AgenticCommerce} from "./mocks/AgenticCommerce.sol";
import {MockUSDC} from "./mocks/MockUSDC.sol";

/// @dev Evaluator berupa KONTRAK (ADR-003): membuktikan mock tidak berasumsi evaluator = EOA.
contract EvaluatorContract {
    AgenticCommerce private immutable acp;

    constructor(AgenticCommerce acp_) {
        acp = acp_;
    }

    function completeJob(uint256 jobId, bytes32 reason) external {
        acp.complete(jobId, reason, "");
    }
}

/// @dev Token ERC-20 yang MENYERANG BALIK dari dalam `transfer`/`transferFrom`. Dipakai untuk
///      membuktikan bahwa guard reentrancy mock berlaku LINTAS FUNGSI (satu slot transient bersama,
///      persis `ReentrancyGuardTransient` yang diwarisi ACP asli) dan bahwa `setProvider` sengaja
///      TIDAK ikut dijaga. Pemanggilan balik dilakukan dengan panggilan BERTIPE, bukan `.call`,
///      supaya revert-nya membubung apa adanya tanpa assembly.
contract ReentrantToken {
    /// @dev Satu mode per fungsi alur job yang di kontrak asli ber-`nonReentrant`, plus `SetProvider`
    ///      yang sengaja TIDAK dijaga. Semua dipanggil BERTIPE supaya revert-nya membubung apa adanya.
    enum Mode {
        None,
        ClaimRefund,
        SetProvider,
        CreateJob,
        SetBudget,
        Submit,
        Complete,
        Reject
    }

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    AgenticCommerce public acp;
    Mode public mode;
    uint256 public modeJobId;
    address public modeProvider;
    /// @dev Parameter numerik mode: `expiredAt` untuk CreateJob, `amount` untuk SetBudget.
    uint256 public modeValue;

    bytes32 public constant PAYLOAD = keccak256("payload reentrancy");

    error NotEnoughBalance();
    error NotEnoughAllowance();

    function setAcp(AgenticCommerce acp_) external {
        acp = acp_;
    }

    /// @dev Sekali tembak: mode direset sebelum menyerang supaya serangan tidak berulang tanpa batas.
    function arm(Mode mode_, uint256 jobId, address provider_, uint256 value_) external {
        mode = mode_;
        modeJobId = jobId;
        modeProvider = provider_;
        modeValue = value_;
    }

    /// @dev Token menjadi CLIENT sebuah job, supaya serangan `setProvider` datang dari pihak yang sah.
    function createJobAsClient(address provider_, address evaluator_, uint256 expiredAt_) external returns (uint256) {
        return acp.createJob(provider_, evaluator_, expiredAt_, "kontrol reentrancy", address(0));
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _move(msg.sender, to, amount);
        _fire();
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            if (allowed < amount) revert NotEnoughAllowance();
            allowance[from][msg.sender] = allowed - amount;
        }
        _move(from, to, amount);
        _fire();
        return true;
    }

    function _move(address from, address to, uint256 amount) private {
        uint256 bal = balanceOf[from];
        if (bal < amount) revert NotEnoughBalance();
        balanceOf[from] = bal - amount;
        balanceOf[to] += amount;
    }

    function _fire() private {
        Mode m = mode;
        if (m == Mode.None) return;
        mode = Mode.None;
        if (m == Mode.ClaimRefund) {
            acp.claimRefund(modeJobId);
        } else if (m == Mode.SetProvider) {
            acp.setProvider(modeJobId, modeProvider);
        } else if (m == Mode.CreateJob) {
            acp.createJob(modeProvider, address(0), modeValue, "reentrancy createJob", address(0));
        } else if (m == Mode.SetBudget) {
            acp.setBudget(modeJobId, modeValue, "");
        } else if (m == Mode.Submit) {
            acp.submit(modeJobId, PAYLOAD, "");
        } else if (m == Mode.Complete) {
            acp.complete(modeJobId, PAYLOAD, "");
        } else {
            acp.reject(modeJobId, PAYLOAD, "");
        }
    }
}

contract AgenticCommerceTest is Test {
    MockUSDC internal usdc;
    AgenticCommerce internal acp;

    address internal client = makeAddr("client");
    address internal provider = makeAddr("provider");
    address internal evaluator = makeAddr("evaluator");
    address internal treasury = makeAddr("treasury");
    address internal stranger = makeAddr("stranger");

    uint256 internal constant BUDGET = 10_000_000; // 10 USDC (6 desimal)
    /// @dev Aritmetika DIBUKTIKAN di fork Base Sepolia (api-facts §A): evaluatorFeeBP=500, platformFeeBP=100.
    uint256 internal constant EVALUATOR_FEE = 500_000; // 5%
    uint256 internal constant PLATFORM_FEE = 100_000; // 1%
    uint256 internal constant PROVIDER_AMOUNT = 9_400_000; // budget - kedua fee

    bytes32 internal constant DELIVERABLE = keccak256("ipfs://bafkreiabc123");
    bytes32 internal constant REASON = keccak256("bukti: lulus rubric");

    /// @dev topic0 dari `cast sig-event` 2026-09-03 (api-facts §A), ditulis LITERAL supaya perubahan
    ///      signature/indexed di mock ketahuan, bukan ikut berubah bersama tes.
    bytes32 internal constant T_JOB_CREATED = 0xb0f0239bfdd96453e24733e18bfc24b70d8fadf123dd977473518dd577ee79b9;
    bytes32 internal constant T_JOB_FUNDED = 0xe3fbcc1ea1bdc559ec7f0347efde7655e58b5f45a30b0e4470a583c3ef5496b3;
    bytes32 internal constant T_JOB_SUBMITTED = 0x80c17db79857f338a6a6df68a6883ecc0ce78e2202fe61ed979733573f40538e;
    bytes32 internal constant T_JOB_COMPLETED = 0x0fd54bd364fa9e67f17b091aefe930932c09fe7651cf5ad02c71a418f3341444;
    bytes32 internal constant T_JOB_REJECTED = 0xae7362b1af91f4492868987b9c73990d780060811551b58728fbe96fd1bab275;
    bytes32 internal constant T_JOB_EXPIRED = 0x97237956f8810192811e2c3f273fd02c5d6295206fdd9c62e6fe2bfc19ba9232;
    bytes32 internal constant T_PAYMENT_RELEASED = 0x21d71db5be59bb9fa133895586b7404307dd33fb93b16db09dc6f1d9d7d231b0;
    bytes32 internal constant T_EVALUATOR_FEE_PAID = 0x253dd534010ac976fa263caa123bae79b9c50292adf7ce67bdc5ec309f784e61;
    bytes32 internal constant T_REFUNDED = 0x7ca5472b7ea78c2c0141c5a12ee6d170cf4ce8ed06be3d22c8252ddfc7a6a2c4;
    bytes32 internal constant T_BUDGET_SET = 0x869e2577b006bf47ee981cf6fec2e25583548081c14b98deab587f77b5068038;
    bytes32 internal constant T_PROVIDER_SET = 0x9a87df076ea1725aba8ba29d32517ce37c9597d88cbf16ec6707892cc330ab69;

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

    function setUp() public {
        // Waktu awal yang wajar supaya `block.timestamp - X` di tes batas tidak underflow.
        vm.warp(1_000_000);
        usdc = new MockUSDC();
        acp = new AgenticCommerce(address(usdc), treasury);
        usdc.mint(client, 100_000_000);
        vm.prank(client);
        usdc.approve(address(acp), type(uint256).max);
    }

    function _createJob(address evaluator_) internal returns (uint256 jobId) {
        vm.prank(client);
        jobId = acp.createJob(provider, evaluator_, block.timestamp + 1 hours, "tulis laporan riset", address(0));
    }

    function _fundedJob(address evaluator_) internal returns (uint256 jobId) {
        jobId = _createJob(evaluator_);
        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");
        vm.prank(client);
        acp.fund(jobId, BUDGET, "");
    }

    function _submittedJob(address evaluator_) internal returns (uint256 jobId) {
        jobId = _fundedJob(evaluator_);
        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");
    }

    function _status(uint256 jobId) internal view returns (AgenticCommerce.Status) {
        return acp.getJob(jobId).status;
    }

    /// @dev Ambil log yang dipancarkan ACP saja (log Transfer milik token dibuang).
    function _acpLogs() internal returns (Vm.Log[] memory out) {
        Vm.Log[] memory all = vm.getRecordedLogs();
        uint256 n;
        for (uint256 i; i < all.length; ++i) {
            if (all[i].emitter == address(acp)) ++n;
        }
        out = new Vm.Log[](n);
        uint256 k;
        for (uint256 i; i < all.length; ++i) {
            if (all[i].emitter == address(acp)) out[k++] = all[i];
        }
    }

    // ====================================================================
    // Siklus utama
    // ====================================================================

    /// AC utama task 1.1: siklus Open→Funded→Submitted→Completed berjalan.
    function test_fullCycle_openFundedSubmittedCompleted() public {
        uint256 expiredAt = block.timestamp + 1 hours;
        uint256 jobId = _createJob(evaluator);

        AgenticCommerce.Job memory job = acp.getJob(jobId);
        assertEq(job.client, client, "client");
        assertEq(job.provider, provider, "provider");
        assertEq(job.evaluator, evaluator, "evaluator");
        assertEq(job.hook, address(0), "hook");
        assertEq(uint256(job.expiredAt), expiredAt, "expiredAt (uint48)");
        assertEq(job.description, "tulis laporan riset", "description");
        assertEq(uint8(job.status), uint8(AgenticCommerce.Status.Open), "status Open");

        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");
        assertEq(acp.getJob(jobId).budget, BUDGET, "budget");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Open), "masih Open setelah setBudget");

        vm.prank(client);
        acp.fund(jobId, BUDGET, "");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Funded), "status Funded");
        assertEq(usdc.balanceOf(address(acp)), BUDGET, "escrow terisi");
        assertEq(usdc.balanceOf(client), 90_000_000, "client berkurang");

        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Submitted), "status Submitted");

        // Urutan emit DIBUKTIKAN di fork: EvaluatorFeePaid, JobCompleted, PaymentReleased.
        vm.expectEmit(true, true, true, true, address(acp));
        emit EvaluatorFeePaid(jobId, evaluator, EVALUATOR_FEE);
        vm.expectEmit(true, true, true, true, address(acp));
        emit JobCompleted(jobId, evaluator, REASON);
        vm.expectEmit(true, true, true, true, address(acp));
        emit PaymentReleased(jobId, provider, PROVIDER_AMOUNT);

        vm.prank(evaluator);
        acp.complete(jobId, REASON, "");

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Completed), "status Completed");
        assertEq(usdc.balanceOf(provider), PROVIDER_AMOUNT, "provider dibayar");
        assertEq(usdc.balanceOf(evaluator), EVALUATOR_FEE, "evaluator fee 5%");
        assertEq(usdc.balanceOf(treasury), PLATFORM_FEE, "platform fee 1%");
        assertEq(usdc.balanceOf(address(acp)), 0, "escrow kosong");
    }

    /// AC (c): aritmetika fee dengan platformFeeBP = 100 — angka persis dari fork Base Sepolia.
    function test_complete_feeArithmetic_platformFeeBP100() public {
        assertEq(acp.evaluatorFeeBP(), 500, "evaluatorFeeBP on-chain = 500");
        assertEq(acp.platformFeeBP(), 100, "platformFeeBP on-chain = 100, BUKAN 0");

        uint256 jobId = _submittedJob(evaluator);
        vm.prank(evaluator);
        acp.complete(jobId, REASON, "");

        assertEq(usdc.balanceOf(provider), 9_400_000, "provider 9.400.000");
        assertEq(usdc.balanceOf(evaluator), 500_000, "evaluator 500.000");
        assertEq(usdc.balanceOf(treasury), 100_000, "treasury 100.000");
        assertEq(
            usdc.balanceOf(provider) + usdc.balanceOf(evaluator) + usdc.balanceOf(treasury), BUDGET, "konservasi dana"
        );
    }

    /// ADR-003: evaluator = EvaluatorVault (kontrak), bukan EOA.
    function test_complete_byContractEvaluator() public {
        EvaluatorContract vault = new EvaluatorContract(acp);
        uint256 jobId = _submittedJob(address(vault));

        vault.completeJob(jobId, REASON);

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Completed), "status Completed");
        assertEq(usdc.balanceOf(address(vault)), EVALUATOR_FEE, "fee ke kontrak evaluator");
    }

    /// api-facts §A: bila `evaluator == address(0)`, `submit` LANGSUNG menyelesaikan job dan provider
    /// menerima budget − platformFee saja; `JobCompleted.reason` = nilai `deliverable`.
    function test_submit_withoutEvaluator_autoCompletes() public {
        uint256 jobId = _fundedJob(address(0));

        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Completed), "langsung Completed");
        assertEq(usdc.balanceOf(provider), 9_900_000, "provider = budget - platformFee");
        assertEq(usdc.balanceOf(treasury), PLATFORM_FEE, "platform fee tetap dipotong");
        assertEq(usdc.balanceOf(address(acp)), 0, "escrow kosong");

        vm.prank(address(0));
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.complete(jobId, REASON, "");
    }

    // ====================================================================
    // Batas waktu
    // ====================================================================

    /// AC (c): `expiredAt` STRICT — `now + 300` revert, `now + 301` sukses (api-facts §A).
    function test_createJob_expiryBoundary_isStrict() public {
        assertEq(acp.MIN_EXPIRY_DELAY(), 300, "MIN_EXPIRY_DELAY 5 menit");

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ExpiryTooShort.selector);
        acp.createJob(provider, evaluator, block.timestamp + 300, "tepat di batas", address(0));

        vm.prank(client);
        uint256 jobId = acp.createJob(provider, evaluator, block.timestamp + 301, "satu detik di atas", address(0));
        assertEq(uint256(acp.getJob(jobId).expiredAt), block.timestamp + 301, "job terbuat");
    }

    /// api-facts §A: `submit` pada `now == expiredAt` → `WrongStatus()` (bukan error waktu tersendiri).
    function test_submit_atExpiredAt_reverts() public {
        uint256 jobId = _fundedJob(evaluator);
        vm.warp(acp.getJob(jobId).expiredAt);

        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.submit(jobId, DELIVERABLE, "");
    }

    /// api-facts §A: `complete`/`reject` TIDAK punya guard expiry — verdict telat tetap bisa dieksekusi.
    function test_complete_afterExpiry_succeeds() public {
        uint256 jobId = _submittedJob(evaluator);
        vm.warp(uint256(acp.getJob(jobId).expiredAt) + 1);

        vm.prank(evaluator);
        acp.complete(jobId, REASON, "");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Completed), "Completed setelah expiredAt");
    }

    function test_reject_afterExpiry_refundsFullBudget() public {
        uint256 jobId = _submittedJob(evaluator);
        vm.warp(uint256(acp.getJob(jobId).expiredAt) + 1);

        vm.prank(evaluator);
        acp.reject(jobId, REASON, "");

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Rejected), "status Rejected");
        assertEq(usdc.balanceOf(client), 100_000_000, "client menerima 100% budget");
        assertEq(usdc.balanceOf(evaluator), 0, "tidak ada fee evaluator pada reject");
    }

    // ====================================================================
    // claimRefund
    // ====================================================================

    /// KOREKSI 2026-09-03: klaim lama "claimRefund HANYA dari Funded, dari Submitted selalu WrongStatus"
    /// SALAH. Yang benar: dari Submitted BOLEH, tetapi hanya sesudah `expiredAt + EVALUATOR_GRACE_PERIOD`.
    /// Tes ini mengunci SELURUH sisi MERAH dari bisection fork (api-facts §A): offset -1, 0, +1, +100,
    /// +600, +898, +899 terhadap `expiredAt` semuanya revert `WrongStatus()` dan escrow tidak bergerak.
    function test_claimRefund_fromSubmitted_beforeGrace_revertsAtEveryOffset() public {
        uint256 jobId = _submittedJob(evaluator);
        uint256 expiredAt = uint256(acp.getJob(jobId).expiredAt);

        int256[7] memory offsets = [int256(-1), 0, 1, 100, 600, 898, 899];
        for (uint256 i; i < offsets.length; ++i) {
            vm.warp(uint256(int256(expiredAt) + offsets[i]));
            vm.prank(stranger);
            vm.expectRevert(AgenticCommerce.WrongStatus.selector);
            acp.claimRefund(jobId);

            assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Submitted), "status tidak berubah");
            assertEq(usdc.balanceOf(address(acp)), BUDGET, "escrow tetap terisi");
            assertEq(usdc.balanceOf(client), 90_000_000, "client belum menerima apa pun");
        }
    }

    /// api-facts §A: tepat pada `expiredAt` SUKSES, dan siapa pun boleh memanggil.
    function test_claimRefund_fromFunded_atExpiredAt_succeeds() public {
        uint256 jobId = _fundedJob(evaluator);
        vm.warp(acp.getJob(jobId).expiredAt);

        // Urutan emit DIBUKTIKAN di fork: Refunded, JobExpired.
        vm.expectEmit(true, true, true, true, address(acp));
        emit Refunded(jobId, client, BUDGET);
        vm.expectEmit(true, true, true, true, address(acp));
        emit JobExpired(jobId);

        vm.prank(stranger);
        acp.claimRefund(jobId);

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Expired), "status Expired");
        assertEq(usdc.balanceOf(client), 100_000_000, "client dipulangkan penuh");
    }

    function test_claimRefund_beforeExpiredAt_revertsWrongStatus() public {
        uint256 jobId = _fundedJob(evaluator);
        vm.warp(uint256(acp.getJob(jobId).expiredAt) - 1);

        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.claimRefund(jobId);
    }

    // ====================================================================
    // getJob / job tak dikenal
    // ====================================================================

    /// AC (c): `getJob(<id tak dikenal>)` TIDAK revert, mengembalikan struct nol (api-facts §A).
    function test_getJob_unknownId_returnsZeroStruct() public view {
        AgenticCommerce.Job memory job = acp.getJob(999_999);
        assertEq(job.client, address(0), "client nol");
        assertEq(job.provider, address(0), "provider nol");
        assertEq(job.evaluator, address(0), "evaluator nol");
        assertEq(job.hook, address(0), "hook nol");
        assertEq(uint256(job.expiredAt), 0, "expiredAt nol");
        assertEq(job.budget, 0, "budget nol");
        assertEq(uint8(job.status), uint8(AgenticCommerce.Status.Open), "status nol (= Open)");
        assertEq(bytes(job.description).length, 0, "description kosong");

        AgenticCommerce.Job memory zeroId = acp.getJob(0);
        assertEq(zeroId.client, address(0), "id 0 juga struct nol");
    }

    /// api-facts §A: fungsi yang MENGUBAH state pada id tak dikenal → `InvalidJob()`.
    function test_stateChanging_unknownId_revertsInvalidJob() public {
        uint256 unknownId = 999_999;

        vm.expectRevert(AgenticCommerce.InvalidJob.selector);
        acp.claimRefund(unknownId);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.InvalidJob.selector);
        acp.fund(unknownId, BUDGET, "");

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.InvalidJob.selector);
        acp.setProvider(unknownId, provider);

        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.InvalidJob.selector);
        acp.setBudget(unknownId, BUDGET, "");

        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.InvalidJob.selector);
        acp.submit(unknownId, DELIVERABLE, "");

        vm.prank(evaluator);
        vm.expectRevert(AgenticCommerce.InvalidJob.selector);
        acp.complete(unknownId, REASON, "");

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.InvalidJob.selector);
        acp.reject(unknownId, REASON, "");

        // id 0 tidak pernah dipakai (job pertama = 1).
        vm.expectRevert(AgenticCommerce.InvalidJob.selector);
        acp.claimRefund(0);
    }

    // ====================================================================
    // Otorisasi & aturan setter
    // ====================================================================

    /// api-facts §A: `fund` mensyaratkan provider sudah di-set.
    function test_fund_withoutProvider_reverts() public {
        vm.prank(client);
        uint256 jobId =
            acp.createJob(address(0), evaluator, block.timestamp + 1 hours, "job tanpa provider", address(0));

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ProviderNotSet.selector);
        acp.fund(jobId, 0, "");
    }

    function test_submit_byNonProvider_reverts() public {
        uint256 jobId = _fundedJob(evaluator);

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.submit(jobId, DELIVERABLE, "");
    }

    function test_complete_byNonEvaluator_reverts() public {
        uint256 jobId = _submittedJob(evaluator);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.complete(jobId, REASON, "");
    }

    function test_fund_byNonClient_reverts() public {
        uint256 jobId = _createJob(evaluator);
        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.fund(jobId, BUDGET, "");
    }

    function test_fund_wrongExpectedBudget_reverts() public {
        uint256 jobId = _createJob(evaluator);
        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");

        // `BudgetMismatch()` TIDAK punya argumen di ABI asli.
        vm.prank(client);
        vm.expectRevert(AgenticCommerce.BudgetMismatch.selector);
        acp.fund(jobId, BUDGET - 1, "");
    }

    /// api-facts §A: `fund(jobId, 0, "")` pada job yang belum pernah `setBudget` DITERIMA (budget 0 sah).
    function test_fund_zeroBudget_withoutSetBudget_succeeds() public {
        uint256 jobId = _createJob(evaluator);

        vm.prank(client);
        acp.fund(jobId, 0, "");

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Funded), "status Funded");
        assertEq(acp.getJob(jobId).budget, 0, "budget 0");
    }

    function test_fund_twice_revertsWrongStatus() public {
        uint256 jobId = _fundedJob(evaluator);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.fund(jobId, BUDGET, "");
    }

    /// api-facts §A: `setBudget` hanya provider, `amount == 0` diterima, boleh berulang selagi Open.
    function test_setBudget_zeroAllowed_andRepeatable() public {
        uint256 jobId = _createJob(evaluator);

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.setBudget(jobId, BUDGET, "");

        vm.prank(provider);
        acp.setBudget(jobId, 0, "");
        assertEq(acp.getJob(jobId).budget, 0, "budget 0 diterima");

        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");
        vm.prank(provider);
        acp.setBudget(jobId, BUDGET + 1, "");
        assertEq(acp.getJob(jobId).budget, BUDGET + 1, "setBudget menimpa");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Open), "tetap Open");
    }

    /// api-facts §A: `setProvider` hanya client, HANYA saat Open + `now < expiredAt`, hanya bila provider
    /// masih address(0), dan bukan ke address(0). Urutan cek lengkap dikunci di
    /// `test_setProvider_checkOrder_statusAndExpiryBeforeAuthorization`.
    function test_setProvider_rules() public {
        vm.prank(client);
        uint256 jobId =
            acp.createJob(address(0), evaluator, block.timestamp + 1 hours, "job tanpa provider", address(0));

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.setProvider(jobId, provider);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ZeroAddress.selector);
        acp.setProvider(jobId, address(0));

        vm.expectEmit(true, true, true, true, address(acp));
        emit ProviderSet(jobId, provider);
        vm.prank(client);
        acp.setProvider(jobId, provider);
        assertEq(acp.getJob(jobId).provider, provider, "provider terpasang");

        // Sudah terisi → WrongStatus, bukan Unauthorized.
        vm.prank(client);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.setProvider(jobId, stranger);
    }

    /// api-facts §A: saat Open, evaluator BUKAN pihak yang berwenang (yang berwenang: client ATAU
    /// provider — lihat `test_reject_open_byProviderOrClient_succeeds`); saat Funded/Submitted dengan
    /// `evaluator != 0`, HANYA evaluator.
    function test_reject_authorization_dependsOnStatus() public {
        uint256 openJob = _createJob(evaluator);
        vm.prank(evaluator);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.reject(openJob, REASON, "");

        vm.prank(client);
        acp.reject(openJob, REASON, "");
        assertEq(uint8(_status(openJob)), uint8(AgenticCommerce.Status.Rejected), "Open ditolak client");

        uint256 fundedJob = _fundedJob(evaluator);
        vm.prank(client);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.reject(fundedJob, REASON, "");

        vm.prank(evaluator);
        acp.reject(fundedJob, REASON, "");
        assertEq(uint8(_status(fundedJob)), uint8(AgenticCommerce.Status.Rejected), "Funded ditolak evaluator");
    }

    function test_createJob_nonWhitelistedHook_reverts() public {
        address hook = makeAddr("hook");

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.HookNotWhitelisted.selector);
        acp.createJob(provider, evaluator, block.timestamp + 1 hours, "job dengan hook", hook);

        acp.mockSetHookWhitelist(hook, true);
        vm.prank(client);
        uint256 jobId = acp.createJob(provider, evaluator, block.timestamp + 1 hours, "job dengan hook", hook);
        assertEq(acp.getJob(jobId).hook, hook, "hook tersimpan");
    }

    // ====================================================================
    // Bentuk log (topic0 + indexed) & selector
    // ====================================================================

    /// Mengunci bentuk log terhadap topic0 LITERAL dari chain: kalau daftar `indexed` atau signature event
    /// di mock menyimpang, topic0/`topics.length` tidak akan cocok. Termasuk mengunci bahwa
    /// `JobCompleted` berbentuk 3 argumen (uint256,address,bytes32) — bentuk 2 argumen TIDAK ADA di ACP.
    function test_eventTopics_andEmitOrder_matchAcpAbi() public {
        vm.recordLogs();

        vm.prank(client);
        uint256 jobId = acp.createJob(address(0), evaluator, block.timestamp + 1 hours, "job", address(0));
        vm.prank(client);
        acp.setProvider(jobId, provider);
        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");
        vm.prank(client);
        acp.fund(jobId, BUDGET, "");
        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");

        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 5, "5 log ACP sebelum complete");

        assertEq(logs[0].topics[0], T_JOB_CREATED, "topic0 JobCreated");
        assertEq(logs[0].topics.length, 4, "JobCreated: jobId+client+provider indexed (evaluator TIDAK)");
        assertEq(uint256(logs[0].topics[1]), jobId, "JobCreated topic1 = jobId");
        assertEq(address(uint160(uint256(logs[0].topics[2]))), client, "JobCreated topic2 = client");

        assertEq(logs[1].topics[0], T_PROVIDER_SET, "topic0 ProviderSet");
        assertEq(logs[1].topics.length, 3, "ProviderSet: jobId+provider indexed");
        assertEq(address(uint160(uint256(logs[1].topics[2]))), provider, "ProviderSet topic2 = provider");
        assertEq(logs[1].data.length, 0, "ProviderSet tidak punya argumen non-indexed");

        assertEq(logs[2].topics[0], T_BUDGET_SET, "topic0 BudgetSet");
        assertEq(logs[2].topics.length, 2, "BudgetSet: hanya jobId indexed");
        assertEq(abi.decode(logs[2].data, (uint256)), BUDGET, "BudgetSet.amount di data = BUDGET");

        assertEq(logs[3].topics[0], T_JOB_FUNDED, "topic0 JobFunded");
        assertEq(logs[3].topics.length, 3, "JobFunded: jobId+client indexed");
        assertEq(address(uint160(uint256(logs[3].topics[2]))), client, "JobFunded topic2 = client");
        assertEq(abi.decode(logs[3].data, (uint256)), BUDGET, "JobFunded.amount di data = BUDGET");

        assertEq(logs[4].topics[0], T_JOB_SUBMITTED, "topic0 JobSubmitted");
        assertEq(logs[4].topics.length, 3, "JobSubmitted: jobId+provider indexed");
        assertEq(address(uint160(uint256(logs[4].topics[2]))), provider, "JobSubmitted topic2 = provider");
        // `deliverable` inilah yang vault cocokkan dengan teks hasil API ACP (api-facts §B.1).
        assertEq(abi.decode(logs[4].data, (bytes32)), DELIVERABLE, "JobSubmitted.deliverable di data");

        vm.recordLogs();
        vm.prank(evaluator);
        acp.complete(jobId, REASON, "");

        Vm.Log[] memory done = _acpLogs();
        assertEq(done.length, 3, "3 log ACP saat complete");
        assertEq(done[0].topics[0], T_EVALUATOR_FEE_PAID, "urutan 1: EvaluatorFeePaid");
        assertEq(done[0].topics.length, 3, "EvaluatorFeePaid: jobId+evaluator indexed");
        assertEq(address(uint160(uint256(done[0].topics[2]))), evaluator, "EvaluatorFeePaid topic2 = evaluator");
        assertEq(abi.decode(done[0].data, (uint256)), EVALUATOR_FEE, "EvaluatorFeePaid.amount di data");
        assertEq(done[1].topics[0], T_JOB_COMPLETED, "urutan 2: JobCompleted (3 argumen)");
        assertEq(done[1].topics.length, 3, "JobCompleted: jobId+evaluator indexed");
        assertEq(address(uint160(uint256(done[1].topics[2]))), evaluator, "JobCompleted topic2 = evaluator");
        assertEq(abi.decode(done[1].data, (bytes32)), REASON, "JobCompleted.reason di data");
        assertEq(done[2].topics[0], T_PAYMENT_RELEASED, "urutan 3: PaymentReleased");
        assertEq(done[2].topics.length, 3, "PaymentReleased: jobId+provider indexed");
        assertEq(address(uint160(uint256(done[2].topics[2]))), provider, "PaymentReleased topic2 = provider");
        assertEq(abi.decode(done[2].data, (uint256)), PROVIDER_AMOUNT, "PaymentReleased.amount di data");
    }

    function test_eventTopics_refundAndReject() public {
        uint256 jobId = _fundedJob(evaluator);
        vm.warp(acp.getJob(jobId).expiredAt);

        vm.recordLogs();
        acp.claimRefund(jobId);
        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 2, "2 log ACP saat claimRefund");
        assertEq(logs[0].topics[0], T_REFUNDED, "urutan 1: Refunded");
        assertEq(logs[0].topics.length, 3, "Refunded: jobId+client indexed");
        assertEq(address(uint160(uint256(logs[0].topics[2]))), client, "Refunded topic2 = client");
        assertEq(abi.decode(logs[0].data, (uint256)), BUDGET, "Refunded.amount di data = BUDGET");
        assertEq(logs[1].topics[0], T_JOB_EXPIRED, "urutan 2: JobExpired");
        assertEq(logs[1].topics.length, 2, "JobExpired: hanya jobId indexed");
        assertEq(logs[1].data.length, 0, "JobExpired tidak punya argumen non-indexed");

        uint256 rejected = _fundedJob(evaluator);
        vm.recordLogs();
        vm.prank(evaluator);
        acp.reject(rejected, REASON, "");
        Vm.Log[] memory rlogs = _acpLogs();
        assertEq(rlogs.length, 2, "2 log ACP saat reject berdana");
        assertEq(rlogs[0].topics[0], T_REFUNDED, "urutan 1: Refunded");
        assertEq(abi.decode(rlogs[0].data, (uint256)), BUDGET, "Refunded.amount = 100% budget");
        assertEq(rlogs[1].topics[0], T_JOB_REJECTED, "topic0 JobRejected");
        assertEq(rlogs[1].topics.length, 3, "JobRejected: jobId+rejector indexed");
        // `rejector` = msg.sender (di sini evaluator), BUKAN client.
        assertEq(address(uint160(uint256(rlogs[1].topics[2]))), evaluator, "JobRejected topic2 = rejector");
        assertEq(abi.decode(rlogs[1].data, (bytes32)), REASON, "JobRejected.reason di data");
    }

    /// Mengunci KESEMBILAN selector yang dipanggil kode kita terhadap konstanta literal dari ABI
    /// acp-node-v2 (api-facts §A). Konstanta sengaja ditulis sebagai literal, bukan diturunkan ulang
    /// dari string di file ini: mock yang salah dan tes yang salah dengan cara yang sama akan hijau
    /// sempurna di lokal lalu ditolak ACP asli di Sepolia — persis kegagalan yang dijaga tes ini.
    /// Sumber angka: `cast sig "<signature>"`, 2026-09-03.
    function test_selectors_matchAcpAbi() public pure {
        // `fund` punya parameter kedua `expectedBudget` (api-facts §A), BUKAN `fund(uint256)`
        // seperti teks EIP-8183 — ini penyimpangan yang paling sering dihalusinasikan.
        assertEq(AgenticCommerce.fund.selector, bytes4(0xd2e13f50), "fund(uint256,uint256,bytes)");

        assertEq(
            AgenticCommerce.createJob.selector, bytes4(0x41528812), "createJob(address,address,uint256,string,address)"
        );
        assertEq(AgenticCommerce.setProvider.selector, bytes4(0xd0fae591), "setProvider(uint256,address)");
        assertEq(AgenticCommerce.setBudget.selector, bytes4(0xdd4ae9d4), "setBudget(uint256,uint256,bytes)");
        assertEq(AgenticCommerce.submit.selector, bytes4(0x9e63798d), "submit(uint256,bytes32,bytes)");
        assertEq(AgenticCommerce.complete.selector, bytes4(0xd75bbdf3), "complete(uint256,bytes32,bytes)");
        assertEq(AgenticCommerce.reject.selector, bytes4(0x41dd26f5), "reject(uint256,bytes32,bytes)");
        assertEq(AgenticCommerce.claimRefund.selector, bytes4(0x5b7baf64), "claimRefund(uint256)");
        assertEq(AgenticCommerce.getJob.selector, bytes4(0xbf22c457), "getJob(uint256)");
    }

    /// KESEBELAS custom error PROYEK milik kontrak asli, dikunci ke selector literal (api-facts §A,
    /// `cast sig`, 2026-09-03). Angka lama SEMBILAN berasal dari ABI paket SDK acp-node-v2 yang ternyata
    /// SUBSET BASI: `ClientIsProvider`/`EvaluatorIsProvider` tidak ada di sana padahal ADA dan DIPAKAI di
    /// kontrak (ABI SDK 21 error vs ABI terverifikasi Sourcify 25). Nama lama
    /// (`NotClient`/`PastExpiry`/`UnknownJob`/…) tetap tidak ada, jadi tes ini juga mencegah nama-nama itu
    /// kembali menyelinap.
    function test_errorSelectors_matchAcpAbi() public pure {
        assertEq(AgenticCommerce.WrongStatus.selector, bytes4(0x8e78f0cb), "WrongStatus()");
        assertEq(AgenticCommerce.ExpiryTooShort.selector, bytes4(0xf7a0748c), "ExpiryTooShort()");
        assertEq(AgenticCommerce.BudgetMismatch.selector, bytes4(0x99b0fc87), "BudgetMismatch() TANPA argumen");
        assertEq(AgenticCommerce.InvalidJob.selector, bytes4(0x71c8f460), "InvalidJob()");
        assertEq(AgenticCommerce.Unauthorized.selector, bytes4(0x82b42900), "Unauthorized()");
        assertEq(AgenticCommerce.ProviderNotSet.selector, bytes4(0xa9456d43), "ProviderNotSet()");
        assertEq(AgenticCommerce.HookNotWhitelisted.selector, bytes4(0xa04b28ec), "HookNotWhitelisted()");
        assertEq(AgenticCommerce.ZeroAddress.selector, bytes4(0xd92e233d), "ZeroAddress()");
        assertEq(AgenticCommerce.FeesTooHigh.selector, bytes4(0xc9034e18), "FeesTooHigh()");
        assertEq(AgenticCommerce.ClientIsProvider.selector, bytes4(0x332ff0f9), "ClientIsProvider()");
        assertEq(AgenticCommerce.EvaluatorIsProvider.selector, bytes4(0xc7b4e9eb), "EvaluatorIsProvider()");

        // Milik OpenZeppelin `ReentrancyGuardTransient` yang diwarisi kontrak asli; selector 0x3ee5aeb5
        // memang ada di bytecode implementasi (api-facts §A).
        assertEq(
            AgenticCommerce.ReentrancyGuardReentrantCall.selector, bytes4(0x3ee5aeb5), "ReentrancyGuardReentrantCall()"
        );
    }

    // ====================================================================
    // claimRefund — tenggang evaluator (KOREKSI 2026-09-03)
    //
    // Sumber: docs/api-facts.md §A blok "KOREKSI 2026-09-03", diturunkan dari source TERVERIFIKASI
    // Sourcify (`exact_match`) untuk implementasi 0xc4E95dBc7E8C99c114FF9C8299A3E4851e1530fF dan
    // dibuktikan ulang dengan bisection di fork Base Sepolia. ABI paket SDK acp-node-v2 TIDAK boleh
    // dipakai sebagai sumber lagi: ia subset basi dan tidak memuat `EVALUATOR_GRACE_PERIOD()`.
    // ====================================================================

    /// Konstanta PUBLIK on-chain, nama persis. `cast call <ACP> "EVALUATOR_GRACE_PERIOD()(uint256)"` → 900.
    function test_evaluatorGracePeriod_isPublicConstant900() public view {
        assertEq(acp.EVALUATOR_GRACE_PERIOD(), 900, "EVALUATOR_GRACE_PERIOD = 900 detik (15 menit)");
    }

    /// Sisi HIJAU bisection: tepat `expiredAt + 900` SUKSES, oleh pemanggil acak. Status → Expired(5),
    /// client menerima 100% budget, provider NOL. Sesudah itu verdict vault jadi YATIM: `complete` DAN
    /// `reject` oleh evaluator sama-sama revert `WrongStatus()`.
    function test_claimRefund_fromSubmitted_atGrace_succeeds_andOrphansVerdict() public {
        uint256 jobId = _submittedJob(evaluator);
        uint256 expiredAt = uint256(acp.getJob(jobId).expiredAt);
        vm.warp(expiredAt + 900);

        vm.recordLogs();
        vm.prank(stranger);
        acp.claimRefund(jobId);

        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 2, "2 log ACP: Refunded lalu JobExpired");
        assertEq(logs[0].topics[0], T_REFUNDED, "urutan 1: Refunded");
        assertEq(logs[1].topics[0], T_JOB_EXPIRED, "urutan 2: JobExpired");

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Expired), "status Expired(5)");
        assertEq(usdc.balanceOf(client), 100_000_000, "client menerima 100% budget");
        assertEq(usdc.balanceOf(provider), 0, "provider NOL walaupun sudah submit");
        assertEq(usdc.balanceOf(address(acp)), 0, "escrow kosong");

        vm.prank(evaluator);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.complete(jobId, REASON, "");

        vm.prank(evaluator);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.reject(jobId, REASON, "");
    }

    /// Anchor tenggang = `expiredAt`, BUKAN waktu submit. Dua arah dikunci sekaligus:
    /// (a) submit SANGAT AWAL lalu refund pada `submitTime + 900` yang masih < `expiredAt` → `WrongStatus()`;
    /// (b) submit tepat di `expiredAt - 1` tetap gagal di `expiredAt + 899` dan sukses di `expiredAt + 900`.
    function test_claimRefund_graceAnchoredToExpiredAt_notSubmitTime() public {
        // (a) submit di detik pertama; +900 dari waktu submit masih jauh sebelum expiredAt.
        uint256 early = _submittedJob(evaluator);
        uint256 submitTime = block.timestamp;
        uint256 earlyExpiredAt = uint256(acp.getJob(early).expiredAt);
        assertLt(submitTime + 900, earlyExpiredAt, "prasyarat: submitTime+900 masih sebelum expiredAt");

        vm.warp(submitTime + 900);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.claimRefund(early);

        // (b) job lain yang di-submit tepat sedetik sebelum expiredAt.
        uint256 late = _fundedJob(evaluator);
        uint256 lateExpiredAt = uint256(acp.getJob(late).expiredAt);
        vm.warp(lateExpiredAt - 1);
        vm.prank(provider);
        acp.submit(late, DELIVERABLE, "");

        vm.warp(lateExpiredAt + 899);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.claimRefund(late);

        vm.warp(lateExpiredAt + 900);
        vm.prank(stranger);
        acp.claimRefund(late);
        assertEq(uint8(_status(late)), uint8(AgenticCommerce.Status.Expired), "sukses tepat di +900");
    }

    /// Dari Open/Funded TIDAK ada tenggang sama sekali: `expiredAt - 1` revert; `+0/+1/+899/+900` sukses.
    /// Kalau tenggang 900 bocor ke jalur Funded, keempat panggilan pertama akan gagal.
    function test_claimRefund_fromFunded_hasNoGracePeriod() public {
        uint256 tooEarly = _fundedJob(evaluator);
        vm.warp(uint256(acp.getJob(tooEarly).expiredAt) - 1);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.claimRefund(tooEarly);

        uint256[4] memory offsets = [uint256(0), 1, 899, 900];
        for (uint256 i; i < offsets.length; ++i) {
            uint256 jobId = _fundedJob(evaluator);
            uint256 expiredAt = uint256(acp.getJob(jobId).expiredAt);
            vm.warp(expiredAt + offsets[i]);

            vm.prank(stranger);
            acp.claimRefund(jobId);
            assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Expired), "Funded: sukses tanpa tenggang");
        }
        // Job `tooEarly` sengaja dibiarkan Funded: 10 USDC-nya masih di escrow, sisanya sudah kembali.
        assertEq(usdc.balanceOf(address(acp)), BUDGET, "hanya escrow job yang belum expired yang tersisa");
        assertEq(usdc.balanceOf(client), 90_000_000, "keempat refund kembali ke client");
    }

    /// Dari Open: SUKSES pada `now >= expiredAt` tetapi TANPA transfer — escrow memang belum pernah terisi.
    /// Varian kedua sengaja memanggil `setBudget` lebih dulu: `budget != 0` TIDAK berarti uang sudah masuk,
    /// jadi implementasi yang memakai `job.budget` apa adanya akan mencoba mengirim USDC yang tidak ada.
    function test_claimRefund_fromOpen_succeedsWithoutTransfer() public {
        uint256 bare = _createJob(evaluator);
        uint256 bareExpiredAt = uint256(acp.getJob(bare).expiredAt);

        vm.warp(bareExpiredAt - 1);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.claimRefund(bare);

        vm.warp(bareExpiredAt);
        vm.recordLogs();
        vm.prank(stranger);
        acp.claimRefund(bare);

        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 1, "jalur Open: hanya JobExpired (tidak ada Refunded beramount nol)");
        assertEq(logs[0].topics[0], T_JOB_EXPIRED, "topic0 JobExpired");
        assertEq(uint8(_status(bare)), uint8(AgenticCommerce.Status.Expired), "status Expired");
        assertEq(usdc.balanceOf(address(acp)), 0, "escrow tetap kosong");
        assertEq(usdc.balanceOf(client), 100_000_000, "saldo client tidak berubah");

        uint256 priced = _createJob(evaluator);
        vm.prank(provider);
        acp.setBudget(priced, BUDGET, "");
        assertEq(acp.getJob(priced).budget, BUDGET, "budget terpasang tanpa fund");

        vm.warp(uint256(acp.getJob(priced).expiredAt));
        vm.prank(stranger);
        acp.claimRefund(priced);

        assertEq(uint8(_status(priced)), uint8(AgenticCommerce.Status.Expired), "status Expired");
        assertEq(usdc.balanceOf(client), 100_000_000, "tetap tidak ada transfer dari escrow kosong");
    }

    /// Completed/Rejected/Expired → SELALU `WrongStatus()`, termasuk untuk mencegah refund GANDA.
    function test_claimRefund_terminalStates_alwaysRevert() public {
        uint256 completed = _submittedJob(evaluator);
        vm.prank(evaluator);
        acp.complete(completed, REASON, "");

        uint256 rejected = _fundedJob(evaluator);
        vm.prank(evaluator);
        acp.reject(rejected, REASON, "");

        uint256 expired = _fundedJob(evaluator);
        vm.warp(uint256(acp.getJob(expired).expiredAt) + 10_000);
        vm.prank(stranger);
        acp.claimRefund(expired);
        assertEq(uint8(_status(expired)), uint8(AgenticCommerce.Status.Expired), "sudah Expired");

        uint256 balanceBefore = usdc.balanceOf(client);
        uint256 escrowBefore = usdc.balanceOf(address(acp));

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.claimRefund(completed);

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.claimRefund(rejected);

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.claimRefund(expired);

        assertEq(usdc.balanceOf(client), balanceBefore, "tidak ada refund ganda");
        assertEq(usdc.balanceOf(address(acp)), escrowBefore, "escrow tidak bergerak");
    }

    // ====================================================================
    // Urutan cek: status/waktu SEBELUM otorisasi
    // ====================================================================

    /// `setProvider` mengecek STATUS lalu WAKTU, keduanya SEBELUM `msg.sender != client`. Buktinya:
    /// pihak ASING pun menerima `WrongStatus()` (bukan `Unauthorized()`) pada job yang statusnya salah
    /// atau sudah lewat `expiredAt`. Catatan lama "tidak ada cek status di setProvider" SALAH.
    function test_setProvider_checkOrder_statusAndExpiryBeforeAuthorization() public {
        vm.prank(client);
        uint256 rejectedJob =
            acp.createJob(address(0), evaluator, block.timestamp + 1 hours, "job tanpa provider", address(0));
        vm.prank(client);
        acp.reject(rejectedJob, REASON, "");
        assertEq(uint8(_status(rejectedJob)), uint8(AgenticCommerce.Status.Rejected), "status Rejected");

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.setProvider(rejectedJob, provider);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.setProvider(rejectedJob, provider);

        vm.prank(client);
        uint256 openJob =
            acp.createJob(address(0), evaluator, block.timestamp + 1 hours, "job tanpa provider", address(0));
        vm.warp(uint256(acp.getJob(openJob).expiredAt));

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.setProvider(openJob, provider);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.setProvider(openJob, provider);
    }

    /// Dua error terakhir dalam rantai `setProvider` (api-facts §A): `provider_ == client` →
    /// `ClientIsProvider()` 0x332ff0f9; `provider_ == evaluator` → `EvaluatorIsProvider()` 0xc7b4e9eb.
    /// Keduanya TIDAK ada di ABI paket SDK — jangan simpulkan ketiadaannya dari sana.
    function test_setProvider_identityGuards() public {
        vm.prank(client);
        uint256 jobId =
            acp.createJob(address(0), evaluator, block.timestamp + 1 hours, "job tanpa provider", address(0));

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ClientIsProvider.selector);
        acp.setProvider(jobId, client);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.EvaluatorIsProvider.selector);
        acp.setProvider(jobId, evaluator);

        vm.prank(client);
        acp.setProvider(jobId, provider);
        assertEq(acp.getJob(jobId).provider, provider, "provider sah tetap bisa dipasang");
    }

    /// `complete` mengecek STATUS DULU, BARU otorisasi (fork 2026-09-03). Mock yang membalik urutannya
    /// akan menjawab `Unauthorized()` pada baris pertama — persis penyimpangan yang dijaga tes ini.
    /// Baris terakhir adalah KONTROL: pada status Submitted, non-evaluator tetap `Unauthorized()` di
    /// kedua urutan, jadi ia membuktikan tes ini tidak sekadar menuntut `WrongStatus()` di mana-mana.
    function test_complete_checkOrder_statusBeforeAuthorization() public {
        uint256 fundedJob = _fundedJob(evaluator);

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.complete(fundedJob, REASON, "");

        vm.prank(evaluator);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.complete(fundedJob, REASON, "");

        uint256 submittedJob = _submittedJob(evaluator);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.complete(submittedJob, REASON, "");
    }

    // ====================================================================
    // createJob — batas atas expiredAt + guard identitas
    // ====================================================================

    /// `expiredAt > type(uint48).max` → revert `ExpiryTooShort()` (BUKAN truncation diam-diam).
    /// Tepat `type(uint48).max` SUKSES. Implementasi lama memotong nilainya dan menyimpan expiredAt palsu.
    function test_createJob_expiredAtUpperBound_isUint48Max() public {
        uint256 max48 = uint256(type(uint48).max);

        vm.prank(client);
        uint256 jobId = acp.createJob(provider, evaluator, max48, "tepat di batas uint48", address(0));
        assertEq(uint256(acp.getJob(jobId).expiredAt), max48, "expiredAt tersimpan utuh");

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ExpiryTooShort.selector);
        acp.createJob(provider, evaluator, max48 + 1, "2**48", address(0));

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ExpiryTooShort.selector);
        acp.createJob(provider, evaluator, type(uint256).max, "uint256 max", address(0));
    }

    /// Guard identitas `createJob` (api-facts §A, dibuktikan di fork): `msg.sender == provider` →
    /// `ClientIsProvider()`; `evaluator != 0 && evaluator == provider` → `EvaluatorIsProvider()`.
    /// Baris terakhir mengunci bahwa guard kedua TIDAK menyala saat keduanya `address(0)`.
    function test_createJob_identityGuards() public {
        uint256 expiredAt = block.timestamp + 1 hours;

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ClientIsProvider.selector);
        acp.createJob(client, evaluator, expiredAt, "client == provider", address(0));

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.EvaluatorIsProvider.selector);
        acp.createJob(provider, provider, expiredAt, "evaluator == provider", address(0));

        vm.prank(client);
        uint256 jobId = acp.createJob(address(0), address(0), expiredAt, "keduanya nol = sah", address(0));
        assertEq(acp.getJob(jobId).provider, address(0), "provider nol sah");
        assertEq(acp.getJob(jobId).evaluator, address(0), "evaluator nol sah");
    }

    // ====================================================================
    // reject — matriks otorisasi lengkap
    // ====================================================================

    /// Saat Open: client ATAU provider. Catatan lama "saat Open hanya client" SALAH (fork 2026-09-03).
    /// `JobRejected.rejector` = `msg.sender` APA ADANYA, bukan `job.client`: pada cabang Open kedua
    /// pihak bisa jadi penolak, jadi indexer yang menyamakan rejector dengan client akan salah atribusi.
    function test_reject_open_byProviderOrClient_succeeds() public {
        uint256 byProvider = _createJob(evaluator);
        vm.recordLogs();
        vm.prank(provider);
        acp.reject(byProvider, REASON, "");
        assertEq(uint8(_status(byProvider)), uint8(AgenticCommerce.Status.Rejected), "provider boleh menolak Open");

        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 1, "Open: hanya JobRejected");
        assertEq(logs[0].topics[0], T_JOB_REJECTED, "topic0 JobRejected");
        assertEq(address(uint160(uint256(logs[0].topics[2]))), provider, "rejector = provider, BUKAN client");
        assertEq(abi.decode(logs[0].data, (bytes32)), REASON, "JobRejected.reason di data");

        uint256 byClient = _createJob(evaluator);
        vm.prank(client);
        acp.reject(byClient, REASON, "");
        assertEq(uint8(_status(byClient)), uint8(AgenticCommerce.Status.Rejected), "client boleh menolak Open");

        uint256 byStranger = _createJob(evaluator);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.reject(byStranger, REASON, "");
    }

    /// Funded dengan `evaluator == 0`: client ATAU provider boleh menolak; pihak asing `Unauthorized()`.
    /// (Kombinasi "Submitted + evaluator == 0" tidak bisa dicapai: `submit` tanpa evaluator langsung
    /// menyelesaikan job — lihat `test_submit_withoutEvaluator_autoCompletes`.)
    function test_reject_fundedWithoutEvaluator_byClientOrProvider() public {
        uint256 byClient = _fundedJob(address(0));

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.reject(byClient, REASON, "");

        vm.prank(client);
        acp.reject(byClient, REASON, "");
        assertEq(uint8(_status(byClient)), uint8(AgenticCommerce.Status.Rejected), "client boleh saat evaluator nol");
        assertEq(usdc.balanceOf(client), 100_000_000, "refund 100%");

        uint256 byProvider = _fundedJob(address(0));
        vm.prank(provider);
        acp.reject(byProvider, REASON, "");
        assertEq(
            uint8(_status(byProvider)), uint8(AgenticCommerce.Status.Rejected), "provider boleh saat evaluator nol"
        );
    }

    /// Funded/Submitted dengan `evaluator != 0`: HANYA evaluator. Provider pun ditolak.
    function test_reject_withEvaluator_onlyEvaluator() public {
        uint256 fundedJob = _fundedJob(evaluator);
        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.reject(fundedJob, REASON, "");

        uint256 submittedJob = _submittedJob(evaluator);
        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.reject(submittedJob, REASON, "");

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.reject(submittedJob, REASON, "");

        vm.prank(evaluator);
        acp.reject(submittedJob, REASON, "");
        assertEq(uint8(_status(submittedJob)), uint8(AgenticCommerce.Status.Rejected), "evaluator berhasil");
    }

    /// Status selain Open/Funded/Submitted → `WrongStatus()`, siapa pun pemanggilnya.
    function test_reject_terminalStates_revertWrongStatus() public {
        uint256 completed = _submittedJob(evaluator);
        vm.prank(evaluator);
        acp.complete(completed, REASON, "");

        uint256 rejected = _fundedJob(evaluator);
        vm.prank(evaluator);
        acp.reject(rejected, REASON, "");

        uint256 expired = _fundedJob(evaluator);
        vm.warp(uint256(acp.getJob(expired).expiredAt));
        vm.prank(stranger);
        acp.claimRefund(expired);

        vm.prank(evaluator);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.reject(completed, REASON, "");

        vm.prank(evaluator);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.reject(rejected, REASON, "");

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.reject(expired, REASON, "");
    }

    // ====================================================================
    // setBudget — guard waktu
    // ====================================================================

    /// `setBudget` boleh berulang selagi Open DAN `now < expiredAt`; tepat pada `expiredAt` → `WrongStatus()`.
    function test_setBudget_atExpiredAt_reverts() public {
        uint256 jobId = _createJob(evaluator);
        uint256 expiredAt = uint256(acp.getJob(jobId).expiredAt);

        vm.warp(expiredAt - 1);
        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");
        assertEq(acp.getJob(jobId).budget, BUDGET, "sedetik sebelum expiredAt masih boleh");

        vm.warp(expiredAt);
        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.setBudget(jobId, BUDGET + 1, "");
        assertEq(acp.getJob(jobId).budget, BUDGET, "budget tidak berubah");
    }

    // ====================================================================
    // Reentrancy — meniru ReentrancyGuardTransient milik ACP asli
    //
    // Kontrak asli mewarisi `ReentrancyGuardTransient`: SATU slot transient dipakai bersama, sehingga
    // guard berlaku LINTAS FUNGSI dalam satu tx. Tanpa tiruan ini, tes vault (task 1.2) bisa lulus
    // dengan mengandalkan reentrancy yang di produksi MUSTAHIL.
    // ====================================================================

    /// @dev Rangkaian ACP terpisah yang memakai token penyerang sebagai `paymentToken`.
    function _reentrantSetup() internal returns (ReentrantToken token, AgenticCommerce acp2) {
        token = new ReentrantToken();
        acp2 = new AgenticCommerce(address(token), treasury);
        token.setAcp(acp2);
        token.mint(client, 100_000_000);
        vm.prank(client);
        token.approve(address(acp2), type(uint256).max);
    }

    /// Masuk lewat `fund` → `transferFrom` → `claimRefund` pada job LAIN yang sah untuk di-refund.
    /// Tanpa guard, panggilan kedua itu SUKSES; dengan guard lintas fungsi ia revert
    /// `ReentrancyGuardReentrantCall()` 0x3ee5aeb5 dan seluruh tx ikut batal.
    /// KONTROL di akhir: `claimRefund` yang SAMA dipanggil di luar reentrancy dan SUKSES — jadi revert
    /// di atas benar-benar berasal dari guard, bukan dari status job.
    function test_reentrancy_guardIsCrossFunction() public {
        (ReentrantToken token, AgenticCommerce acp2) = _reentrantSetup();

        vm.prank(client);
        uint256 victim = acp2.createJob(provider, evaluator, block.timestamp + 1 hours, "korban", address(0));
        vm.prank(provider);
        acp2.setBudget(victim, BUDGET, "");
        vm.prank(client);
        acp2.fund(victim, BUDGET, "");

        vm.prank(client);
        uint256 carrier = acp2.createJob(provider, evaluator, block.timestamp + 2 hours, "pembawa", address(0));
        vm.prank(provider);
        acp2.setBudget(carrier, BUDGET, "");

        vm.warp(uint256(acp2.getJob(victim).expiredAt));
        token.arm(ReentrantToken.Mode.ClaimRefund, victim, address(0), 0);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ReentrancyGuardReentrantCall.selector);
        acp2.fund(carrier, BUDGET, "");

        assertEq(uint8(acp2.getJob(carrier).status), uint8(AgenticCommerce.Status.Open), "fund ikut batal");
        assertEq(uint8(acp2.getJob(victim).status), uint8(AgenticCommerce.Status.Funded), "korban tidak berubah");

        // KONTROL: panggilan yang sama tanpa reentrancy memang sah. Perlu dilucuti dulu — `mode` di token
        // ikut ter-rollback bersama tx yang revert di atas, jadi tanpa ini kontrolnya sendiri akan menyerang.
        token.arm(ReentrantToken.Mode.None, 0, address(0), 0);
        vm.prank(stranger);
        acp2.claimRefund(victim);
        assertEq(uint8(acp2.getJob(victim).status), uint8(AgenticCommerce.Status.Expired), "kontrol: sah di luar tx");
    }

    /// `setProvider` adalah SATU-SATUNYA fungsi alur job yang TIDAK `nonReentrant` di kontrak asli
    /// (api-facts §A). Tes ini menahan godaan "sekalian dijaga semua": memasang guard di sana membuat
    /// mock lebih ketat dari ACP nyata dan menyembunyikan bug vault.
    function test_reentrancy_setProviderIsNotGuarded() public {
        (ReentrantToken token, AgenticCommerce acp2) = _reentrantSetup();

        uint256 tokenJob = token.createJobAsClient(address(0), evaluator, block.timestamp + 1 hours);

        vm.prank(client);
        uint256 carrier = acp2.createJob(provider, evaluator, block.timestamp + 1 hours, "pembawa", address(0));
        vm.prank(provider);
        acp2.setBudget(carrier, BUDGET, "");

        token.arm(ReentrantToken.Mode.SetProvider, tokenJob, provider, 0);

        vm.prank(client);
        acp2.fund(carrier, BUDGET, "");

        assertEq(uint8(acp2.getJob(carrier).status), uint8(AgenticCommerce.Status.Funded), "fund tetap sukses");
        assertEq(acp2.getJob(tokenJob).provider, provider, "setProvider dari dalam reentrancy BERHASIL");
    }

    // ====================================================================
    // Kunci LAYOUT ABI (bukan sekadar selector/topic0)
    //
    // Selector `getJob(uint256)` tidak memuat tipe kembalian, dan topic0 `JobCreated` tidak berubah
    // saat dua argumen bertipe sama tertukar. Jadi kedua tes lama BUTA terhadap pertukaran field.
    // Dua tes di bawah mengunci urutan field ke nilai LITERAL yang sengaja dibuat berbeda satu sama
    // lain, karena pertukaran field akan lolos semua tes lain lalu di Sepolia membuat vault membaca
    // `hook` sebagai `evaluator` dan watcher memungut job milik orang lain.
    // Urutan resmi: api-facts §A tuple `(address,uint8,address,uint48,address,address,uint256,string)`
    // dan `JobCreated(uint256 indexed, address indexed, address indexed, address evaluator,
    // uint256 expiredAt, address hook)`.
    // ====================================================================

    /// @dev Alamat sentinel: pola berulang yang mustahil tertukar diam-diam saat dibaca manusia.
    address internal constant S_CLIENT = 0x1111111111111111111111111111111111111111;
    address internal constant S_PROVIDER = 0x2222222222222222222222222222222222222222;
    address internal constant S_EVALUATOR = 0x3333333333333333333333333333333333333333;
    address internal constant S_HOOK = 0x4444444444444444444444444444444444444444;
    /// @dev Nilai numerik sentinel, sengaja berbeda satu sama lain dan bukan kelipatan satu sama lain.
    uint256 internal constant S_EXPIRED_AT = 1_006_666; // setUp() warp ke 1_000_000, jadi > now + 300
    uint256 internal constant S_BUDGET = 5_555_555;
    string internal constant S_DESCRIPTION = "layout-sentinel";

    /// @dev Ambil word ke-`index` dari returndata mentah tanpa assembly.
    function _word(bytes memory data, uint256 index) internal pure returns (bytes32 w) {
        uint256 start = index * 32;
        require(data.length >= start + 32, "returndata lebih pendek dari yang diharapkan");
        for (uint256 i; i < 32; ++i) {
            w |= bytes32(uint256(uint8(data[start + i])) << (8 * (31 - i)));
        }
    }

    /// @dev Potong `count` byte pertama dari returndata. `getJob` mengembalikan struct DINAMIS, jadi
    ///      returndata diawali satu word offset (0x20); tuple itu sendiri baru mulai sesudahnya.
    function _tail(bytes memory data, uint256 count) internal pure returns (bytes memory out) {
        out = new bytes(data.length - count);
        for (uint256 i; i < out.length; ++i) {
            out[i] = data[i + count];
        }
    }

    /// @dev Job dengan SEMUA field bernilai sentinel berbeda, dibawa sampai status Submitted (=2)
    ///      supaya `status` juga tidak nol dan tidak bisa tertukar dengan field lain yang kebetulan nol.
    function _sentinelJob() internal returns (uint256 jobId) {
        usdc.mint(S_CLIENT, S_BUDGET);
        vm.prank(S_CLIENT);
        usdc.approve(address(acp), type(uint256).max);
        acp.mockSetHookWhitelist(S_HOOK, true);

        vm.prank(S_CLIENT);
        jobId = acp.createJob(S_PROVIDER, S_EVALUATOR, S_EXPIRED_AT, S_DESCRIPTION, S_HOOK);
        vm.prank(S_PROVIDER);
        acp.setBudget(jobId, S_BUDGET, "");
        vm.prank(S_CLIENT);
        acp.fund(jobId, S_BUDGET, "");
        vm.prank(S_PROVIDER);
        acp.submit(jobId, DELIVERABLE, "");
    }

    /// Mengunci RETURNDATA MENTAH `getJob(uint256)` word demi word ke tuple ABI asli
    /// `(address,uint8,address,uint48,address,address,uint256,string)` (api-facts §A).
    /// `test_selectors_matchAcpAbi` TIDAK menutup ini: selector fungsi tidak mengandung tipe kembalian,
    /// jadi struct dengan field tertukar tetap memberi selector 0xbf22c457 yang sama.
    function test_getJob_returndataLayout_matchesAcpTuple() public {
        uint256 jobId = _sentinelJob();

        (bool ok, bytes memory ret) = address(acp).staticcall(abi.encodeWithSelector(bytes4(0xbf22c457), jobId));
        assertTrue(ok, "getJob harus sukses");

        // 8 field + offset tuple + offset string + panjang string + 1 word isi string.
        assertEq(ret.length, 11 * 32, "panjang returndata getJob");

        assertEq(uint256(_word(ret, 0)), 32, "word0 = offset tuple dinamis (0x20)");
        assertEq(address(uint160(uint256(_word(ret, 1)))), S_CLIENT, "word1 = client (BUKAN provider)");
        assertEq(uint256(_word(ret, 2)), uint256(uint8(AgenticCommerce.Status.Submitted)), "word2 = status (uint8)");
        assertEq(address(uint160(uint256(_word(ret, 3)))), S_PROVIDER, "word3 = provider (BUKAN client)");
        assertEq(uint256(_word(ret, 4)), S_EXPIRED_AT, "word4 = expiredAt (uint48)");
        assertEq(address(uint160(uint256(_word(ret, 5)))), S_EVALUATOR, "word5 = evaluator (BUKAN hook)");
        assertEq(address(uint160(uint256(_word(ret, 6)))), S_HOOK, "word6 = hook (BUKAN evaluator)");
        assertEq(uint256(_word(ret, 7)), S_BUDGET, "word7 = budget");
        assertEq(uint256(_word(ret, 8)), 8 * 32, "word8 = offset string relatif awal tuple");
        assertEq(uint256(_word(ret, 9)), bytes(S_DESCRIPTION).length, "word9 = panjang description");
        assertEq(_word(ret, 10), bytes32(bytes(S_DESCRIPTION)), "word10 = isi description");

        // Dekode ulang dengan tuple tipe EKSPLISIT (bukan lewat `AgenticCommerce.Job`, yang ikut
        // berubah bila struct dimutasi) — inilah bentuk yang akan dideklarasikan ulang EvaluatorVault.
        (
            address client_,
            uint8 status_,
            address provider_,
            uint48 expiredAt_,
            address evaluator_,
            address hook_,
            uint256 budget_,
            string memory description_
        ) = abi.decode(_tail(ret, 32), (address, uint8, address, uint48, address, address, uint256, string));

        assertEq(client_, S_CLIENT, "field 1 client");
        assertEq(uint256(status_), 2, "field 2 status = Submitted");
        assertEq(provider_, S_PROVIDER, "field 3 provider");
        assertEq(uint256(expiredAt_), S_EXPIRED_AT, "field 4 expiredAt");
        assertEq(evaluator_, S_EVALUATOR, "field 5 evaluator");
        assertEq(hook_, S_HOOK, "field 6 hook");
        assertEq(budget_, S_BUDGET, "field 7 budget");
        assertEq(description_, S_DESCRIPTION, "field 8 description");
    }

    /// Mengunci isi `JobCreated.data` ke `(address evaluator, uint256 expiredAt, address hook)`.
    /// topic0 tidak bisa mendeteksi pertukaran ini (urutan tipe tetap sama), padahal watcher (task 2.2)
    /// WAJIB mengambil `evaluator` dari `data` — ia tidak `indexed` (api-facts §A).
    function test_jobCreatedData_matchesAcpArgumentOrder() public {
        acp.mockSetHookWhitelist(S_HOOK, true);

        vm.recordLogs();
        vm.prank(S_CLIENT);
        uint256 jobId = acp.createJob(S_PROVIDER, S_EVALUATOR, S_EXPIRED_AT, S_DESCRIPTION, S_HOOK);

        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 1, "hanya JobCreated");
        assertEq(logs[0].topics[0], T_JOB_CREATED, "topic0 JobCreated");
        assertEq(logs[0].topics.length, 4, "3 argumen indexed: jobId, client, provider");
        assertEq(uint256(logs[0].topics[1]), jobId, "topic1 = jobId");
        assertEq(address(uint160(uint256(logs[0].topics[2]))), S_CLIENT, "topic2 = client");
        assertEq(address(uint160(uint256(logs[0].topics[3]))), S_PROVIDER, "topic3 = provider");

        assertEq(logs[0].data.length, 3 * 32, "data = tepat 3 argumen non-indexed");
        assertEq(address(uint160(uint256(_word(logs[0].data, 0)))), S_EVALUATOR, "data word0 = evaluator");
        assertEq(uint256(_word(logs[0].data, 1)), S_EXPIRED_AT, "data word1 = expiredAt");
        assertEq(address(uint160(uint256(_word(logs[0].data, 2)))), S_HOOK, "data word2 = hook");

        (address evaluator_, uint256 expiredAt_, address hook_) = abi.decode(logs[0].data, (address, uint256, address));
        assertEq(evaluator_, S_EVALUATOR, "abi.decode: evaluator lebih dulu (BUKAN hook)");
        assertEq(expiredAt_, S_EXPIRED_AT, "abi.decode: expiredAt di tengah");
        assertEq(hook_, S_HOOK, "abi.decode: hook terakhir");
    }

    /// Mengunci NAMA + urutan argumen di ABI JSON hasil build. Ini menutup celah terakhir: menukar dua
    /// argumen bertipe sama HANYA pada deklarasi (mis. `address hook` sebelum `address evaluator`)
    /// tidak mengubah topic0, tidak mengubah returndata, dan tidak terdeteksi `abi.decode` mana pun —
    /// Solidity mendekode per POSISI. Tetapi watcher (task 2.2, web3.py) dan web (viem) mendekode per
    /// NAMA dari ABI JSON, jadi pertukaran itu membuat mereka membaca `hook` sebagai `evaluator`.
    /// Nilai acuan: api-facts §A.
    function test_abiJson_argumentNames_matchAcpAbi() public view {
        string memory json =
            vm.readFile(string.concat(vm.projectRoot(), "/out/AgenticCommerce.sol/AgenticCommerce.json"));

        string[] memory eventNames =
            abi.decode(vm.parseJson(json, "$.abi[?(@.name == 'JobCreated')].inputs[*].name"), (string[]));
        string[] memory eventTypes =
            abi.decode(vm.parseJson(json, "$.abi[?(@.name == 'JobCreated')].inputs[*].type"), (string[]));
        bool[] memory eventIndexed =
            abi.decode(vm.parseJson(json, "$.abi[?(@.name == 'JobCreated')].inputs[*].indexed"), (bool[]));

        string[6] memory expectedEventNames = ["jobId", "client", "provider", "evaluator", "expiredAt", "hook"];
        string[6] memory expectedEventTypes = ["uint256", "address", "address", "address", "uint256", "address"];
        bool[6] memory expectedEventIndexed = [true, true, true, false, false, false];

        assertEq(eventNames.length, 6, "JobCreated punya 6 argumen");
        assertEq(eventTypes.length, 6, "JobCreated punya 6 tipe");
        assertEq(eventIndexed.length, 6, "JobCreated punya 6 flag indexed");
        for (uint256 i; i < 6; ++i) {
            assertEq(eventNames[i], expectedEventNames[i], "urutan nama argumen JobCreated");
            assertEq(eventTypes[i], expectedEventTypes[i], "urutan tipe argumen JobCreated");
            assertEq(eventIndexed[i], expectedEventIndexed[i], "daftar indexed JobCreated");
        }

        string[] memory fieldNames =
            abi.decode(vm.parseJson(json, "$.abi[?(@.name == 'getJob')].outputs[0].components[*].name"), (string[]));
        string[] memory fieldTypes =
            abi.decode(vm.parseJson(json, "$.abi[?(@.name == 'getJob')].outputs[0].components[*].type"), (string[]));

        string[8] memory expectedFieldNames =
            ["client", "status", "provider", "expiredAt", "evaluator", "hook", "budget", "description"];
        string[8] memory expectedFieldTypes =
            ["address", "uint8", "address", "uint48", "address", "address", "uint256", "string"];

        assertEq(fieldNames.length, 8, "struct Job punya 8 field");
        assertEq(fieldTypes.length, 8, "struct Job punya 8 tipe");
        for (uint256 i; i < 8; ++i) {
            assertEq(fieldNames[i], expectedFieldNames[i], "urutan nama field struct Job");
            assertEq(fieldTypes[i], expectedFieldTypes[i], "urutan tipe field struct Job");
        }
    }

    // ====================================================================
    // submit — transisi Open→Submitted/Completed untuk job BERBUDGET NOL
    //
    // Sumber: source TERVERIFIKASI Sourcify `exact_match` AgenticCommerceV3.sol:456-459 —
    //   if (job.status != Funded && (job.status != Open || job.budget > 0)) revert WrongStatus();
    // dan docs/api-facts.md §A ("juga menerima Open→Completed bila budget == 0 & evaluator == 0").
    // Mock yang hanya menerima Funded MENYEMBUNYIKAN kanal nyata: job tanpa `fund` sepeser pun bisa
    // langsung Submitted/Completed → memory-poisoning berbiaya nol untuk vault (task 1.2).
    // ====================================================================

    /// (a) Open + budget 0 + `evaluator != 0` → **Submitted**, TANPA escrow. Lalu `complete` oleh
    ///     evaluator tetap SUKSES: job mencapai Completed tanpa satu sen pun pernah masuk escrow.
    function test_submit_fromOpen_zeroBudget_withEvaluator_becomesSubmitted() public {
        uint256 jobId = _createJob(evaluator);
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Open), "prasyarat: masih Open");
        assertEq(acp.getJob(jobId).budget, 0, "prasyarat: budget 0");
        assertEq(usdc.balanceOf(address(acp)), 0, "prasyarat: escrow kosong");

        vm.recordLogs();
        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");

        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 1, "hanya JobSubmitted (bukan jalur auto-complete)");
        assertEq(logs[0].topics[0], T_JOB_SUBMITTED, "topic0 JobSubmitted");
        assertEq(abi.decode(logs[0].data, (bytes32)), DELIVERABLE, "JobSubmitted.deliverable");

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Submitted), "Open-ke-Submitted tanpa fund");
        assertEq(usdc.balanceOf(address(acp)), 0, "tetap tanpa escrow");

        // Inilah kanal yang harus terlihat: verdict evaluator dieksekusi atas job tanpa uang.
        vm.prank(evaluator);
        acp.complete(jobId, REASON, "");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Completed), "complete sukses tanpa escrow");
        assertEq(usdc.balanceOf(provider), 0, "tidak ada pembayaran");
        assertEq(usdc.balanceOf(evaluator), 0, "tidak ada fee evaluator");
    }

    /// (b) Open + budget 0 + `evaluator == 0` → **Completed** lewat jalur auto-complete.
    function test_submit_fromOpen_zeroBudget_withoutEvaluator_autoCompletes() public {
        vm.prank(client);
        uint256 jobId =
            acp.createJob(provider, address(0), block.timestamp + 1 hours, "job tanpa evaluator", address(0));

        vm.recordLogs();
        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");

        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 3, "JobSubmitted, JobCompleted, PaymentReleased");
        assertEq(logs[0].topics[0], T_JOB_SUBMITTED, "urutan 1: JobSubmitted");
        assertEq(logs[1].topics[0], T_JOB_COMPLETED, "urutan 2: JobCompleted");
        assertEq(address(uint160(uint256(logs[1].topics[2]))), address(0), "JobCompleted.evaluator = address(0)");
        assertEq(abi.decode(logs[1].data, (bytes32)), DELIVERABLE, "JobCompleted.reason = deliverable");
        assertEq(logs[2].topics[0], T_PAYMENT_RELEASED, "urutan 3: PaymentReleased");
        assertEq(abi.decode(logs[2].data, (uint256)), 0, "PaymentReleased.amount = 0 (tidak ada escrow)");

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Completed), "Open-ke-Completed tanpa fund");
        assertEq(usdc.balanceOf(provider), 0, "tidak ada pembayaran");
        assertEq(usdc.balanceOf(treasury), 0, "tidak ada platform fee");
    }

    /// (c) KONTROL NEGATIF: Open + budget > 0 (sudah `setBudget`, belum `fund`) → `WrongStatus()`.
    ///     Batasnya STRICT `> 0`: budget 1 pun ditolak, budget 0 diterima.
    function test_submit_fromOpen_withBudget_revertsWrongStatus() public {
        uint256 jobId = _createJob(evaluator);

        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");
        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.submit(jobId, DELIVERABLE, "");

        vm.prank(provider);
        acp.setBudget(jobId, 1, "");
        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.submit(jobId, DELIVERABLE, "");

        // KONTROL: turunkan lagi ke 0 → submit yang SAMA sukses, jadi revert di atas benar-benar
        // berasal dari `budget > 0` dan bukan dari status Open itu sendiri.
        vm.prank(provider);
        acp.setBudget(jobId, 0, "");
        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Submitted), "budget 0 boleh submit");
    }

    /// Guard expiry berlaku juga di jalur Open berbudget nol: tepat pada `expiredAt` → `WrongStatus()`.
    function test_submit_fromOpen_zeroBudget_atExpiredAt_reverts() public {
        uint256 jobId = _createJob(evaluator);
        uint256 expiredAt = uint256(acp.getJob(jobId).expiredAt);

        vm.warp(expiredAt);
        vm.prank(provider);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.submit(jobId, DELIVERABLE, "");

        vm.warp(expiredAt - 1);
        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Submitted), "sedetik sebelumnya masih boleh");
    }

    /// `submit` mengecek STATUS lalu WAKTU, keduanya SEBELUM otorisasi (source :455-461).
    /// Pihak ASING menerima `WrongStatus()` pada job berstatus salah / lewat waktu — berbeda dari
    /// `fund`, di mana otorisasi menang atas expiry (api-facts §A, tabel "selector pemenang").
    function test_submit_checkOrder_statusAndExpiryBeforeAuthorization() public {
        uint256 completed = _submittedJob(evaluator);
        vm.prank(evaluator);
        acp.complete(completed, REASON, "");

        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.submit(completed, DELIVERABLE, "");

        uint256 lateJob = _fundedJob(evaluator);
        vm.warp(uint256(acp.getJob(lateJob).expiredAt));
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.submit(lateJob, DELIVERABLE, "");

        // KONTROL: status benar + belum lewat waktu → pihak asing memang `Unauthorized()`.
        uint256 okJob = _fundedJob(evaluator);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.submit(okJob, DELIVERABLE, "");
    }

    // ====================================================================
    // fund — guard expiry + urutan cek (source :419-425)
    // ====================================================================

    /// Source `:424`: `if (block.timestamp >= job.expiredAt) revert WrongStatus();`. Tanpa guard ini,
    /// mock mengunci USDC di job kedaluwarsa yang tidak akan pernah bisa di-`submit`.
    function test_fund_atExpiredAt_revertsWrongStatus() public {
        uint256 jobId = _createJob(evaluator);
        vm.prank(provider);
        acp.setBudget(jobId, BUDGET, "");
        uint256 expiredAt = uint256(acp.getJob(jobId).expiredAt);

        vm.warp(expiredAt);
        vm.prank(client);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.fund(jobId, BUDGET, "");

        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Open), "status tidak berubah");
        assertEq(usdc.balanceOf(address(acp)), 0, "tidak ada USDC yang terkunci");
        assertEq(usdc.balanceOf(client), 100_000_000, "saldo client utuh");

        // KONTROL: sedetik sebelumnya panggilan yang SAMA sukses.
        vm.warp(expiredAt - 1);
        vm.prank(client);
        acp.fund(jobId, BUDGET, "");
        assertEq(uint8(_status(jobId)), uint8(AgenticCommerce.Status.Funded), "expiredAt-1 masih boleh");
    }

    /// Urutan cek `fund` APA ADANYA dari source `:419-425`:
    /// InvalidJob → status `WrongStatus` → bukan client `Unauthorized` → provider nol `ProviderNotSet`
    /// → lewat waktu `WrongStatus` → budget beda `BudgetMismatch`.
    /// PERHATIAN: `fund` BUKAN "status/expiry dulu, auth terakhir" seperti `setBudget`/`submit`. Di sini
    /// OTORISASI menang atas `ProviderNotSet` DAN atas guard expiry; hanya cek status yang mendahuluinya.
    /// Kelima baris `fund` di tabel "selector pemenang" api-facts §A dikunci di bawah, satu per satu.
    function test_fund_checkOrder_matchesSource() public {
        // (1) STATUS sebelum OTORISASI: job sudah Funded, pihak asing tetap `WrongStatus()`.
        uint256 funded = _fundedJob(evaluator);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.fund(funded, BUDGET, "");

        // KONTROL: status Open → pihak asing memang `Unauthorized()`.
        uint256 openJob = _createJob(evaluator);
        vm.prank(provider);
        acp.setBudget(openJob, BUDGET, "");
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.fund(openJob, BUDGET, "");

        // (2) OTORISASI sebelum ProviderNotSet: job tanpa provider, pihak asing → `Unauthorized()`.
        vm.prank(client);
        uint256 noProvider =
            acp.createJob(address(0), evaluator, block.timestamp + 1 hours, "job tanpa provider", address(0));
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.fund(noProvider, 0, "");

        // KONTROL untuk cek terakhir, dijalankan sebelum warp: budget beda saja → `BudgetMismatch()`.
        vm.prank(client);
        vm.expectRevert(AgenticCommerce.BudgetMismatch.selector);
        acp.fund(openJob, BUDGET - 1, "");

        uint256 expiredAt = uint256(acp.getJob(openJob).expiredAt);
        vm.warp(expiredAt);

        // (3) OTORISASI menang atas guard EXPIRY — INILAH yang membedakan `fund` dari `setBudget`/`submit`.
        //     Pihak asing pada job yang SUDAH lewat waktu tetap menerima `Unauthorized()` `0x82b42900`,
        //     BUKAN `WrongStatus()` (api-facts §A, tabel "selector pemenang", baris `fund` ke-2).
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.fund(openJob, BUDGET, "");

        // (4) ProviderNotSet sebelum guard EXPIRY: client, job lewat waktu tanpa provider → `ProviderNotSet()`.
        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ProviderNotSet.selector);
        acp.fund(noProvider, 0, "");

        // (5) guard EXPIRY sebelum BudgetMismatch: budget salah + lewat waktu → `WrongStatus()`.
        vm.prank(client);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.fund(openJob, BUDGET - 1, "");
    }

    // ====================================================================
    // setBudget — urutan cek (source :396-399)
    // ====================================================================

    /// Source: status → expiry → otorisasi. Pihak asing menerima `WrongStatus()` pada job berstatus
    /// salah atau lewat waktu, dan `Unauthorized()` HANYA pada job yang sah. Ini KEBALIKAN `fund`,
    /// yang mendahulukan otorisasi atas guard expiry (api-facts §A, tabel "selector pemenang").
    function test_setBudget_checkOrder_statusAndExpiryBeforeAuthorization() public {
        uint256 funded = _fundedJob(evaluator);
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.setBudget(funded, BUDGET, "");

        uint256 openJob = _createJob(evaluator);

        // KONTROL dulu (sebelum warp): status Open + belum lewat waktu → `Unauthorized()`.
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.Unauthorized.selector);
        acp.setBudget(openJob, BUDGET, "");

        vm.warp(uint256(acp.getJob(openJob).expiredAt));
        vm.prank(stranger);
        vm.expectRevert(AgenticCommerce.WrongStatus.selector);
        acp.setBudget(openJob, BUDGET, "");
    }

    // ====================================================================
    // reject — TIDAK ada `Refunded` beramount nol
    // ====================================================================

    /// Source `:584-590`: `Refunded` hanya diemit bila `prev ∈ {Funded, Submitted}` **DAN `budget > 0`**.
    /// `fund(jobId, 0, "")` sah (api-facts §A), jadi jalur berbudget nol ini NYATA — indexer tidak boleh
    /// dilatih pada `Refunded(jobId, client, 0)` hantu.
    function test_reject_zeroBudget_doesNotEmitRefunded() public {
        uint256 fundedZero = _createJob(evaluator);
        vm.prank(client);
        acp.fund(fundedZero, 0, "");

        vm.recordLogs();
        vm.prank(evaluator);
        acp.reject(fundedZero, REASON, "");
        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 1, "Funded berbudget nol: HANYA JobRejected");
        assertEq(logs[0].topics[0], T_JOB_REJECTED, "topic0 JobRejected");

        uint256 submittedZero = _createJob(evaluator);
        vm.prank(client);
        acp.fund(submittedZero, 0, "");
        vm.prank(provider);
        acp.submit(submittedZero, DELIVERABLE, "");

        vm.recordLogs();
        vm.prank(evaluator);
        acp.reject(submittedZero, REASON, "");
        Vm.Log[] memory slogs = _acpLogs();
        assertEq(slogs.length, 1, "Submitted berbudget nol: HANYA JobRejected");
        assertEq(slogs[0].topics[0], T_JOB_REJECTED, "topic0 JobRejected");

        // Jalur Open memang tidak pernah punya escrow.
        uint256 openJob = _createJob(evaluator);
        vm.recordLogs();
        vm.prank(client);
        acp.reject(openJob, REASON, "");
        Vm.Log[] memory ologs = _acpLogs();
        assertEq(ologs.length, 1, "Open: HANYA JobRejected");
        // Pasangan dari `test_reject_open_byProviderOrClient_succeeds` (di sana penolaknya provider):
        // dua kasus ini bersama-sama mengunci `rejector == msg.sender`, bukan salah satu pihak tetap.
        assertEq(address(uint160(uint256(ologs[0].topics[2]))), client, "rejector = client di sini");

        // KONTROL: begitu budget > 0, `Refunded` MUNCUL lagi (2 log).
        uint256 withBudget = _fundedJob(evaluator);
        vm.recordLogs();
        vm.prank(evaluator);
        acp.reject(withBudget, REASON, "");
        Vm.Log[] memory blogs = _acpLogs();
        assertEq(blogs.length, 2, "budget > 0: Refunded + JobRejected");
        assertEq(blogs[0].topics[0], T_REFUNDED, "urutan 1: Refunded");
    }

    // ====================================================================
    // claimRefund — Funded/Submitted BERBUDGET NOL hanya mengemit JobExpired
    //
    // api-facts §A tabel event `claimRefund`: syarat emit `Refunded` adalah `budget > 0` DAN
    // status ∈ {Funded, Submitted} — BUKAN status saja. Jalur ini nyata karena `fund(jobId, 0, "")` sah.
    // ====================================================================

    function test_claimRefund_zeroBudget_fromFundedAndSubmitted_emitsOnlyJobExpired() public {
        uint256 fundedZero = _createJob(evaluator);
        vm.prank(client);
        acp.fund(fundedZero, 0, "");

        uint256 submittedZero = _createJob(evaluator);
        vm.prank(client);
        acp.fund(submittedZero, 0, "");
        vm.prank(provider);
        acp.submit(submittedZero, DELIVERABLE, "");

        vm.warp(uint256(acp.getJob(fundedZero).expiredAt));
        vm.recordLogs();
        vm.prank(stranger);
        acp.claimRefund(fundedZero);
        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 1, "Funded + budget 0: HANYA JobExpired");
        assertEq(logs[0].topics[0], T_JOB_EXPIRED, "topic0 JobExpired");
        assertEq(uint8(_status(fundedZero)), uint8(AgenticCommerce.Status.Expired), "status Expired");

        vm.warp(uint256(acp.getJob(submittedZero).expiredAt) + 900);
        vm.recordLogs();
        vm.prank(stranger);
        acp.claimRefund(submittedZero);
        Vm.Log[] memory slogs = _acpLogs();
        assertEq(slogs.length, 1, "Submitted + budget 0: HANYA JobExpired");
        assertEq(slogs[0].topics[0], T_JOB_EXPIRED, "topic0 JobExpired");

        assertEq(usdc.balanceOf(client), 100_000_000, "tidak ada dana yang pernah bergerak");
        assertEq(usdc.balanceOf(address(acp)), 0, "escrow tetap kosong");
    }

    // ====================================================================
    // Nilai NUMERIK enum Status
    //
    // `status` menyeberangi ABI sebagai `uint8`; vault (task 1.2) dan watcher (task 2.2)
    // membandingkannya sebagai ANGKA. Menukar dua anggota enum tidak mengubah selector, topic0,
    // maupun nama field di ABI JSON — hanya tes ini yang menangkapnya.
    // Acuan: source AgenticCommerceV3.sol:44-51 dan api-facts §A.
    // ====================================================================

    /// @dev Status APA ADANYA dari returndata `getJob` (word ke-2), tanpa lewat enum Solidity.
    function _rawStatus(uint256 jobId) internal view returns (uint256) {
        (bool ok, bytes memory ret) = address(acp).staticcall(abi.encodeWithSelector(bytes4(0xbf22c457), jobId));
        require(ok, "getJob harus sukses");
        return uint256(_word(ret, 2));
    }

    function test_statusEnum_numericValuesMatchAcpAbi() public {
        assertEq(uint256(uint8(AgenticCommerce.Status.Open)), 0, "Open = 0");
        assertEq(uint256(uint8(AgenticCommerce.Status.Funded)), 1, "Funded = 1");
        assertEq(uint256(uint8(AgenticCommerce.Status.Submitted)), 2, "Submitted = 2");
        assertEq(uint256(uint8(AgenticCommerce.Status.Completed)), 3, "Completed = 3");
        assertEq(uint256(uint8(AgenticCommerce.Status.Rejected)), 4, "Rejected = 4");
        assertEq(uint256(uint8(AgenticCommerce.Status.Expired)), 5, "Expired = 5");

        // Angka yang BENAR-BENAR dikirim lewat ABI di setiap tahap siklus, bukan sekadar enum.
        uint256 openJob = _createJob(evaluator);
        assertEq(_rawStatus(openJob), 0, "ABI: Open = 0");

        uint256 job = _fundedJob(evaluator);
        assertEq(_rawStatus(job), 1, "ABI: Funded = 1");
        vm.prank(provider);
        acp.submit(job, DELIVERABLE, "");
        assertEq(_rawStatus(job), 2, "ABI: Submitted = 2");
        vm.prank(evaluator);
        acp.complete(job, REASON, "");
        assertEq(_rawStatus(job), 3, "ABI: Completed = 3");

        uint256 rejected = _fundedJob(evaluator);
        vm.prank(evaluator);
        acp.reject(rejected, REASON, "");
        assertEq(_rawStatus(rejected), 4, "ABI: Rejected = 4");

        uint256 expired = _fundedJob(evaluator);
        vm.warp(uint256(acp.getJob(expired).expiredAt));
        vm.prank(stranger);
        acp.claimRefund(expired);
        assertEq(_rawStatus(expired), 5, "ABI: Expired = 5");
    }

    // ====================================================================
    // Jalur auto-complete — isi data event, bukan hanya topic0
    // ====================================================================

    /// Mengunci ketiga log jalur `evaluator == 0` (Funded berbudget) berikut ISI datanya:
    /// `JobSubmitted.deliverable`, `JobCompleted.evaluator = address(0)`,
    /// `JobCompleted.reason = deliverable`, `PaymentReleased.amount = budget − platformFee`.
    function test_autoComplete_eventData_matchesAcpAbi() public {
        uint256 jobId = _fundedJob(address(0));

        vm.recordLogs();
        vm.prank(provider);
        acp.submit(jobId, DELIVERABLE, "");

        Vm.Log[] memory logs = _acpLogs();
        assertEq(logs.length, 3, "JobSubmitted, JobCompleted, PaymentReleased");

        assertEq(logs[0].topics[0], T_JOB_SUBMITTED, "urutan 1: JobSubmitted");
        assertEq(logs[0].topics.length, 3, "JobSubmitted: jobId+provider indexed");
        assertEq(address(uint160(uint256(logs[0].topics[2]))), provider, "JobSubmitted topic2 = provider");
        assertEq(abi.decode(logs[0].data, (bytes32)), DELIVERABLE, "JobSubmitted.deliverable");

        assertEq(logs[1].topics[0], T_JOB_COMPLETED, "urutan 2: JobCompleted");
        assertEq(logs[1].topics.length, 3, "JobCompleted: jobId+evaluator indexed");
        assertEq(address(uint160(uint256(logs[1].topics[2]))), address(0), "JobCompleted.evaluator = 0, BUKAN provider");
        assertEq(abi.decode(logs[1].data, (bytes32)), DELIVERABLE, "JobCompleted.reason = deliverable");

        assertEq(logs[2].topics[0], T_PAYMENT_RELEASED, "urutan 3: PaymentReleased");
        assertEq(logs[2].topics.length, 3, "PaymentReleased: jobId+provider indexed");
        assertEq(address(uint160(uint256(logs[2].topics[2]))), provider, "PaymentReleased topic2 = provider");
        assertEq(abi.decode(logs[2].data, (uint256)), 9_900_000, "PaymentReleased.amount = budget - platformFee");

        // Tidak ada EvaluatorFeePaid di jalur ini: fee evaluator memang tidak dipotong.
        assertEq(usdc.balanceOf(treasury), PLATFORM_FEE, "hanya platform fee yang dipotong");
    }

    // ====================================================================
    // Reentrancy — SISA fungsi ber-`nonReentrant` yang belum terkunci
    //
    // Kontrak asli mewarisi `ReentrancyGuardTransient` dan memasang `nonReentrant` di
    // createJob/setBudget/fund/submit/complete/reject/claimRefund (source :331,:394,:418,:453,:514,:559,:601).
    // Sebelumnya hanya `fund` dan `claimRefund` yang terkunci tes; lima tes di bawah menutup sisanya.
    // Pola tiap tes: masuk lewat `fund` → `transferFrom` token penyerang → panggil fungsi target yang
    // SEHARUSNYA sah. Ditutup KONTROL: panggilan yang sama di luar reentrancy SUKSES, jadi revert-nya
    // benar-benar dari guard dan bukan dari status/otorisasi.
    // ====================================================================

    /// @dev Job "pembawa" berbudget: `fund`-nya memicu `transferFrom` token penyerang.
    function _carrier(AgenticCommerce acp2) internal returns (uint256 carrier) {
        vm.prank(client);
        carrier = acp2.createJob(provider, evaluator, block.timestamp + 1 hours, "pembawa", address(0));
        vm.prank(provider);
        acp2.setBudget(carrier, BUDGET, "");
    }

    function test_reentrancy_createJobIsGuarded() public {
        (ReentrantToken token, AgenticCommerce acp2) = _reentrantSetup();
        uint256 carrier = _carrier(acp2);
        uint256 expiredAt = block.timestamp + 1 hours;

        token.arm(ReentrantToken.Mode.CreateJob, 0, provider, expiredAt);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ReentrancyGuardReentrantCall.selector);
        acp2.fund(carrier, BUDGET, "");
        assertEq(uint8(acp2.getJob(carrier).status), uint8(AgenticCommerce.Status.Open), "fund ikut batal");

        token.arm(ReentrantToken.Mode.None, 0, address(0), 0);
        uint256 created = token.createJobAsClient(provider, address(0), expiredAt);
        assertEq(acp2.getJob(created).client, address(token), "kontrol: createJob sah di luar reentrancy");
    }

    function test_reentrancy_setBudgetIsGuarded() public {
        (ReentrantToken token, AgenticCommerce acp2) = _reentrantSetup();
        vm.prank(client);
        uint256 target = acp2.createJob(address(token), evaluator, block.timestamp + 1 hours, "target", address(0));
        uint256 carrier = _carrier(acp2);

        token.arm(ReentrantToken.Mode.SetBudget, target, address(0), 777);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ReentrancyGuardReentrantCall.selector);
        acp2.fund(carrier, BUDGET, "");
        assertEq(acp2.getJob(target).budget, 0, "budget target tidak berubah");

        token.arm(ReentrantToken.Mode.None, 0, address(0), 0);
        vm.prank(address(token));
        acp2.setBudget(target, 777, "");
        assertEq(acp2.getJob(target).budget, 777, "kontrol: setBudget sah di luar reentrancy");
    }

    function test_reentrancy_submitIsGuarded() public {
        (ReentrantToken token, AgenticCommerce acp2) = _reentrantSetup();
        // Dibaca DULU: `token.PAYLOAD()` adalah panggilan eksternal yang akan memakan `vm.prank`.
        bytes32 payload = token.PAYLOAD();
        vm.prank(client);
        uint256 target = acp2.createJob(address(token), evaluator, block.timestamp + 1 hours, "target", address(0));
        vm.prank(address(token));
        acp2.setBudget(target, BUDGET, "");
        vm.prank(client);
        acp2.fund(target, BUDGET, "");
        uint256 carrier = _carrier(acp2);

        token.arm(ReentrantToken.Mode.Submit, target, address(0), 0);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ReentrancyGuardReentrantCall.selector);
        acp2.fund(carrier, BUDGET, "");
        assertEq(uint8(acp2.getJob(target).status), uint8(AgenticCommerce.Status.Funded), "target tidak berubah");

        token.arm(ReentrantToken.Mode.None, 0, address(0), 0);
        vm.prank(address(token));
        acp2.submit(target, payload, "");
        assertEq(
            uint8(acp2.getJob(target).status), uint8(AgenticCommerce.Status.Submitted), "kontrol: submit sah di luar"
        );
    }

    function test_reentrancy_completeIsGuarded() public {
        (ReentrantToken token, AgenticCommerce acp2) = _reentrantSetup();
        bytes32 payload = token.PAYLOAD();
        vm.prank(client);
        uint256 target = acp2.createJob(provider, address(token), block.timestamp + 1 hours, "target", address(0));
        vm.prank(provider);
        acp2.setBudget(target, BUDGET, "");
        vm.prank(client);
        acp2.fund(target, BUDGET, "");
        vm.prank(provider);
        acp2.submit(target, DELIVERABLE, "");
        uint256 carrier = _carrier(acp2);

        token.arm(ReentrantToken.Mode.Complete, target, address(0), 0);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ReentrancyGuardReentrantCall.selector);
        acp2.fund(carrier, BUDGET, "");
        assertEq(uint8(acp2.getJob(target).status), uint8(AgenticCommerce.Status.Submitted), "target tidak berubah");

        token.arm(ReentrantToken.Mode.None, 0, address(0), 0);
        vm.prank(address(token));
        acp2.complete(target, payload, "");
        assertEq(
            uint8(acp2.getJob(target).status), uint8(AgenticCommerce.Status.Completed), "kontrol: complete sah di luar"
        );
        assertEq(token.balanceOf(provider), PROVIDER_AMOUNT, "kontrol: provider dibayar");
    }

    function test_reentrancy_rejectIsGuarded() public {
        (ReentrantToken token, AgenticCommerce acp2) = _reentrantSetup();
        bytes32 payload = token.PAYLOAD();
        vm.prank(client);
        uint256 target = acp2.createJob(provider, address(token), block.timestamp + 1 hours, "target", address(0));
        vm.prank(provider);
        acp2.setBudget(target, BUDGET, "");
        vm.prank(client);
        acp2.fund(target, BUDGET, "");
        uint256 carrier = _carrier(acp2);

        token.arm(ReentrantToken.Mode.Reject, target, address(0), 0);

        vm.prank(client);
        vm.expectRevert(AgenticCommerce.ReentrancyGuardReentrantCall.selector);
        acp2.fund(carrier, BUDGET, "");
        assertEq(uint8(acp2.getJob(target).status), uint8(AgenticCommerce.Status.Funded), "target tidak berubah");

        token.arm(ReentrantToken.Mode.None, 0, address(0), 0);
        vm.prank(address(token));
        acp2.reject(target, payload, "");
        assertEq(
            uint8(acp2.getJob(target).status), uint8(AgenticCommerce.Status.Rejected), "kontrol: reject sah di luar"
        );
        assertEq(token.balanceOf(client), 100_000_000, "kontrol: refund 100% ke client");
    }

    /// Source `:431`: `fund` mentransfer HANYA bila `budget > 0`; `reject`/`claimRefund` juga tidak
    /// memindahkan apa pun saat budget nol. Tes ini melihat log MENTAH (tidak difilter emitter) supaya
    /// `Transfer` ERC-20 beramount nol — yang tidak pernah ada di ACP asli dan menuntut allowance yang
    /// tak pernah diminta — ketahuan.
    function test_zeroAmountPaths_emitNoErc20Transfer() public {
        uint256 zeroJob = _createJob(evaluator);

        vm.recordLogs();
        vm.prank(client);
        acp.fund(zeroJob, 0, "");
        Vm.Log[] memory funded = vm.getRecordedLogs();
        assertEq(funded.length, 1, "fund budget 0: hanya JobFunded, TANPA Transfer ERC-20");
        assertEq(funded[0].emitter, address(acp), "emitter = ACP");
        assertEq(funded[0].topics[0], T_JOB_FUNDED, "topic0 JobFunded");

        // KONTROL: budget > 0 memang memancarkan `Transfer` token lebih dulu.
        uint256 paidJob = _createJob(evaluator);
        vm.prank(provider);
        acp.setBudget(paidJob, BUDGET, "");
        vm.recordLogs();
        vm.prank(client);
        acp.fund(paidJob, BUDGET, "");
        Vm.Log[] memory paid = vm.getRecordedLogs();
        assertEq(paid.length, 2, "budget > 0: Transfer ERC-20 lalu JobFunded");
        assertEq(paid[0].emitter, address(usdc), "Transfer dipancarkan token");
        assertEq(paid[1].emitter, address(acp), "JobFunded dipancarkan ACP");

        vm.recordLogs();
        vm.prank(evaluator);
        acp.reject(zeroJob, REASON, "");
        Vm.Log[] memory rejected = vm.getRecordedLogs();
        assertEq(rejected.length, 1, "reject budget 0: hanya JobRejected, tanpa Transfer");
        assertEq(rejected[0].topics[0], T_JOB_REJECTED, "topic0 JobRejected");
    }
}
