/** 환경변수 + 체인 설정 */

export const config = {
  API_URL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  WS_URL: import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws',
  ESCROW_ADDRESS: import.meta.env.VITE_ESCROW_ADDRESS || '',
};

/** BSC Testnet 체인 파라미터 */
export const BSC_TESTNET = {
  chainId: 97,
  chainIdHex: '0x61',
  name: 'BNB Smart Chain Testnet',
  rpcUrl: 'https://data-seed-prebsc-1-s1.bnbchain.org:8545',
  blockExplorer: 'https://testnet.bscscan.com',
  currency: {
    name: 'tBNB',
    symbol: 'tBNB',
    decimals: 18,
  },
};

/** 토큰 컨트랙트 주소 (BSC Testnet) */
export const TOKEN_ADDRESSES: Record<string, string> = {
  BNB: import.meta.env.VITE_TOKEN_BNB || '',
  USDT: import.meta.env.VITE_TOKEN_USDT || '',
  ETH: import.meta.env.VITE_TOKEN_ETH || '',
  BTC: import.meta.env.VITE_TOKEN_BTC || '',
  SOL: import.meta.env.VITE_TOKEN_SOL || '',
  XRP: import.meta.env.VITE_TOKEN_XRP || '',
};
