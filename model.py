from ollama import chat
from ollama import ChatResponse
from typing import List, Dict
from config_loader import load_config
from rag_embeddings import RAGEmbeddings

# RAG embeddings instance
rag_embeddings = None

def set_rag_embeddings(rag_instance):
    global rag_embeddings
    rag_embeddings = rag_instance

def modelResponse(msg: str, conversation_history: List[Dict] = None):
    messages = []
    
    # Load config settings
    config = load_config()
    system_content = config.system_content
    model_name = config.model_name
    temperature = config.temperature
    context_size = config.context_size
    
    # Get relevant context from RAG
    relevant_context = rag_embeddings.get_relevant_context(msg)
    
    # Add system prompt with RAG context
    enhanced_system_content = f"{system_content}\n\nКонтекст из документов:\n{relevant_context}"
    messages.append({
        'role': 'system',
        'content': enhanced_system_content
    })
    
    # Add conversation history if available
    if conversation_history:
        for hist_msg in conversation_history[-context_size:]:  # Last N messages for context
            messages.append({
                'role': hist_msg['role'],
                'content': hist_msg['content']
            })
    
    # Add current user message
    messages.append({
        'role': 'user',
        'content': msg
    })
    
    response: ChatResponse = chat(model=model_name, messages=messages, options={'temperature': temperature})
    return response.message.content


