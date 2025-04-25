from ollama import chat
from ollama import ChatResponse

def modelResponse(msg):
  messages = []
  context = ''   
  # Add context if available
  if context:
    messages.append({
        'role': 'system',
        'content': f"Context: {context}"
    })
    
    # Add user message
    messages.append({
        'role': 'user',
        'content': msg,
    })
  response: ChatResponse = chat(model='gemma3:27b', messages=[
    {
    'role': 'user',
    'content': 'Ты - блатной. Отвечай на сообщение по фене: ' + msg,
    },
  ])

  return response.message.content


