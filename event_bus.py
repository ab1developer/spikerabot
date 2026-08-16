"""
Event Bus - Minimal pub/sub for service communication
"""

import asyncio
from typing import Callable, Dict, List
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Event:
    type: str
    data: dict
    timestamp: datetime = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now()

class EventBus:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._subscribers: Dict[str, List[Callable]] = {}
        self._initialized = True
    
    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to an event type"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable):
        """Unsubscribe from an event type"""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(handler)
    
    async def publish(self, event: Event):
        """Publish event to all subscribers"""
        if event.type in self._subscribers:
            tasks = []
            for handler in self._subscribers[event.type]:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(event))
                else:
                    handler(event)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    def publish_sync(self, event: Event):
        """Synchronous publish for non-async contexts"""
        if event.type in self._subscribers:
            for handler in self._subscribers[event.type]:
                try:
                    handler(event)
                except Exception as e:
                    print(f"Event handler error: {e}")

# Global instance
event_bus = EventBus()
