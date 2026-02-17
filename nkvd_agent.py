"""
NKVD Agent - ReAct (Reason + Act) pattern implementation
Routes user queries to appropriate tools and synthesizes responses
"""

import json
import re
from tools import NKVDArsenal

ROUTER_SYSTEM_PROMPT = """Ты - координатор НКВД. Анализируй запрос и выбирай инструмент.

ИНСТРУМЕНТЫ:
- "razvedka": поиск в интернете (для вопросов о текущих событиях, фактах, новостях)
- "gosplan": математические вычисления (для арифметики, формул)
- "answer": прямой ответ (для философских вопросов, мнений, общения)

ФОРМАТ ОТВЕТА (ТОЛЬКО JSON):
{
  "tool": "razvedka" | "gosplan" | "answer",
  "args": "поисковый запрос | математическое выражение | текст ответа",
  "thought": "почему выбран этот инструмент"
}

ПРИМЕРЫ:
Запрос: "Найди информацию о ценах на нефть"
{"tool": "razvedka", "args": "цены на нефть сегодня", "thought": "нужна актуальная информация"}

Запрос: "Посчитай 500 * 1.5"
{"tool": "gosplan", "args": "500 * 1.5", "thought": "математическое вычисление"}

Запрос: "Что ты думаешь о коллективизации?"
{"tool": "answer", "args": "Коллективизация - необходимый этап...", "thought": "идеологический вопрос"}

ОТВЕЧАЙ ТОЛЬКО JSON. НЕ ДОБАВЛЯЙ ТЕКСТ ДО ИЛИ ПОСЛЕ JSON."""

class NKVDAgent:
    def __init__(self, core):
        self.core = core
        self.arsenal = NKVDArsenal()
    
    async def execute_order(self, user_input: str) -> str:
        """Execute ReAct loop: Reason -> Act -> Respond"""
        
        # Step 1: Router decision
        router_prompt = f"{ROUTER_SYSTEM_PROMPT}\n\nЗАПРОС: {user_input}"
        
        try:
            router_response = self.core.get_model_response(router_prompt, [])
            decision = self._parse_json(router_response)
            
            if not decision:
                # Fallback to direct answer
                return self.core.get_model_response(user_input, [])
            
            tool = decision.get("tool")
            args = decision.get("args", "")
            thought = decision.get("thought", "")
            
            print(f"🧠 NKVD Decision: {tool} | Thought: {thought}")
            
            # Step 2: Execute tool
            if tool == "razvedka":
                search_results = await self.arsenal.razvedka(args)
                
                # Step 3: Synthesize response with search data
                synthesis_prompt = f"""Пользователь спросил: {user_input}

Данные разведки:
{search_results}

Ответь как товарищ Сталин, используя найденную информацию."""
                
                return self.core.get_model_response(synthesis_prompt, [])
            
            elif tool == "gosplan":
                calc_result = await self.arsenal.gosplan_calc(args)
                return f"Госплан докладывает: {calc_result}"
            
            elif tool == "answer":
                # Direct answer (already styled by router or needs styling)
                if len(args) > 50:
                    return args
                else:
                    return self.core.get_model_response(user_input, [])
            
            else:
                return self.core.get_model_response(user_input, [])
        
        except Exception as e:
            print(f"❌ NKVD Agent error: {e}")
            # Fallback to standard response
            return self.core.get_model_response(user_input, [])
    
    def _parse_json(self, text: str) -> dict:
        """Parse JSON from LLM response, handling markdown backticks"""
        try:
            # Remove markdown code blocks
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)
            text = text.strip()
            
            # Find JSON object
            match = re.search(r'\{[^}]+\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)
            
            return None
        except Exception as e:
            print(f"JSON parse error: {e}")
            return None
