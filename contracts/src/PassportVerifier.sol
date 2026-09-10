// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ReentrancyGuardTransient} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

import {MockTreasury} from "./MockTreasury.sol";

/// @title PassportVerifier
/// @notice Deliberately narrow Execution Passport enforcement gate for the hackathon MVP.
/// @dev It accepts one target, one selector, and one trusted policy signer. It does not
///      query Sibyl, an oracle, or a simulator. Those observations are bound to the
///      signer-attested EIP-712 passport and remain within the mock trust boundary.
contract PassportVerifier is EIP712, ReentrancyGuardTransient {
    using ECDSA for bytes32;

    bytes32 public constant ACTION_CLASS = keccak256("treasury-rebalance");
    bytes4 public constant REBALANCE_SELECTOR = bytes4(keccak256("rebalance(uint256)"));
    uint256 public constant PASSPORT_VERSION = 1;
    uint256 public constant MAX_PASSPORT_LIFETIME = 60;

    bytes32 private constant EXECUTION_PASSPORT_TYPEHASH = keccak256(
        "ExecutionPassport(uint256 passportVersion,bytes32 actionClass,uint256 chainId,address target,bytes4 selector,bytes32 calldataHash,uint256 value,uint256 stateBlockNumber,bytes32 stateBlockHash,bytes32 hypothesisIdsHash,bytes32 obligationResultsHash,bytes32 memoryRoot,uint256 issuedAt,uint256 expiresAt,uint256 nonce)"
    );
    bytes32 private constant ACTION_DIGEST_TYPEHASH = keccak256(
        "Action(uint256 chainId,address target,bytes4 selector,bytes32 calldataHash,uint256 value,uint256 stateBlockNumber,bytes32 stateBlockHash)"
    );

    struct ExecutionPassport {
        uint256 passportVersion;
        bytes32 actionClass;
        uint256 chainId;
        address target;
        bytes4 selector;
        bytes32 calldataHash;
        uint256 value;
        uint256 stateBlockNumber;
        bytes32 stateBlockHash;
        bytes32 hypothesisIdsHash;
        bytes32 obligationResultsHash;
        bytes32 memoryRoot;
        uint256 issuedAt;
        uint256 expiresAt;
        uint256 nonce;
    }

    MockTreasury public immutable treasury;
    address public immutable policySigner;
    mapping(uint256 nonce => bool used) public usedNonces;

    error WrongPassportVersion();
    error WrongActionClass();
    error WrongChain();
    error WrongTarget();
    error WrongSelector();
    error CalldataMismatch();
    error ValueMismatch();
    error PassportNotYetValid();
    error PassportExpired();
    error PassportLifetimeTooLong();
    error NonceAlreadyUsed();
    error WrongSigner();
    error TreasuryCallFailed();

    event PassportConsumed(
        uint256 indexed nonce,
        bytes32 indexed passportDigest,
        bytes32 actionDigest,
        bytes32 hypothesisIdsHash,
        bytes32 obligationResultsHash,
        bytes32 memoryRoot
    );

    constructor(MockTreasury treasury_, address policySigner_)
        EIP712("Execution Passport", "1")
    {
        if (address(treasury_) == address(0) || policySigner_ == address(0)) revert WrongTarget();
        treasury = treasury_;
        policySigner = policySigner_;
    }

    function execute(
        ExecutionPassport calldata passport,
        bytes calldata signature,
        bytes calldata rebalanceCalldata
    ) external payable nonReentrant returns (bytes memory returndata) {
        if (passport.passportVersion != PASSPORT_VERSION) revert WrongPassportVersion();
        if (passport.actionClass != ACTION_CLASS) revert WrongActionClass();
        if (passport.chainId != block.chainid) revert WrongChain();
        if (passport.target != address(treasury)) revert WrongTarget();
        if (passport.selector != REBALANCE_SELECTOR) revert WrongSelector();
        if (passport.value != msg.value) revert ValueMismatch();
        if (passport.issuedAt > block.timestamp) revert PassportNotYetValid();
        if (block.timestamp > passport.expiresAt) revert PassportExpired();
        if (passport.expiresAt < passport.issuedAt) revert PassportExpired();
        if (passport.expiresAt - passport.issuedAt > MAX_PASSPORT_LIFETIME) {
            revert PassportLifetimeTooLong();
        }
        if (usedNonces[passport.nonce]) revert NonceAlreadyUsed();

        bytes4 suppliedSelector;
        assembly {
            suppliedSelector := calldataload(rebalanceCalldata.offset)
        }
        if (rebalanceCalldata.length < 4 || suppliedSelector != passport.selector) {
            revert WrongSelector();
        }
        if (keccak256(rebalanceCalldata) != passport.calldataHash) revert CalldataMismatch();

        bytes32 digest = _hashPassport(passport);
        if (digest.recover(signature) != policySigner) revert WrongSigner();

        usedNonces[passport.nonce] = true;
        (bool ok, bytes memory result) = address(treasury).call{value: msg.value}(rebalanceCalldata);
        if (!ok) revert TreasuryCallFailed();

        emit PassportConsumed(
            passport.nonce,
            digest,
            _actionDigest(passport),
            passport.hypothesisIdsHash,
            passport.obligationResultsHash,
            passport.memoryRoot
        );
        return result;
    }

    /// @notice Exposes the exact digest for local clients and fixed-vector tests.
    /// @dev This is a pure format helper; it does not authorize an execution.
    function hashPassport(ExecutionPassport calldata passport) external view returns (bytes32) {
        return _hashPassport(passport);
    }

    function _hashPassport(ExecutionPassport calldata passport) internal view returns (bytes32) {
        return _hashTypedDataV4(
            keccak256(abi.encode(EXECUTION_PASSPORT_TYPEHASH, passport))
        );
    }

    function _actionDigest(ExecutionPassport calldata passport) internal pure returns (bytes32) {
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
