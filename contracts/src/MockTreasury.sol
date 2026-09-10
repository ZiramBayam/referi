// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

/// @notice Minimal value-accounting fixture used only by the Passport MVP.
/// @dev Reserve decreases on rebalance. There is intentionally no direct public
///      value-moving path once the verifier has been configured.
contract MockTreasury {
    error NotOwner();
    error NotVerifier();
    error ZeroAddress();
    error VerifierAlreadyConfigured();
    error ReserveInvariant();
    error AmountExceedsReserve();

    address public immutable owner;
    address public verifier;
    uint256 public reserve;
    uint256 public immutable minimumReserve;

    event VerifierConfigured(address indexed verifier);
    event Rebalanced(uint256 amount, uint256 previousReserve, uint256 newReserve);

    constructor(address owner_, uint256 initialReserve_, uint256 minimumReserve_) {
        if (owner_ == address(0)) revert ZeroAddress();
        if (minimumReserve_ > initialReserve_) revert ReserveInvariant();
        owner = owner_;
        reserve = initialReserve_;
        minimumReserve = minimumReserve_;
    }

    /// @dev One-time wiring avoids a deploy-time circular dependency while leaving
    ///      no owner bypass for the actual rebalance action.
    function configureVerifier(address verifier_) external {
        if (msg.sender != owner) revert NotOwner();
        if (verifier != address(0)) revert VerifierAlreadyConfigured();
        if (verifier_ == address(0)) revert ZeroAddress();
        verifier = verifier_;
        emit VerifierConfigured(verifier_);
    }

    function rebalance(uint256 amount) external {
        if (msg.sender != verifier) revert NotVerifier();
        if (amount > reserve) revert AmountExceedsReserve();
        uint256 previousReserve = reserve;
        uint256 newReserve = previousReserve - amount;
        if (newReserve < minimumReserve) revert ReserveInvariant();
        reserve = newReserve;
        emit Rebalanced(amount, previousReserve, newReserve);
    }
}
