// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

/**
 * @title  DarkPoolEscrow  (v2 — 선예치 + 부분체결)
 * @notice Privacy-preserving OTC escrow for DarkPool Lite.
 *
 * v2 changes vs v1:
 *  - Pre-deposit: users deposit BEFORE matching (선예치).
 *  - Partial fills: 100 sell vs 60 buy → 60 filled, 40 remains.
 *  - Cancel/refund: unfilled remainder is refundable on cancel.
 *  - Fee (P1): optional 0.1 % fee on each fill, accumulated in contract.
 *
 * Flow:
 *  1. Alice calls deposit(orderId, tokenAddr, amount) → tokens locked in contract.
 *  2. Frontend sends order info (off-chain) to TEE for matching.
 *  3. TEE matches Alice & Bob (rule-based: price-priority → time-priority).
 *  4. TEE signs the swap params and calls (or relays) executeSwap().
 *  5. Contract verifies TEE sig → atomically swaps filled amounts.
 *  6. If partially filled, remainder stays locked for future matches.
 *  7. User may cancelOrder() at any time to withdraw unfilled remainder.
 *
 * Privacy: Only deposit tx + swap tx are on-chain. Order price, side, and
 *          pending quantities are never published.
 *
 * Security:
 *  - Fake TEE signature → rejected by _verifyTEESignature().
 *  - Replay / double execute → executedSwaps mapping blocks re-use of swapId.
 *  - Reentrancy → ReentrancyGuard + Checks-Effects-Interactions.
 *  - Cross-chain replay → signed payload includes chainId + address(this).
 */
