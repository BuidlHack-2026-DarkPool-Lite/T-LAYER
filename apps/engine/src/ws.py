"""WebSocket 연결 관리."""

import logging

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """활성 WebSocket 연결을 관리하고 브로드캐스트한다."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        try:
            self._connections.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, data: dict) -> None:
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except (RuntimeError, WebSocketDisconnect):
                self._connections.remove(ws)
            except Exception:
                logger.exception("broadcast 중 예기치 않은 오류")
                try:
                    self._connections.remove(ws)
                except ValueError:
                    pass
