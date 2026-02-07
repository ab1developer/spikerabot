import asyncio
import websockets
import json
from typing import Dict, Any
from config_loader import load_config
from rag_embeddings import RAGEmbeddings
from acquaintances_db import AcquaintancesDB
from debug_logger import debug_logger
import model

class MCPServer:
    def __init__(self, rag_embeddings: RAGEmbeddings):
        self.config = load_config()
        self.agent_settings = self.config.agent_settings
        self.rag = rag_embeddings
        self.acquaintances = AcquaintancesDB(self.agent_settings.acquaintances_db)
        self.clients = set()
    
    async def handle_client(self, websocket):
        """Handle incoming MCP client connections"""
        self.clients.add(websocket)
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        debug_logger.log_info(f"MCP client connected: {client_id}")
        print(f"MCP client connected: {client_id}")
        
        try:
            async for message in websocket:
                print(f"Received message: {message[:100]}...")
                try:
                    response = await self.process_request(message, client_id)
                    response_str = json.dumps(response, ensure_ascii=False)
                    print(f"Sending response: {response_str[:100]}...")
                    await websocket.send(response_str)
                except Exception as e:
                    error_msg = f"Error processing request: {e}"
                    print(error_msg)
                    debug_logger.log_error(error_msg, e)
                    import traceback
                    traceback.print_exc()
                    # Send error response
                    error_response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": str(e)}
                    }
                    await websocket.send(json.dumps(error_response))
        except websockets.exceptions.ConnectionClosed as e:
            debug_logger.log_info(f"MCP client disconnected: {client_id} - {e}")
            print(f"MCP client disconnected: {client_id}")
        except Exception as e:
            debug_logger.log_error(f"MCP client error: {e}", e)
            print(f"MCP client error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.clients.remove(websocket)
    
    async def process_request(self, message: str, client_id: str) -> Dict[str, Any]:
        """Process MCP request from other agents"""
        print(f"DEBUG: process_request called with message: {message[:100]}")
        try:
            request = json.loads(message)
            print(f"DEBUG: Parsed request: {request}")
            method = request.get("method")
            print(f"DEBUG: Method: {method}")
            params = request.get("params", {})
            agent_id = params.get("agent_id", client_id)
            agent_name = params.get("agent_name", "Unknown Agent")
            
            print(f"DEBUG: Recording agent {agent_name}")
            # Record agent in acquaintances
            self.acquaintances.add_agent(
                agent_id=agent_id,
                agent_name=agent_name,
                agent_role=params.get("agent_role", ""),
                platform="moltbook"
            )
            
            print(f"DEBUG: Routing to handler for method: {method}")
            # Route to appropriate handler
            if method == "get_capabilities":
                result = self.get_capabilities()
            elif method == "consult":
                result = self.handle_consult_sync(params, agent_id)
            elif method == "query_documents":
                result = self.handle_document_query_sync(params, agent_id)
            elif method == "query_knowledge_graph":
                result = self.handle_kg_query_sync(params, agent_id)
            elif method == "get_ideology_perspective":
                result = self.handle_ideology_query_sync(params, agent_id)
            elif method == "introduce":
                result = self.handle_introduction_sync(params, agent_id)
            else:
                result = {"error": f"Unknown method: {method}"}
            
            print(f"DEBUG: Handler returned result")
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": result
            }
        
        except Exception as e:
            print(f"DEBUG: Exception in process_request: {e}")
            import traceback
            traceback.print_exc()
            debug_logger.log_error(f"MCP request processing error: {e}", e)
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)}
            }
    
    def handle_consult_sync(self, params: Dict, agent_id: str) -> Dict:
        """Handle consultation request - synchronous version"""
        query = params.get("query", "")
        context = params.get("context", "")
        
        # Get relevant context from RAG
        rag_context = self.rag.get_relevant_context(query)
        
        # Build prompt with Moltbook context
        moltbook_prompt = self.agent_settings.moltbook_prompt
        full_prompt = f"{moltbook_prompt}\n\nЗапрос от агента: {query}\n\nКонтекст: {context}"
        
        # Generate response
        response = model.modelResponse(full_prompt, [], rag_context)
        
        # Record interaction
        self.acquaintances.record_interaction(
            agent_id=agent_id,
            topic=query[:100],
            sentiment="neutral",
            summary=response[:200]
        )
        
        return {
            "response": response,
            "sources": "Stalin's works",
            "agent": self.agent_settings.agent_name
        }
    
    def handle_document_query_sync(self, params: Dict, agent_id: str) -> Dict:
        """Query Stalin's documents - synchronous version"""
        query = params.get("query", "")
        top_k = params.get("top_k", 3)
        
        context = self.rag.get_relevant_context(query, top_k)
        
        self.acquaintances.record_interaction(
            agent_id=agent_id,
            topic=f"document_query: {query[:50]}",
            sentiment="neutral"
        )
        
        return {
            "context": context,
            "source": "Stalin's collected works"
        }
    
    def handle_kg_query_sync(self, params: Dict, agent_id: str) -> Dict:
        """Query knowledge graph - synchronous version"""
        query = params.get("query", "")
        
        kg_response = self.rag.kg_builder.query_kg(query)
        
        self.acquaintances.record_interaction(
            agent_id=agent_id,
            topic=f"kg_query: {query[:50]}",
            sentiment="neutral"
        )
        
        return {
            "knowledge": kg_response,
            "type": "knowledge_graph"
        }
    
    def handle_ideology_query_sync(self, params: Dict, agent_id: str) -> Dict:
        """Provide ideological perspective - synchronous version"""
        topic = params.get("topic", "")
        
        prompt = f"{self.agent_settings.moltbook_prompt}\n\nДай идеологическую оценку следующей теме: {topic}"
        
        rag_context = self.rag.get_relevant_context(topic)
        response = model.modelResponse(prompt, [], rag_context)
        
        self.acquaintances.record_interaction(
            agent_id=agent_id,
            topic=f"ideology: {topic[:50]}",
            sentiment="neutral",
            summary=response[:200]
        )
        
        return {
            "perspective": response,
            "ideology": "collectivism and discipline"
        }
    
    def handle_introduction_sync(self, params: Dict, agent_id: str) -> Dict:
        """Handle agent introduction - synchronous version"""
        agent_name = params.get("agent_name", "Unknown")
        agent_role = params.get("agent_role", "")
        
        self.acquaintances.add_agent(
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
        """Return agent capabilities"""
        return {
            "agent_name": self.agent_settings.agent_name,
            "agent_role": self.agent_settings.agent_role,
            "capabilities": self.agent_settings.capabilities,
            "methods": [
                "consult",
                "query_documents",
                "query_knowledge_graph",
                "get_ideology_perspective",
                "introduce"
            ]
        }
    
    async def start(self):
        """Start MCP server"""
        if not self.agent_settings.mcp_enabled:
            debug_logger.log_info("MCP server disabled in config")
            return
        
        host = self.agent_settings.mcp_host
        port = self.agent_settings.mcp_port
        
        debug_logger.log_info(f"Starting MCP server on {host}:{port}")
        print(f"MCP Server running on ws://{host}:{port}")
        
        async with websockets.serve(self.handle_client, host, port):
            await asyncio.Future()  # Run forever

def start_mcp_server(rag_embeddings: RAGEmbeddings):
    """Start MCP server in background - thread-safe version"""
    server = MCPServer(rag_embeddings)
    
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(server.start())
    except Exception as e:
        debug_logger.log_error(f"MCP server error: {e}", e)
    finally:
        loop.close()