contract DarkPoolEscrow is ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;

    // ─────────────────────────────────────────────────────────────────────────
    //  Constants & State
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Fee in basis points (10 = 0.1 %).  P1 feature.
    uint256 public constant FEE_BPS = 10;
    uint256 public constant BPS_DENOMINATOR = 10_000;

    /// @notice TEE signer address (ECDSA public key → Ethereum address).
    address public teeSignerAddress;

    /// @notice Toggle for fee collection.  Disabled by default for MVP demo.
    bool public feeEnabled;

    struct Order {
        address trader;        // who deposited
        address token;         // ERC-20 token address
        uint256 totalAmount;   // original deposit
        uint256 filledAmount;  // cumulative filled so far
        bool    active;        // false after full-fill or cancel
    }

    /// @dev orderId (generated off-chain) → Order
    mapping(bytes32 => Order) public orders;

    /// @dev swapId → true if already executed (replay protection)
    mapping(bytes32 => bool) public executedSwaps;

    /// @dev token address → accumulated protocol fees (P1)
    mapping(address => uint256) public collectedFees;

    // ─────────────────────────────────────────────────────────────────────────
    //  Events  (P0: Deposited, SwapExecuted, PartialFill, Cancelled)
    // ─────────────────────────────────────────────────────────────────────────

    event TEESignerUpdated(address indexed oldSigner, address indexed newSigner);
    event FeeToggled(bool enabled);

    /// @notice Emitted when a user deposits tokens to create an order.
    event Deposited(
        bytes32 indexed orderId,
        address indexed trader,
        address  token,
        uint256  amount
    );

    /// @notice Emitted on every successful swap execution (full or partial).
    event SwapExecuted(
        bytes32 indexed swapId,
        bytes32 indexed makerOrderId,
        bytes32 indexed takerOrderId,
        uint256 makerFillAmount,
        uint256 takerFillAmount
    );

    /// @notice Emitted when an order is partially filled (remaining > 0).
    event PartialFill(
        bytes32 indexed orderId,
        uint256 filledAmount,
        uint256 remainingAmount
    );

    /// @notice Emitted when a user cancels an order and receives a refund.
    event Cancelled(
        bytes32 indexed orderId,
        address indexed trader,
        uint256 refundAmount
    );

    // ─────────────────────────────────────────────────────────────────────────
    //  Constructor
    // ─────────────────────────────────────────────────────────────────────────

    constructor(address _teeSignerAddress) Ownable(msg.sender) {
        require(_teeSignerAddress != address(0), "DPE: zero TEE signer");
        teeSignerAddress = _teeSignerAddress;
        feeEnabled = false; // MVP demo: no fees
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Admin  (P0 + P1)
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Update TEE signer.  Only owner.
    function updateTEESignerAddress(address _newSigner) external onlyOwner {
        require(_newSigner != address(0), "DPE: zero address");
        emit TEESignerUpdated(teeSignerAddress, _newSigner);
        teeSignerAddress = _newSigner;
    }

    /// @notice Toggle fee collection on/off.  P1 feature.
    function setFeeEnabled(bool _enabled) external onlyOwner {
        feeEnabled = _enabled;
        emit FeeToggled(_enabled);
    }

    /// @notice Withdraw accumulated fees.  P1 feature.
    function withdrawFees(address token, address to) external onlyOwner {
        require(to != address(0), "DPE: zero address");
        uint256 amount = collectedFees[token];
        require(amount > 0, "DPE: no fees");
        collectedFees[token] = 0;
        IERC20(token).safeTransfer(to, amount);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Core: deposit  (P0 — 선예치)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Deposit tokens and create an order.  Called BEFORE matching (선예치).
     *         Requires prior ERC-20 approve() for this contract.
     *
     * @param orderId  Unique order ID (generated off-chain, e.g. by frontend / TEE).
     * @param token    ERC-20 token address to deposit.
     * @param amount   Amount to deposit (in token's smallest unit).
     */
    function deposit(
        bytes32 orderId,
        address token,
        uint256 amount
    ) external nonReentrant {
        require(orders[orderId].trader == address(0), "DPE: order exists");
        require(token  != address(0),                 "DPE: zero token");
        require(amount > 0,                           "DPE: zero amount");

        orders[orderId] = Order({
            trader:       msg.sender,
            token:        token,
            totalAmount:  amount,
            filledAmount: 0,
            active:       true
        });

        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);

        emit Deposited(orderId, msg.sender, token, amount);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Core: executeSwap  (P0 — TEE 서명 검증 + 아토믹 스왓 + 부분체결)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Execute a TEE-authorised atomic swap between two orders.
     *         Supports partial fills: fill amounts may be less than order totals.
     *
     *         Maker's token goes to taker's trader; taker's token goes to maker's trader.
     *
     * @param swapId           Unique swap execution ID (TEE-generated, prevents replay).
     * @param makerOrderId     Order ID of the maker (e.g. seller).
     * @param takerOrderId     Order ID of the taker (e.g. buyer / MM).
     * @param makerFillAmount  Amount of maker's token being traded in this fill.
     * @param takerFillAmount  Amount of taker's token being traded in this fill.
     * @param teeSignature     65-byte ECDSA signature from TEE over the swap hash.
     */
    function executeSwap(
        bytes32 swapId,
        bytes32 makerOrderId,
        bytes32 takerOrderId,
        uint256 makerFillAmount,
        uint256 takerFillAmount,
        bytes calldata teeSignature
    ) external nonReentrant {
        // ── Checks ──────────────────────────────────────────────────────────
        require(!executedSwaps[swapId],  "DPE: swap already executed");
        require(makerFillAmount > 0 && takerFillAmount > 0, "DPE: zero fill");

        Order storage maker = orders[makerOrderId];
        Order storage taker = orders[takerOrderId];

        require(maker.active, "DPE: maker order not active");
        require(taker.active, "DPE: taker order not active");
        require(
            maker.filledAmount + makerFillAmount <= maker.totalAmount,
            "DPE: maker fill exceeds remaining"
        );
        require(
            taker.filledAmount + takerFillAmount <= taker.totalAmount,
            "DPE: taker fill exceeds remaining"
        );

        // Verify TEE signature
        _verifyTEESignature(
            swapId, makerOrderId, takerOrderId,
            makerFillAmount, takerFillAmount,
            teeSignature
        );

        // ── Effects (before interactions – prevents reentrancy) ─────────────
        executedSwaps[swapId] = true;
        maker.filledAmount += makerFillAmount;
        taker.filledAmount += takerFillAmount;

        // Auto-deactivate fully filled orders
        if (maker.filledAmount == maker.totalAmount) {
            maker.active = false;
        }
        if (taker.filledAmount == taker.totalAmount) {
            taker.active = false;
        }

        // ── Interactions: atomic swap ───────────────────────────────────────
        uint256 makerToTaker = makerFillAmount; // maker's tokens → taker
        uint256 takerToMaker = takerFillAmount; // taker's tokens → maker

        if (feeEnabled) {
            uint256 makerFee = makerFillAmount * FEE_BPS / BPS_DENOMINATOR;
            uint256 takerFee = takerFillAmount * FEE_BPS / BPS_DENOMINATOR;
            collectedFees[maker.token] += makerFee;
            collectedFees[taker.token] += takerFee;
            makerToTaker -= makerFee;
            takerToMaker -= takerFee;
        }

        // Maker's token → Taker's trader  (Alice's Token A → Bob)
        IERC20(maker.token).safeTransfer(taker.trader, makerToTaker);
        // Taker's token → Maker's trader  (Bob's Token B → Alice)
        IERC20(taker.token).safeTransfer(maker.trader, takerToMaker);

        emit SwapExecuted(
            swapId, makerOrderId, takerOrderId,
            makerFillAmount, takerFillAmount
        );

        // Emit PartialFill for orders that still have remaining
        uint256 makerRemaining = maker.totalAmount - maker.filledAmount;
        if (makerRemaining > 0) {
            emit PartialFill(makerOrderId, maker.filledAmount, makerRemaining);
        }
        uint256 takerRemaining = taker.totalAmount - taker.filledAmount;
        if (takerRemaining > 0) {
            emit PartialFill(takerOrderId, taker.filledAmount, takerRemaining);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Core: cancelOrder  (P0 — 잔량 환불 / 취소)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Cancel an active order and refund the unfilled remainder.
     *         Only the order owner (trader) may cancel.
     *         If partially filled, only the unfilled portion is refunded.
     *
     * @param orderId  The order to cancel.
     */
    function cancelOrder(bytes32 orderId) external nonReentrant {
        Order storage o = orders[orderId];
        require(o.trader == msg.sender, "DPE: not order owner");
        require(o.active,              "DPE: order not active");

        // Effect
        o.active = false;
        uint256 refund = o.totalAmount - o.filledAmount;

        // Interaction
        if (refund > 0) {
            IERC20(o.token).safeTransfer(o.trader, refund);
        }

        emit Cancelled(orderId, o.trader, refund);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  View helpers
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Compute the raw struct hash the TEE signs for executeSwap.
     *
     *         Payload: chainId ‖ address(this) ‖ swapId ‖ makerOrderId ‖ takerOrderId
     *                  ‖ makerFillAmount ‖ takerFillAmount
     *
     *         The TEE calls `eth_sign` / `signMessage(bytes)` over this hash,
     *         which prepends the EIP-191 prefix before signing.
     */
    function getSwapStructHash(
        bytes32 swapId,
        bytes32 makerOrderId,
        bytes32 takerOrderId,
        uint256 makerFillAmount,
        uint256 takerFillAmount
    ) public view returns (bytes32) {
        return keccak256(abi.encodePacked(
            block.chainid,
            address(this),
            swapId,
            makerOrderId,
            takerOrderId,
            makerFillAmount,
            takerFillAmount
        ));
    }

    /// @notice Remaining unfilled amount for an order.
    function getOrderRemaining(bytes32 orderId) external view returns (uint256) {
        Order storage o = orders[orderId];
        if (!o.active) return 0;
        return o.totalAmount - o.filledAmount;
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Internal
    // ─────────────────────────────────────────────────────────────────────────

    function _verifyTEESignature(
        bytes32 swapId,
        bytes32 makerOrderId,
        bytes32 takerOrderId,
        uint256 makerFillAmount,
        uint256 takerFillAmount,
        bytes calldata sig
    ) internal view {
        bytes32 structHash = getSwapStructHash(
            swapId, makerOrderId, takerOrderId,
            makerFillAmount, takerFillAmount
        );
        bytes32 ethHash = MessageHashUtils.toEthSignedMessageHash(structHash);
        address recovered = ECDSA.recover(ethHash, sig);
        require(recovered == teeSignerAddress, "DPE: invalid TEE signature");
    }
}
