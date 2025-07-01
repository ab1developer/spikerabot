from ollama import chat
from ollama import ChatResponse
from typing import List, Dict
from config_loader import load_config

def modelResponse(msg: str, conversation_history: List[Dict] = None):
    messages = []
    
    # Load config settings
    config = load_config()
    system_content = config.system_content
    temperature = config.temperature
    context_size = config.context_size
    
    # Add system prompt
    messages.append({
        'role': 'system',
        'content': system_content
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
    
    response: ChatResponse = chat(model='gemma3:12b', messages=messages, options={'temperature': temperature})
    return response.message.content


