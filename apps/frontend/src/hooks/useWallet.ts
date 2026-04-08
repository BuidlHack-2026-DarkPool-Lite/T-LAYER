import { useState, useEffect, useCallback } from 'react';
import { ethers } from 'ethers';
import { BSC_TESTNET } from '../config';

interface WalletState {
  address: string | null;
  isConnected: boolean;
  chainId: number | null;
  isCorrectChain: boolean;
  provider: ethers.BrowserProvider | null;
  signer: ethers.JsonRpcSigner | null;
  connect: () => Promise<void>;
  disconnect: () => void;
  switchToTestnet: () => Promise<void>;
}

export function useWallet(): WalletState {
  const [address, setAddress] = useState<string | null>(null);
  const [chainId, setChainId] = useState<number | null>(null);
  const [provider, setProvider] = useState<ethers.BrowserProvider | null>(null);
  const [signer, setSigner] = useState<ethers.JsonRpcSigner | null>(null);

  const isConnected = !!address;
  const isCorrectChain = chainId === BSC_TESTNET.chainId;

  const setupProvider = useCallback(async () => {
    if (!window.ethereum) return;
    const p = new ethers.BrowserProvider(window.ethereum);
    setProvider(p);

    try {
      const network = await p.getNetwork();
      setChainId(Number(network.chainId));
    } catch {
      // ignore
    }

    const accounts: string[] = await window.ethereum.request({ method: 'eth_accounts' });
    if (accounts.length > 0) {
      setAddress(accounts[0]);
      const s = await p.getSigner();
      setSigner(s);
    }
  }, []);

  useEffect(() => {
    setupProvider();

    if (!window.ethereum) return;

    const handleAccountsChanged = (accounts: string[]) => {
      if (accounts.length === 0) {
        setAddress(null);
        setSigner(null);
      } else {
        setAddress(accounts[0]);
        setupProvider();
      }
    };

    const handleChainChanged = () => {
      // 체인 변경 시 provider 재설정
      setupProvider();
    };

    window.ethereum.on('accountsChanged', handleAccountsChanged);
    window.ethereum.on('chainChanged', handleChainChanged);

    return () => {
      window.ethereum?.removeListener('accountsChanged', handleAccountsChanged);
      window.ethereum?.removeListener('chainChanged', handleChainChanged);
    };
  }, [setupProvider]);

  const connect = useCallback(async () => {
    if (!window.ethereum) {
      window.open('https://metamask.io/download/', '_blank');
      return;
    }

    const accounts: string[] = await window.ethereum.request({
      method: 'eth_requestAccounts',
    });

    if (accounts.length > 0) {
      const p = new ethers.BrowserProvider(window.ethereum);
      const s = await p.getSigner();
      const network = await p.getNetwork();

      setProvider(p);
      setSigner(s);
      setAddress(accounts[0]);
      setChainId(Number(network.chainId));
    }
  }, []);

  const disconnect = useCallback(() => {
    setAddress(null);
    setSigner(null);
    setProvider(null);
    setChainId(null);
  }, []);

  const switchToTestnet = useCallback(async () => {
    if (!window.ethereum) return;

    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: BSC_TESTNET.chainIdHex }],
      });
    } catch (err: any) {
      // 4902 = chain not added
      if (err.code === 4902) {
        await window.ethereum.request({
          method: 'wallet_addEthereumChain',
          params: [
            {
              chainId: BSC_TESTNET.chainIdHex,
              chainName: BSC_TESTNET.name,
              nativeCurrency: BSC_TESTNET.currency,
              rpcUrls: [BSC_TESTNET.rpcUrl],
              blockExplorerUrls: [BSC_TESTNET.blockExplorer],
            },
          ],
        });
      }
    }
  }, []);

  return {
    address,
    isConnected,
    chainId,
    isCorrectChain,
    provider,
    signer,
    connect,
    disconnect,
    switchToTestnet,
  };
}
