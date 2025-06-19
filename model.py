from ollama import chat
from ollama import ChatResponse
from typing import List, Dict

def modelResponse(msg: str, conversation_history: List[Dict] = None):
    messages = []
    
    # Add system prompt
    messages.append({
        'role': 'system',
        'content': 'Ты - блатной. Отвечай на сообщения по фене, учитывая контекст предыдущих сообщений.'
    })
    
    # Add conversation history if available
    if conversation_history:
        for hist_msg in conversation_history[-5:]:  # Last 5 messages for context
            messages.append({
                'role': hist_msg['role'],
                'content': hist_msg['content']
            })
    
    # Add current user message
    messages.append({
        'role': 'user',
        'content': msg
    })
    
    response: ChatResponse = chat(model='gemma3:12b', messages=messages)
    return response.message.content


