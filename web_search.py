import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse
from config_loader import load_config
from debug_logger import debug_logger
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re
import numpy as np

class WebSearcher:
    def __init__(self):
        self.config = load_config()
        self.smart_search_enabled = self.config.smart_search_enabled
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        self.search_sources = self.config.search_sources
        self.semantic_ranking = self.config.semantic_ranking
        self.embedding_model = None
        self._embedding_load_attempted = False
        # TTL cache: {query: (timestamp, (results_text, links))}
        # Only successful results are cached; errors are never stored.
        self._search_cache: dict = {}
        self._cache_ttl: int = 300  # 5 minutes
    
    def _load_embedding_model(self):
        """Load embedding model for semantic ranking"""
        if self._embedding_load_attempted:
            return
        self._embedding_load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer(
                self.config.embedding_model,
                device=self.config.embedding_device,
            )
            debug_logger.log_info(f"Loaded embedding model for semantic ranking: {self.config.embedding_model}")
        except Exception as e:
            debug_logger.log_error(f"Failed to load embedding model: {e}", e)
            self.semantic_ranking = False
    
    def should_search_web(self, text: str) -> bool:
        """Legacy fast-path check kept for backwards compatibility.

        New code should use IntentRouter.classify() instead.
        Returns True if any configured trigger phrase is present.
        """
        if not self.config.web_search_enabled:
            return False
        return any(trigger in text.lower() for trigger in self.config.web_search_triggers)
    
    def _normalize_url(self, url: str) -> str:
        """Return a usable absolute HTTP(S) URL, or an empty string."""
        if not isinstance(url, str):
            return ""
        url = url.strip()
        if not url:
            return ""
        if url.startswith('//'):
            url = 'https:' + url
        elif not url.startswith(('http://', 'https://')):
            # Search-page navigation links such as /goggles are not results.
            if url.startswith(('/', '?', '#')):
                return ""
            url = 'https://' + url

        parsed = urlparse(url)
        return url if parsed.scheme in ('http', 'https') and parsed.netloc else ""
    
    def extract_page_content(self, url: str, max_chars: int = 1000) -> str:
        """Extract text content from webpage"""
        try:
            url = self._normalize_url(url)
            if not url:
                return ""
            response = requests.get(url, headers=self.headers, timeout=5)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove scripts, styles, nav, footer
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            return text[:max_chars] if text else ""
        except Exception as e:
            debug_logger.log_error(f"Content extraction error for {url}: {e}", e)
            return ""
    
    def extract_multiple_contents(self, urls: list, max_chars: int = 1000) -> dict:
        """Extract content from multiple URLs in parallel"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.config.parallel_extraction_workers) as executor:
            future_to_url = {executor.submit(self.extract_page_content, url, max_chars): url for url in urls}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    content = future.result()
                    results[url] = content
                except Exception as e:
                    debug_logger.log_error(f"Parallel extraction error for {url}: {e}", e)
                    results[url] = ""
        
        return results
    
    def cosine_similarity(self, vec1, vec2):
        """Calculate cosine similarity between two vectors"""
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    
    def calculate_semantic_score(self, title: str, snippet: str, query: str) -> float:
        """Calculate semantic similarity score using embeddings"""
        if self.semantic_ranking and self.embedding_model is None:
            self._load_embedding_model()
        if not self.semantic_ranking or self.embedding_model is None:
            return 0.0
        
        try:
            # Combine title and snippet for better context
            result_text = f"{title} {snippet}" if snippet else title
            
            # Get embeddings
            query_embedding = self.embedding_model.encode(query, convert_to_numpy=True)
            result_embedding = self.embedding_model.encode(result_text, convert_to_numpy=True)
            
            # Calculate cosine similarity (returns value between -1 and 1)
            similarity = self.cosine_similarity(query_embedding, result_embedding)
            
            # Convert to 0-100 scale
            return (similarity + 1) * 50
        except Exception as e:
            debug_logger.log_error(f"Semantic scoring error: {e}", e)
            return 0.0
    
    def calculate_relevance_score(self, title: str, snippet: str, url: str, query: str) -> float:
        """Calculate relevance score for search result"""
        if self.semantic_ranking and self.embedding_model is None:
            self._load_embedding_model()
        if self.semantic_ranking and self.embedding_model is not None:
            # Semantic ranking mode (70% semantic + 30% other factors)
            semantic_score = self.calculate_semantic_score(title, snippet, query)
            
            # Domain authority (20% weight)
            domain_score = 0.0
            trusted_domains = ['wikipedia.org', 'gov', 'edu', 'reuters.com', 'bbc.com']
            for domain in trusted_domains:
                if domain in url:
                    domain_score = 20.0
                    break
            
            # Recency bonus (10% weight)
            recency_score = 0.0
            current_year = datetime.now().year
            if str(current_year) in title or (snippet and str(current_year) in snippet):
                recency_score = 10.0
            
            # Combine: 70% semantic + 20% domain + 10% recency
            return (semantic_score * 0.7) + domain_score + recency_score
        else:
            # Keyword-based ranking (fallback)
            score = 0.0
            query_lower = query.lower()
            query_words = set(query_lower.split())
            if not query_words:
                return 0.0
            
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
    
    def _search_duckduckgo(self, query: str) -> list:
        """Search using the ddgs library (API-based, not HTML scraping)."""
        try:
            from ddgs import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=self.config.web_search_max_results * 2):
                    title = str(r.get('title') or '').strip()
                    url = self._normalize_url(str(r.get('href') or ''))
                    if not title or not url:
                        continue
                    results.append({
                        'title': title,
                        'url': url,
                        'snippet': r.get('body', ''),
                        'source': 'DuckDuckGo',
                    })
            return results
        except Exception as e:
            debug_logger.log_error(f"DuckDuckGo search error: {e}", e)
            return []
    
    def _search_brave(self, query: str) -> list:
        """Search using Brave Search (HTML scraping)"""
        try:
            search_url = f"https://search.brave.com/search?q={quote_plus(query)}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            results = []
            # Brave uses different HTML structure
            result_divs = soup.find_all('div', class_='snippet')[:self.config.web_search_max_results * 2]
            
            for div in result_divs:
                title_elem = div.find('a', class_='result-header')
                if not title_elem:
                    title_elem = div.find_previous('a')
                
                if title_elem:
                    title = title_elem.get_text().strip()
                    url = self._normalize_url(title_elem.get('href', ''))
                    snippet_elem = div.find('p', class_='snippet-description')
                    snippet = snippet_elem.get_text().strip() if snippet_elem else ''
                    
                    if title and url:
                        results.append({'title': title, 'url': url, 'snippet': snippet, 'source': 'Brave'})
            
            return results
        except Exception as e:
            debug_logger.log_error(f"Brave search error: {e}", e)
            return []
    
    def _search_google(self, query: str) -> list:
        """Search using Google (HTML scraping)"""
        try:
            search_url = f"https://www.google.com/search?q={quote_plus(query)}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            results = []
            # Google search results
            result_divs = soup.find_all('div', class_='g')[:self.config.web_search_max_results * 2]
            
            for div in result_divs:
                title_elem = div.find('h3')
                link_elem = div.find('a')
                snippet_elem = div.find('div', class_='VwiC3b')
                
                if title_elem and link_elem:
                    title = title_elem.get_text().strip()
                    url = self._normalize_url(link_elem.get('href', ''))
                    snippet = snippet_elem.get_text().strip() if snippet_elem else ''
                    
                    if title and url:
                        results.append({'title': title, 'url': url, 'snippet': snippet, 'source': 'Google'})
            
            return results
        except Exception as e:
            debug_logger.log_error(f"Google search error: {e}", e)
            return []
    
    def _multi_source_search(self, query: str) -> list:
        """Search across multiple sources with fallback"""
        all_results = []
        
        for source_config in self.search_sources:
            source_name = source_config['name'].lower()
            
            debug_logger.log_info(f"Trying search source: {source_name}")
            
            if source_name == 'duckduckgo':
                results = self._search_duckduckgo(query)
            elif source_name == 'brave':
                results = self._search_brave(query)
            elif source_name == 'google':
                results = self._search_google(query)
            else:
                debug_logger.log_info(f"Unknown search source: {source_name}")
                continue
            
            if results:
                all_results.extend(results)
                debug_logger.log_info(f"{source_name} returned {len(results)} results")
                # If we have enough results, stop trying other sources
                if len(all_results) >= self.config.web_search_max_results * 2:
                    break
            else:
                debug_logger.log_info(f"{source_name} returned no results, trying next source")
        
        # Keep provider priority while removing duplicate and invalid URLs.
        unique_results = []
        seen_urls = set()
        for result in all_results:
            url = self._normalize_url(result.get('url', ''))
            if not url or url in seen_urls:
                continue
            result['url'] = url
            seen_urls.add(url)
            unique_results.append(result)
        return unique_results
    

    def _perform_search(self, query: str) -> tuple:
        """Perform multi-source web search and return results with links"""
        try:
            query = ' '.join((query or '').split())
            if not query:
                return "🔍 Пустой поисковый запрос", []
            raw_results = self._multi_source_search(query)
            
            if not raw_results:
                return "🔍 Поиск не дал результатов", []
            
            ranked = self.rank_results(raw_results, query)[:self.config.web_search_max_results]
            
            results = []
            links = []
            for r in ranked:
                text = f"• {r['title']}"
                if r['snippet']:
                    text += f"\n  {r['snippet'][:150]}..."
                text += f" [{r.get('source', 'Web')}] [Рел: {r['score']:.0f}%]"
                results.append(text)
                links.append(r['url'])
            
            search_text = f"🔍 Результаты (мульти-источник):\n\n" + "\n\n".join(results)
            return search_text, links
                
        except Exception as e:
            debug_logger.log_error(f"Web search error: {e}", e)
            return "🔍 Ошибка поиска в интернете", []
    
    def search(self, query: str) -> tuple:
        """Perform web search with TTL caching (5 minutes, successful results only).

        Replaces the old @lru_cache approach which:
        - included `self` in the cache key (leaking the instance)
        - cached error/empty strings, silencing search for the full TTL window

        Only results containing at least one URL are cached; empty/error
        results are discarded so the next call retries immediately.
        """
        now = time.time()
        query = ' '.join((query or '').split())
        cache_key = query.casefold()
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            cached_at, payload = cached
            if now - cached_at < self._cache_ttl:
                debug_logger.log_info(f"WebSearcher: cache hit for query={query!r}")
                return payload

        result = self._perform_search(query)

        results_text, links = result
        if links:  # only cache real results
            self._search_cache[cache_key] = (now, result)

        return result
    
    def search_and_analyze(self, query: str, conversation_history) -> str:
        """Perform web search and return a formatted LLM-synthesised response string.

        This is the primary entry point called by main.py / the intent router.
        It returns a plain string ready to send to the user.
        """
        try:
            search_results, links = self.search(query)

            # Do not ask the persona model to explain an empty lookup: doing so
            # produced long hallucinated replies followed by the same failure
            # line twice. Return one clear diagnostic and let a later call retry.
            if not links:
                return search_results

            import model

            enhanced_query = f"{query}\n\nКонтекст из интернета:\n{search_results}"
            response = model.modelResponse(enhanced_query, conversation_history)

            final_response = f"{response}\n\n{search_results}"
            if links:
                final_response += "\n\n🔗 Ссылки:\n" + "\n".join(links)

            return final_response

        except Exception as e:
            debug_logger.log_error(f"Web search and analysis error: {e}", e)
            # Fallback: return raw search results without LLM synthesis
            search_results, links = self.search(query)
            result = search_results
            if links:
                result += "\n\n🔗 Ссылки:\n" + "\n".join(links)
            return result

    def smart_search_and_compact(self, query: str) -> str:
        """Perform smart search with ranking, parallel content extraction and compact results"""
        try:
            raw_results = self._multi_source_search(query)
            
            if not raw_results:
                return ""
            
            ranked = self.rank_results(raw_results, query)[:self.config.smart_search_links]
            
            results = []
            for r in ranked:
                results.append(f"• {r['title']}")
                if r['snippet']:
                    results.append(f"  {r['snippet'][:200]}")
            
            # Extract content from top 3 ranked results in parallel
            if ranked:
                top_urls = [r['url'] for r in ranked[:3]]
                contents = self.extract_multiple_contents(top_urls, max_chars=800)
                
                # Use content from most relevant result that has content
                for url in top_urls:
                    content = contents.get(url, '')
                    if content:
                        results.append(f"\nСодержание наиболее релевантной страницы: {content}")
                        break
            
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
