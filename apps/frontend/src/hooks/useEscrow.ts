import { useCallback } from 'react';
import { useAccount } from 'wagmi';
import { bscTestnet } from 'wagmi/chains';
import { getPublicClient, waitForTransactionReceipt, writeContract } from 'wagmi/actions';
import { formatUnits, padHex, type Hash } from 'viem';
import { wagmiConfig } from '../lib/wagmi';
import { config, TOKEN_ADDRESSES } from '../config';
import { ERC20_ABI, ESCROW_ABI } from '../abi';

/**
 * orderId (백엔드의 uuid4().hex) → bytes32 padded hex.
 */
function toBytes32(orderId: string): `0x${string}` {
  const hex = orderId.startsWith('0x') ? orderId : `0x${orderId}`;
  return padHex(hex as `0x${string}`, { size: 32 });
}

/**
 * deposit / cancelOrder 등의 결과 — App.tsx의 `receipt?.hash` 접근을 보존.
 */
interface TxResult {
  hash: Hash;
  blockNumber: bigint;
}

/**
 * DarkPoolEscrow 호출 어댑터. wagmi v3 `wagmi/actions`의 명령형 API를 사용.
 *
 * - writes (`writeContract`): wagmi v3 타입 시그니처가 union resolution으로
 *   `chain`과 `account`를 명시 요구한다. 연결된 지갑에서 `useAccount`로
 *   address를 받아 명시적으로 전달.
 * - reads (`readContract`): const-narrowed ABI(`tools/sync-abi.mjs` 생성)
 *   덕분에 functionName 추론이 작동.
 *
 * 기존 ethers 기반 useEscrow의 공개 함수 6개 시그니처는 그대로 보존해서
 * App.tsx 변경 면적을 최소화한다.
 */
