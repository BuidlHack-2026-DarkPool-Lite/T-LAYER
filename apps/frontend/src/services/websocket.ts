import { config } from '../config';

export interface WsEvent {
  action: 'created' | 'matched' | 'cancelled';
  order?: any;
  results?: any[];
  [key: string]: any;
}

interface WsOptions {
  onMessage: (event: WsEvent) => void;
  onStatusChange: (connected: boolean) => void;
}

/**
 * WebSocket 매니저 — 자동 재연결 (exponential backoff)
 * 반환된 close()를 호출하면 연결 종료 + 재연결 중지
 */
export function createWebSocket(options: WsOptions): { close: () => void } {
  let ws: WebSocket | null = null;
  let reconnectDelay = 1000;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  function connect() {
    if (stopped) return;

    try {
      ws = new WebSocket(config.WS_URL);
    } catch {
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      reconnectDelay = 1000; // 재연결 성공 시 딜레이 리셋
      options.onStatusChange(true);
    };

    ws.onmessage = (e) => {
      try {
        const data: WsEvent = JSON.parse(e.data);
        options.onMessage(data);
      } catch {
        // 파싱 실패 무시
      }
    };

    ws.onclose = () => {
      options.onStatusChange(false);
      scheduleReconnect();
    };

    ws.onerror = () => {
      ws?.close();
    };
  }

  function scheduleReconnect() {
    if (stopped) return;
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 10000);
      connect();
    }, reconnectDelay);
  }

  function close() {
    stopped = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    ws?.close();
    ws = null;
  }

  connect();

  return { close };
}
