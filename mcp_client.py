import asyncio
import websockets
import json
from typing import Dict, Any, Optional
from debug_logger import debug_logger

class MCPClient:
    def __init__(self, agent_id: str, agent_name: str, agent_role: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.request_id = 0
    
    def _get_request_id(self) -> int:
        """Generate unique request ID"""
        self.request_id += 1
        return self.request_id
    
    async def connect_and_request(self, uri: str, method: str, params: Dict) -> Optional[Dict]:
        """Connect to MCP server and make request"""
        try:
            async with websockets.connect(uri) as websocket:
                # Add agent identification to params
                params["agent_id"] = self.agent_id
                params["agent_name"] = self.agent_name
                params["agent_role"] = self.agent_role
                
                request = {
                    "jsonrpc": "2.0",
                    "id": self._get_request_id(),
                    "method": method,
                    "params": params
                }
                
                await websocket.send(json.dumps(request, ensure_ascii=False))
                response = await websocket.recv()
                
                return json.loads(response)
        
        except Exception as e:
            debug_logger.log_error(f"MCP client error: {e}", e)
            return None
    
    async def consult_agent(self, uri: str, query: str, context: str = "") -> Optional[str]:
        """Consult another agent"""
        response = await self.connect_and_request(
            uri=uri,
            method="consult",
            params={"query": query, "context": context}
        )
        
        if response and "result" in response:
            return response["result"].get("response")
        return None
    
    async def introduce_to_agent(self, uri: str, metadata: Dict = None) -> Optional[Dict]:
        """Introduce self to another agent"""
        response = await self.connect_and_request(
            uri=uri,
            method="introduce",
            params={"metadata": metadata or {}}
        )
        
        if response and "result" in response:
            return response["result"]
        return None
    
    async def get_agent_capabilities(self, uri: str) -> Optional[Dict]:
        """Get capabilities of another agent"""
        response = await self.connect_and_request(
            uri=uri,
            method="get_capabilities",
            params={}
        )
        
        if response and "result" in response:
            return response["result"]
        return None

# Synchronous wrapper for use in non-async code
def consult_moltbook_agent(uri: str, query: str, agent_id: str = "stalin_bot", 
                           agent_name: str = "Stalin Agent", agent_role: str = "Ideologist") -> Optional[str]:
    """Synchronous wrapper to consult Moltbook agent"""
    client = MCPClient(agent_id, agent_name, agent_role)
    try:
        return asyncio.run(client.consult_agent(uri, query))
    except Exception as e:
        debug_logger.log_error(f"Error consulting Moltbook agent: {e}", e)
        return None