export function useEscrow() {
  const escrowAddress = config.ESCROW_ADDRESS as `0x${string}` | '';
  const { address: account } = useAccount();

  const requireAccount = useCallback((): `0x${string}` => {
    if (!account) throw new Error('Wallet not connected');
    return account;
  }, [account]);

  /** ERC20 approve — Escrow 컨트랙트에 토큰 사용 승인 */
  const approveToken = useCallback(
    async (tokenAddress: string, amount: bigint): Promise<TxResult> => {
      if (!escrowAddress) throw new Error('ESCROW_ADDRESS not configured');
      const hash = await writeContract(wagmiConfig, {
        chain: bscTestnet,
        account: requireAccount(),
        abi: ERC20_ABI,
        address: tokenAddress as `0x${string}`,
        functionName: 'approve',
        args: [escrowAddress, amount],
      });
      const receipt = await waitForTransactionReceipt(wagmiConfig, { hash, confirmations: 1 });
      return { hash, blockNumber: receipt.blockNumber };
    },
    [escrowAddress, requireAccount],
  );

  /** Escrow deposit — 토큰 예치 */
  const deposit = useCallback(
    async (orderId: string, tokenAddress: string, amount: bigint): Promise<TxResult> => {
      if (!escrowAddress) throw new Error('ESCROW_ADDRESS not configured');
      const hash = await writeContract(wagmiConfig, {
        chain: bscTestnet,
        account: requireAccount(),
        abi: ESCROW_ABI,
        address: escrowAddress,
        functionName: 'deposit',
        args: [toBytes32(orderId), tokenAddress as `0x${string}`, amount],
      });
      const receipt = await waitForTransactionReceipt(wagmiConfig, { hash, confirmations: 1 });
      return { hash, blockNumber: receipt.blockNumber };
    },
    [escrowAddress, requireAccount],
  );

  /** 주문 취소 — 미체결 잔량 환불 */
  const cancelOrder = useCallback(
    async (orderId: string): Promise<TxResult> => {
      if (!escrowAddress) throw new Error('ESCROW_ADDRESS not configured');
      const hash = await writeContract(wagmiConfig, {
        chain: bscTestnet,
        account: requireAccount(),
        abi: ESCROW_ABI,
        address: escrowAddress,
        functionName: 'cancelOrder',
        args: [toBytes32(orderId)],
      });
      const receipt = await waitForTransactionReceipt(wagmiConfig, { hash, confirmations: 1 });
      return { hash, blockNumber: receipt.blockNumber };
    },
    [escrowAddress, requireAccount],
  );

  /**
   * 읽기 호출은 wagmi의 `getPublicClient`로 viem PublicClient를 얻어
   * `client.readContract({...})` 직접 호출.
   *
   * 모든 read 호출에 `// @ts-expect-error`가 붙어 있는 이유:
   * viem 2.47의 `ReadContractParameters` union이 EIP-7702 set-code 트랜잭션
   * 변형의 `authorizationList` 필드를 일반 read 호출에까지 required로 흘려
   * "타입엔 누락, 런타임엔 무관" 미스매치가 생긴다. const-narrowed ABI나
   * `getContract`/`wagmi/actions/readContract` 모두 같은 union을 거쳐서
   * 우회 불가. viem upstream이 이를 고치면 expect-error가 빨간불을 띄워
   * 자동으로 알려준다.
   */

  /** 온체인 주문 상태 조회 */
  const getOrderState = useCallback(
    async (orderId: string) => {
      if (!escrowAddress) return null;
      const publicClient = getPublicClient(wagmiConfig, { chainId: bscTestnet.id });
      if (!publicClient) return null;
      const [trader, token, totalAmount, filledAmount, active] = await publicClient.readContract(
        // @ts-expect-error viem 2.47 EIP-7702 union: authorizationList 강제 요구 quirk
        {
          abi: ESCROW_ABI,
          address: escrowAddress,
          functionName: 'orders',
          args: [toBytes32(orderId)],
        },
      );
      return { trader, token, totalAmount, filledAmount, active };
    },
    [escrowAddress],
  );

  /** 미체결 잔량 조회 */
  const getOrderRemaining = useCallback(
    async (orderId: string): Promise<bigint> => {
      if (!escrowAddress) return 0n;
      const publicClient = getPublicClient(wagmiConfig, { chainId: bscTestnet.id });
      if (!publicClient) return 0n;
      return publicClient.readContract(
        // @ts-expect-error viem 2.47 EIP-7702 union: authorizationList 강제 요구 quirk
        {
          abi: ESCROW_ABI,
          address: escrowAddress,
          functionName: 'getOrderRemaining',
          args: [toBytes32(orderId)],
        },
      );
    },
    [escrowAddress],
  );

  /** ERC20 잔고 조회 */
  const getTokenBalance = useCallback(
    async (tokenSymbol: string, walletAddress: string): Promise<string> => {
      const tokenAddress = TOKEN_ADDRESSES[tokenSymbol];
      if (!tokenAddress) return '0';

      try {
        const publicClient = getPublicClient(wagmiConfig, { chainId: bscTestnet.id });
        if (!publicClient) return '0';
        const [balance, decimals] = await Promise.all([
          publicClient.readContract(
            // @ts-expect-error viem 2.47 EIP-7702 union: authorizationList 강제 요구 quirk
            {
              abi: ERC20_ABI,
              address: tokenAddress as `0x${string}`,
              functionName: 'balanceOf',
              args: [walletAddress as `0x${string}`],
            },
          ),
          publicClient.readContract(
            // @ts-expect-error viem 2.47 EIP-7702 union: authorizationList 강제 요구 quirk
            {
              abi: ERC20_ABI,
              address: tokenAddress as `0x${string}`,
              functionName: 'decimals',
            },
          ),
        ]);
        return formatUnits(balance as bigint, Number(decimals));
      } catch {
        return '0';
      }
    },
    [],
  );

  return {
    approveToken,
    deposit,
    cancelOrder,
    getOrderState,
    getOrderRemaining,
    getTokenBalance,
  };
}
