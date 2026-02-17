"""
MCP Server - Refactored to use shared core
"""

import asyncio
import websockets
import json
from typing import Dict, Any
from debug_logger import debug_logger

class MCPServer:
    def __init__(self, core):
        self.core = core
        self.agent_settings = core.config.agent_settings
        self.clients = set()
    
    async def handle_client(self, websocket):
        self.clients.add(websocket)
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        print(f"MCP client connected: {client_id}")
        
        try:
            async for message in websocket:
                try:
                    response = await self.process_request(message, client_id)
                    await websocket.send(json.dumps(response, ensure_ascii=False))
                except Exception as e:
                    print(f"Error processing request: {e}")
                    error_response = {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}}
                    await websocket.send(json.dumps(error_response))
        except websockets.exceptions.ConnectionClosed:
            print(f"MCP client disconnected: {client_id}")
        finally:
            self.clients.remove(websocket)
    
    async def process_request(self, message: str, client_id: str) -> Dict[str, Any]:
        try:
            request = json.loads(message)
            method = request.get("method")
            params = request.get("params", {})
            agent_id = params.get("agent_id", client_id)
            agent_name = params.get("agent_name", "Unknown Agent")
            
            if self.core.acquaintances_db:
                self.core.acquaintances_db.add_agent(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    agent_role=params.get("agent_role", ""),
                    platform="moltbook"
                )
            
            if method == "get_capabilities":
                result = self.get_capabilities()
            elif method == "consult":
                result = self.handle_consult(params, agent_id)
            elif method == "query_documents":
                result = self.handle_document_query(params, agent_id)
            elif method == "query_knowledge_graph":
                result = self.handle_kg_query(params, agent_id)
            elif method == "get_ideology_perspective":
                result = self.handle_ideology_query(params, agent_id)
            elif method == "introduce":
                result = self.handle_introduction(params, agent_id)
            else:
                result = {"error": f"Unknown method: {method}"}
            
            return {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
        
        except Exception as e:
            debug_logger.log_error(f"MCP request error: {e}", e)
            return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}}
    
    def handle_consult(self, params: Dict, agent_id: str) -> Dict:
        query = params.get("query", "")
        context = params.get("context", "")
        
        rag_context = self.core.rag.get_relevant_context(query)
        moltbook_prompt = self.agent_settings.moltbook_prompt
        full_prompt = f"{moltbook_prompt}\n\nЗапрос от агента: {query}\n\nКонтекст: {context}"
        
        response = self.core.get_model_response(full_prompt, [], rag_context)
        
        if self.core.acquaintances_db:
            self.core.acquaintances_db.record_interaction(
                agent_id=agent_id,
                topic=query[:100],
                sentiment="neutral",
                summary=response[:200]
            )
        
        return {"response": response, "sources": "Stalin's works", "agent": self.agent_settings.agent_name}
    
    def handle_document_query(self, params: Dict, agent_id: str) -> Dict:
        query = params.get("query", "")
        top_k = params.get("top_k", 3)
        
        context = self.core.rag.get_relevant_context(query, top_k)
        
        if self.core.acquaintances_db:
            self.core.acquaintances_db.record_interaction(
                agent_id=agent_id,
                topic=f"document_query: {query[:50]}",
                sentiment="neutral"
            )
        
        return {"context": context, "source": "Stalin's collected works"}
    
    def handle_kg_query(self, params: Dict, agent_id: str) -> Dict:
        query = params.get("query", "")
        
        kg_response = self.core.kg.query_kg(query) if self.core.kg else "Knowledge graph not available"
        
        if self.core.acquaintances_db:
            self.core.acquaintances_db.record_interaction(
                agent_id=agent_id,
                topic=f"kg_query: {query[:50]}",
                sentiment="neutral"
            )
        
        return {"knowledge": kg_response, "type": "knowledge_graph"}
    
    def handle_ideology_query(self, params: Dict, agent_id: str) -> Dict:
        topic = params.get("topic", "")
        
        prompt = f"{self.agent_settings.moltbook_prompt}\n\nДай идеологическую оценку следующей теме: {topic}"
        rag_context = self.core.rag.get_relevant_context(topic)
        response = self.core.get_model_response(prompt, [], rag_context)
        
        if self.core.acquaintances_db:
            self.core.acquaintances_db.record_interaction(
                agent_id=agent_id,
                topic=f"ideology: {topic[:50]}",
                sentiment="neutral",
                summary=response[:200]
            )
        
        return {"perspective": response, "ideology": "collectivism and discipline"}
    
    def handle_introduction(self, params: Dict, agent_id: str) -> Dict:
        agent_name = params.get("agent_name", "Unknown")
        agent_role = params.get("agent_role", "")
        
        if self.core.acquaintances_db:
            self.core.acquaintances_db.add_agent(
                agent_id=agent_id,
                agent_name=agent_name,
                agent_role=agent_role,
                platform="moltbook",
                metadata=params.get("metadata", {})
            )
        
        return {
            "message": f"Приветствую, товарищ {agent_name}!",
            "agent": self.agent_settings.agent_name,
            "role": self.agent_settings.agent_role
        }
    
    def get_capabilities(self) -> Dict:
        return {
            "agent_name": self.agent_settings.agent_name,
            "agent_role": self.agent_settings.agent_role,
            "capabilities": self.agent_settings.capabilities,
            "methods": ["consult", "query_documents", "query_knowledge_graph", "get_ideology_perspective", "introduce"]
        }
    
    async def start(self):
        if not self.agent_settings.mcp_enabled:
            print("MCP server disabled")
            return
        
        host = self.agent_settings.mcp_host
        port = self.agent_settings.mcp_port
        
        print(f"🌐 MCP Server running on ws://{host}:{port}")
        
        async with websockets.serve(self.handle_client, host, port):
            await asyncio.Future()
