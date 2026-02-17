"""
NKVD Arsenal - Tools for the Action arm of Stalin Bot
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from web_search import web_searcher
import re

class NKVDArsenal:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
    
    async def razvedka(self, query: str) -> str:
        """Internet reconnaissance using existing WebSearch"""
        loop = asyncio.get_event_loop()
        
        try:
            # Run blocking web search in executor
            results = await loop.run_in_executor(
                self.executor,
                lambda: web_searcher.search_and_analyze(query, [])
            )
            return results
        except Exception as e:
            return f"Разведка провалилась: {e}"
    
    async def gosplan_calc(self, expression: str) -> str:
        """Safe math calculator for Gosplan computations"""
        try:
            # Clean expression
            expression = expression.strip()
            
            # Only allow numbers, operators, parentheses, spaces
            if not re.match(r'^[\d\s\+\-\*\/\(\)\.\,]+$', expression):
                return "Недопустимое выражение"
            
            # Replace comma with dot for decimals
            expression = expression.replace(',', '.')
            
            # Safe eval with restricted namespace
            result = eval(expression, {"__builtins__": {}}, {})
            return f"Результат: {result}"
        except Exception as e:
            return f"Ошибка вычисления: {e}"
