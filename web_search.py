import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from config_loader import load_config
from debug_logger import debug_logger
from functools import lru_cache
from datetime import datetime
import time
import re

class WebSearcher:
    def __init__(self):
        self.config = load_config()
        self.smart_search_enabled = self.config.smart_search_enabled
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    def should_search_web(self, text: str) -> bool:
        """Check if message requests web search"""
        if not self.config.web_search_enabled:
            return False
        return any(trigger in text.lower() for trigger in self.config.web_search_triggers)
    
    def extract_page_content(self, url: str, max_chars: int = 1000) -> str:
        """Extract text content from webpage"""
        try:
            response = requests.get(url, headers=self.headers, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove scripts, styles, nav, footer
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            return text[:max_chars] if text else ""
        except Exception as e:
            debug_logger.log_error(f"Content extraction error for {url}: {e}", e)
            return ""
    
    def calculate_relevance_score(self, title: str, snippet: str, url: str, query: str) -> float:
        """Calculate relevance score for search result"""
        score = 0.0
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        # Title relevance (40% weight)
        title_lower = title.lower()
        title_words = set(title_lower.split())
        title_matches = len(query_words & title_words)
        if title_matches > 0:
            score += (title_matches / len(query_words)) * 40
        
        # Snippet relevance (30% weight)
        if snippet:
            snippet_lower = snippet.lower()
            snippet_words = set(snippet_lower.split())
            snippet_matches = len(query_words & snippet_words)
            if snippet_matches > 0:
                score += (snippet_matches / len(query_words)) * 30
        
        # Domain authority (20% weight)
        trusted_domains = ['wikipedia.org', 'gov', 'edu', 'reuters.com', 'bbc.com']
        for domain in trusted_domains:
            if domain in url:
                score += 20
                break
        
        # Recency bonus (10% weight)
        current_year = datetime.now().year
        if str(current_year) in title or (snippet and str(current_year) in snippet):
            score += 10
        
        return score
    
    def rank_results(self, results: list, query: str) -> list:
        """Rank search results by relevance score"""
        for result in results:
            result['score'] = self.calculate_relevance_score(
                result['title'], result.get('snippet', ''), result['url'], query
            )
        results.sort(key=lambda x: x['score'], reverse=True)
        return results
    
    def extract_snippet(self, result_element) -> str:
        """Extract snippet/description from search result"""
        try:
            snippet = result_element.find_parent().find('a', class_='result__snippet')
            if not snippet:
                snippet = result_element.find_next('div', class_='result__snippet')
            return snippet.get_text().strip() if snippet else ""
        except:
            return ""
    
    @lru_cache(maxsize=50)
    def cached_search(self, query: str, timestamp: int) -> tuple:
        """Cached search with 5-minute intervals"""
        return self._perform_search(query)
    
    def _perform_search(self, query: str) -> tuple:
        """Perform web search and return results with links"""
        try:
            search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            raw_results = []
            result_elements = soup.find_all('a', class_='result__a')[:self.config.web_search_max_results * 2]
            
            for elem in result_elements:
                title = elem.get_text().strip()
                url = elem.get('href', '')
                snippet = self.extract_snippet(elem)
                if title and url:
                    raw_results.append({'title': title, 'url': url, 'snippet': snippet})
            
            if not raw_results:
                return "🔍 Поиск не дал результатов", []
            
            ranked = self.rank_results(raw_results, query)[:self.config.web_search_max_results]
            
            results = []
            links = []
            for r in ranked:
                text = f"• {r['title']}"
                if r['snippet']:
                    text += f"\n  {r['snippet'][:150]}..."
                text += f" [Рел: {r['score']:.0f}%]"
                results.append(text)
                links.append(r['url'])
            
            search_text = f"🔍 Результаты (отсортировано):\n\n" + "\n\n".join(results)
            return search_text, links
                
        except Exception as e:
            debug_logger.log_error(f"Web search error: {e}", e)
            return "🔍 Ошибка поиска в интернете", []
    
    def search(self, query: str) -> tuple:
        """Perform web search with caching"""
        # Round timestamp to 5-minute intervals for caching
        timestamp = int(time.time() // 300)
        return self.cached_search(query, timestamp)
    
    def search_and_analyze(self, query: str, conversation_history) -> tuple:
        """Perform web search and generate LLM response with search context"""
        try:
            search_results, links = self.search(query)
            
            # Import here to avoid circular imports
            import model
            
            # Create enhanced prompt with search results
            enhanced_query = f"{query}\n\nКонтекст из интернета:\n{search_results}"
            
            # Generate response using LLM with search context
            response = model.modelResponse(enhanced_query, conversation_history)
            
            # Format final response with links
            final_response = f"{response}\n\n{search_results}"
            if links:
                final_response += "\n\n🔗 Ссылки:\n" + "\n".join(links)
            
            return final_response, links
            
        except Exception as e:
            debug_logger.log_error(f"Web search and analysis error: {e}", e)
            search_results, links = self.search(query)  # Fallback to simple search
            return search_results, links
    
    def should_auto_search(self, message: str) -> tuple:
        """Determine if message needs web search and generate search query"""
        if not self.smart_search_enabled or not self.config.web_search_enabled:
            return False, None
        
        try:
            import model
            
            # Ask LLM to classify and generate search query
            classifier_prompt = f"""Analyze this message and determine if it needs current information from the internet.

Message: "{message}"

Respond ONLY with JSON format:
{{"needs_search": true/false, "search_query": "optimized search query" or null}}

Needs search if message asks about:
- Current events, news, recent happenings
- Facts that may have changed
- Real-time information (weather, prices, etc.)
- Specific recent dates or times
- "What's happening", "latest", "current", "now", "today"

Does NOT need search for:
- Greetings, thanks, casual chat
- Historical facts (before 2023)
- Personal opinions
- General knowledge questions
- Philosophical discussions"""
            
            response = model.modelResponse(classifier_prompt, [])
            
            # Parse JSON response
            import json
            import re
            
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                result = json.loads(json_match.group())
                needs_search = result.get('needs_search', False)
                search_query = result.get('search_query')
                
                debug_logger.log_info(f"Auto-search decision: needs_search={needs_search}, query={search_query}")
                return needs_search, search_query
            
            return False, None
            
        except Exception as e:
            debug_logger.log_error(f"Auto-search classification error: {e}", e)
            return False, None
    
    def smart_search_and_compact(self, query: str) -> str:
        """Perform smart search with ranking, content extraction and compact results"""
        try:
            search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            raw_results = []
            result_elements = soup.find_all('a', class_='result__a')[:self.config.smart_search_links * 2]
            
            for elem in result_elements:
                title = elem.get_text().strip()
                url = elem.get('href', '')
                snippet = self.extract_snippet(elem)
                if title and url:
                    raw_results.append({'title': title, 'url': url, 'snippet': snippet})
            
            if not raw_results:
                return ""
            
            ranked = self.rank_results(raw_results, query)[:self.config.smart_search_links]
            
            results = []
            for r in ranked:
                results.append(f"• {r['title']}")
                if r['snippet']:
                    results.append(f"  {r['snippet'][:200]}")
            
            # Extract content from top ranked result
            if ranked:
                content = self.extract_page_content(ranked[0]['url'], max_chars=800)
                if content:
                    results.append(f"\nСодержание наиболее релевантной страницы: {content}")
            
            import model
            search_text = "\n".join(results)
            compact_prompt = f"""Кратко суммируй ключевую информацию (2-3 предложения):

{search_text}

Краткое резюме:"""
            
            summary = model.modelResponse(compact_prompt, [])
            return f"[Информация из интернета: {summary.strip()}]"
            
        except Exception as e:
            debug_logger.log_error(f"Smart search compact error: {e}", e)
            return ""

web_searcher = WebSearcher()