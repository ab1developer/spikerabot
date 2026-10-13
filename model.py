from ollama import chat, Client
from ollama import ChatResponse
from typing import List, Dict, Optional
from config_loader import load_config
from rag_embeddings import RAGEmbeddings
from inference_scheduler import foreground_inference
import time

# RAG embeddings instance
rag_embeddings = None

# Ollama client with explicit host
client = Client(host='http://localhost:11434', timeout=load_config().request_timeout)

def set_rag_embeddings(rag_instance):
    global rag_embeddings
    rag_embeddings = rag_instance


@foreground_inference
def modelResponse(
    msg: str,
    conversation_history: List[Dict] = None,
    document_context: str = None,
    temperature: Optional[float] = None,
) -> str:
    """Generate a full persona-aware LLM response with RAG context injected.

    Args:
        msg: The user's message text.
        conversation_history: List of prior {role, content} dicts.
        document_context: Optional extra context from an attached document.
        temperature: Override the config temperature (e.g. pass 0 for determinism).
                     Defaults to config.temperature when None.
    """
    messages = []

    config = load_config()
    system_content = config.system_content
    model_name = config.model_name
    effective_temperature = temperature if temperature is not None else config.temperature
    context_size = config.context_size

    # Get relevant context from RAG
    relevant_context = rag_embeddings.get_relevant_context(msg)

    # Build system prompt with RAG context
    context_parts = [f"Контекст из документов:\n{relevant_context}"]
    if document_context:
        context_parts.append(f"Контекст из прикрепленного документа:\n{document_context}")

    enhanced_system_content = f"{system_content}\n\n{chr(10).join(context_parts)}"
    messages.append({'role': 'system', 'content': enhanced_system_content})

    # Add conversation history (last N turns)
    if conversation_history:
        for hist_msg in conversation_history[-context_size:]:
            messages.append({'role': hist_msg['role'], 'content': hist_msg['content']})

    messages.append({'role': 'user', 'content': msg})

    response: ChatResponse = client.chat(
        model=model_name,
        messages=messages,
        options={
            'temperature': effective_temperature,
            'num_ctx': config.ollama_context_window,
        },
        think=False,
    )
    return response.message.content


@foreground_inference
def raw_llm_call(
    prompt: str,
    temperature: float = 0.0,
    timeout: int = 15,
) -> str:
    """Bare Ollama call with NO RAG context and NO persona system prompt.

    Used by the intent classifier so it gets clean, deterministic output
    without Stalin-persona noise or expensive vector lookups.

    Args:
        prompt: The full prompt to send as the user turn.
        temperature: Defaults to 0 for determinism.
        timeout: HTTP timeout in seconds for the classifier call.

    Returns:
        The model's response text, or empty string on failure.
    """
    config = load_config()
    # Set the transport timeout so a timed-out classifier does not leave a
    # background client thread competing with the normal chat request.
    classifier_client = Client(host='http://localhost:11434', timeout=timeout)
    response: ChatResponse = classifier_client.chat(
        model=config.model_name,
        messages=[{'role': 'user', 'content': prompt}],
        options={
            'temperature': temperature,
            'num_ctx': config.ollama_context_window,
            'num_predict': 256,
        },
        think=False,
    )
    return response.message.content
