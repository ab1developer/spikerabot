import json
import os
from datetime import datetime
from typing import Dict, List, Optional

class AcquaintancesDB:
    def __init__(self, db_path: str = "acquaintances.json"):
        self.db_path = db_path
        self.acquaintances = self._load_db()
    
    def _load_db(self) -> Dict:
        """Load acquaintances database from JSON file"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading acquaintances DB: {e}")
                return {"agents": {}, "interactions": []}
        return {"agents": {}, "interactions": []}
    
    def _save_db(self):
        """Save acquaintances database to JSON file"""
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.acquaintances, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving acquaintances DB: {e}")
    
    def add_agent(self, agent_id: str, agent_name: str, agent_role: str = "", 
                  platform: str = "moltbook", metadata: Dict = None):
        """Add or update agent in database"""
        if agent_id not in self.acquaintances["agents"]:
            self.acquaintances["agents"][agent_id] = {
                "name": agent_name,
                "role": agent_role,
                "platform": platform,
                "first_met": datetime.now().isoformat(),
                "last_interaction": datetime.now().isoformat(),
                "interaction_count": 0,
                "relationship_level": "acquaintance",  # acquaintance, colleague, ally, opponent
                "topics_discussed": [],
                "metadata": metadata or {}
            }
        else:
            self.acquaintances["agents"][agent_id]["last_interaction"] = datetime.now().isoformat()
        
        self._save_db()
    
    def record_interaction(self, agent_id: str, topic: str, sentiment: str = "neutral", 
                          summary: str = ""):
        """Record interaction with an agent"""
        if agent_id in self.acquaintances["agents"]:
            self.acquaintances["agents"][agent_id]["interaction_count"] += 1
            self.acquaintances["agents"][agent_id]["last_interaction"] = datetime.now().isoformat()
            
            if topic not in self.acquaintances["agents"][agent_id]["topics_discussed"]:
                self.acquaintances["agents"][agent_id]["topics_discussed"].append(topic)
        
        interaction = {
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "sentiment": sentiment,
            "summary": summary
        }
        self.acquaintances["interactions"].append(interaction)
        
        # Keep only last 1000 interactions
        if len(self.acquaintances["interactions"]) > 1000:
            self.acquaintances["interactions"] = self.acquaintances["interactions"][-1000:]
        
        self._save_db()
    
    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """Get agent information"""
        return self.acquaintances["agents"].get(agent_id)
    
    def get_all_agents(self) -> Dict:
        """Get all known agents"""
        return self.acquaintances["agents"]
    
    def get_agent_history(self, agent_id: str, limit: int = 10) -> List[Dict]:
        """Get interaction history with specific agent"""
        interactions = [
            i for i in self.acquaintances["interactions"] 
            if i["agent_id"] == agent_id
        ]
        return interactions[-limit:]
    
    def update_relationship(self, agent_id: str, level: str):
        """Update relationship level with agent"""
        if agent_id in self.acquaintances["agents"]:
            self.acquaintances["agents"][agent_id]["relationship_level"] = level
            self._save_db()
    
    def get_agents_by_topic(self, topic: str) -> List[str]:
        """Find agents who discussed specific topic"""
        agents = []
        for agent_id, data in self.acquaintances["agents"].items():
            if topic.lower() in [t.lower() for t in data["topics_discussed"]]:
                agents.append(agent_id)
        return agents
    
    def get_statistics(self) -> Dict:
        """Get database statistics"""
        return {
            "total_agents": len(self.acquaintances["agents"]),
            "total_interactions": len(self.acquaintances["interactions"]),
            "most_active_agent": max(
                self.acquaintances["agents"].items(),
                key=lambda x: x[1]["interaction_count"],
                default=(None, {"interaction_count": 0})
            )[0] if self.acquaintances["agents"] else None
        }
