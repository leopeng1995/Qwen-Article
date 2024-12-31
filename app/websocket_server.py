import json
import asyncio
from typing import Dict, Set

import websockets


class PipelineWebSocketServer:
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.connections: Dict[str, Set[websockets.WebSocketServerProtocol]] = {}
    
    async def register(self, websocket: websockets.WebSocketServerProtocol, pipeline_id: str):
        if pipeline_id not in self.connections:
            self.connections[pipeline_id] = set()
        self.connections[pipeline_id].add(websocket)
    
    async def unregister(self, websocket: websockets.WebSocketServerProtocol, pipeline_id: str):
        if pipeline_id in self.connections:
            self.connections[pipeline_id].discard(websocket)
            if not self.connections[pipeline_id]:
                del self.connections[pipeline_id]
    
    async def notify_pipeline_status(self, pipeline_id: str, status_data: str):
        if pipeline_id in self.connections:
            websockets_to_remove = set()
            for websocket in self.connections[pipeline_id]:
                try:
                    await websocket.send(status_data)
                except websockets.ConnectionClosed:
                    websockets_to_remove.add(websocket)
            
            # 清理已关闭的连接
            for websocket in websockets_to_remove:
                await self.unregister(websocket, pipeline_id)
    
    async def handler(self, websocket: websockets.WebSocketServerProtocol):
        try:
            # 等待客户端发送想要监控的 pipeline_id
            message = await websocket.recv()
            data = json.loads(message)
            pipeline_id = data.get('pipeline_id')
            
            if not pipeline_id:
                await websocket.send(json.dumps({"error": "No pipeline_id provided"}))
                return
            
            await self.register(websocket, pipeline_id)
            # 发送初始连接确认消息
            await websocket.send(json.dumps({
                "status": "connected",
                "pipeline_id": pipeline_id,
                "message": "Successfully connected to pipeline monitoring"
            }))
            
            # 保持连接打开，等待直到连接关闭
            try:
                await websocket.wait_closed()
            except websockets.ConnectionClosed:
                pass
                
        except websockets.ConnectionClosed:
            # 处理连接关闭的情况
            if 'pipeline_id' in locals():
                await self.unregister(websocket, pipeline_id)
        except Exception as e:
            print(f"WebSocket error: {str(e)}")
            if 'pipeline_id' in locals():
                await self.unregister(websocket, pipeline_id)
    
    async def start(self):
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()  # 运行直到被终止
