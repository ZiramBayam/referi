// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Test} from "forge-std/Test.sol";

import {MockOracle} from "../src/MockOracle.sol";
import {MockTreasury} from "../src/MockTreasury.sol";
import {PassportVerifier} from "../src/PassportVerifier.sol";

contract ExecutionPassportVerifierTest is Test {
    uint256 private constant POLICY_KEY = 0xA11CE;
    uint256 private constant OTHER_KEY = 0xB0B;
    bytes32 private constant ACTION_DIGEST_TYPEHASH = keccak256(
        "Action(uint256 chainId,address target,bytes4 selector,bytes32 calldataHash,uint256 value,uint256 stateBlockNumber,bytes32 stateBlockHash)"
    );

    MockTreasury private treasury;
    PassportVerifier private verifier;
    address private policySigner;

    function setUp() public {
        policySigner = vm.addr(POLICY_KEY);
        treasury = new MockTreasury(address(this), 1_000_000, 250_000);
        verifier = new PassportVerifier(treasury, policySigner);
        treasury.configureVerifier(address(verifier));
        vm.warp(1_000);
    }

    function test_validPassportExecutesOneMatchingRebalance() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 1, 1_000, 1_030);
        bytes memory calldata_ = _calldata(100_000);
        bytes memory signature = _sign(POLICY_KEY, passport);

        vm.expectEmit(true, true, false, true, address(verifier));
        emit PassportVerifier.PassportConsumed(
            passport.nonce,
            _digest(passport),
            _actionDigest(passport),
            passport.hypothesisIdsHash,
            passport.obligationResultsHash,
            passport.memoryRoot
        );
        verifier.execute(passport, signature, calldata_);

        assertEq(treasury.reserve(), 900_000);
        assertTrue(verifier.usedNonces(1));
    }

    function test_directTreasuryRebalanceReverts() public {
        vm.expectRevert(MockTreasury.NotVerifier.selector);
        treasury.rebalance(100_000);
    }

    function test_mockOracleOnlyOwnerCanChangeFixtureObservation() public {
        MockOracle oracle = new MockOracle(address(this));
        oracle.setObservation(900, 1_000);
        assertEq(oracle.timestamp(), 900);
        assertEq(oracle.price(), 1_000);

        vm.prank(address(0xCAFE));
        vm.expectRevert(MockOracle.NotOwner.selector);
        oracle.setObservation(901, 1_001);
    }

    function test_replayRevertsAndDoesNotChangeReserve() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 2, 1_000, 1_030);
        bytes memory calldata_ = _calldata(100_000);
        bytes memory signature = _sign(POLICY_KEY, passport);
        verifier.execute(passport, signature, calldata_);
        uint256 reserveAfterFirst = treasury.reserve();

        vm.expectRevert(PassportVerifier.NonceAlreadyUsed.selector);
        verifier.execute(passport, signature, calldata_);
        assertEq(treasury.reserve(), reserveAfterFirst);
    }

    function test_calldataMutationRevertsBeforeTreasuryCall() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 3, 1_000, 1_030);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory mutatedCalldata = _calldata(100_001);
        uint256 reserveBefore = treasury.reserve();

        vm.expectRevert(PassportVerifier.CalldataMismatch.selector);
        verifier.execute(passport, signature, mutatedCalldata);
        assertEq(treasury.reserve(), reserveBefore);
        assertFalse(verifier.usedNonces(3));
    }

    function test_wrongSignerReverts() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 4, 1_000, 1_030);
        bytes memory signature = _sign(OTHER_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.WrongSigner.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function test_expiredPassportReverts() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 5, 900, 999);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.PassportExpired.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function test_notYetValidPassportReverts() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 6, 1_001, 1_030);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.PassportNotYetValid.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function test_passportLifetimeCannotExceedBound() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 7, 1_000, 1_061);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.PassportLifetimeTooLong.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function test_wrongTargetReverts() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 8, 1_000, 1_030);
        passport.target = address(0xCAFE);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.WrongTarget.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function test_wrongActionClassReverts() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 10, 1_000, 1_030);
        passport.actionClass = bytes32(uint256(123));
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.WrongActionClass.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function test_wrongSelectorReverts() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 11, 1_000, 1_030);
        passport.selector = bytes4(0x12345678);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.WrongSelector.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function test_wrongChainReverts() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 12, 1_000, 1_030);
        passport.chainId = 1;
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.WrongChain.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function test_valueMismatchReverts() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 13, 1_000, 1_030);
        passport.value = 1;
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectRevert(PassportVerifier.ValueMismatch.selector);
        verifier.execute(passport, signature, calldata_);
    }

    function testFuzz_anyAmountCalldataMutationBreaksBinding(uint256 amount) public {
        amount = bound(amount, 0, 750_000);
        PassportVerifier.ExecutionPassport memory passport = _passport(amount, 14, 1_000, 1_030);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory mutatedCalldata = _calldata(amount + 1);

        vm.expectRevert(PassportVerifier.CalldataMismatch.selector);
        verifier.execute(passport, signature, mutatedCalldata);
        assertEq(treasury.reserve(), 1_000_000);
        assertFalse(verifier.usedNonces(14));
    }

    function test_treasuryInvariantFailureRevertsAtomically() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(800_000, 9, 1_000, 1_030);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(800_000);

        vm.expectRevert(PassportVerifier.TreasuryCallFailed.selector);
        verifier.execute(passport, signature, calldata_);
        assertEq(treasury.reserve(), 1_000_000);
        assertFalse(verifier.usedNonces(9));
    }

    function _calldata(uint256 amount) private view returns (bytes memory) {
        return abi.encodeWithSelector(verifier.REBALANCE_SELECTOR(), amount);
    }

    function _passport(
        uint256 amount,
        uint256 nonce,
        uint256 issuedAt,
        uint256 expiresAt
    ) private view returns (PassportVerifier.ExecutionPassport memory passport) {
        bytes memory calldata_ = _calldata(amount);
        passport = PassportVerifier.ExecutionPassport({
            passportVersion: 1,
            actionClass: verifier.ACTION_CLASS(),
            chainId: block.chainid,
            target: address(treasury),
            selector: verifier.REBALANCE_SELECTOR(),
            calldataHash: keccak256(calldata_),
            value: 0,
            stateBlockNumber: block.number,
            stateBlockHash: bytes32(uint256(0x11)),
            hypothesisIdsHash: bytes32(uint256(0x22)),
            obligationResultsHash: bytes32(uint256(0x33)),
            memoryRoot: bytes32(uint256(0x44)),
            issuedAt: issuedAt,
            expiresAt: expiresAt,
            nonce: nonce
        });
    }

    function _sign(uint256 privateKey, PassportVerifier.ExecutionPassport memory passport)
        private
        view
        returns (bytes memory)
    {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(privateKey, _digest(passport));
        return abi.encodePacked(r, s, v);
    }

    function _digest(PassportVerifier.ExecutionPassport memory passport)
        private
        view
        returns (bytes32)
    {
        return verifier.hashPassport(passport);
    }

    function _actionDigest(PassportVerifier.ExecutionPassport memory passport)
        private
        pure
        returns (bytes32)
    {
        return keccak256(
            abi.encode(
                ACTION_DIGEST_TYPEHASH,
                passport.chainId,
                passport.target,
                passport.selector,
                passport.calldataHash,
                passport.value,
                passport.stateBlockNumber,
                passport.stateBlockHash
            )
        );
    }
}
