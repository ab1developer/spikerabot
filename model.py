from ollama import chat, Client
from ollama import ChatResponse
from typing import List, Dict, Optional
from config_loader import load_config
from rag_embeddings import RAGEmbeddings
import time

# RAG embeddings instance
rag_embeddings = None

# Ollama client with explicit host
client = Client(host='http://localhost:11434')

def set_rag_embeddings(rag_instance):
    global rag_embeddings
    rag_embeddings = rag_instance


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
        options={'temperature': effective_temperature},
    )
    return response.message.content


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
        timeout: Seconds before giving up (best-effort; Ollama client does
                 not natively enforce per-request timeouts, so we wrap in a
                 thread to respect it).

    Returns:
        The model's response text, or empty string on failure.
    """
    import threading

    config = load_config()
    model_name = config.model_name
    result: list = []
    exc: list = []

    def _call():
        try:
            resp: ChatResponse = client.chat(
                model=model_name,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': temperature},
            )
            result.append(resp.message.content)
        except Exception as e:  # noqa: BLE001
            exc.append(e)

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if exc:
        raise exc[0]
    if not result:
        raise TimeoutError(f"raw_llm_call timed out after {timeout}s")
    return result[0]
