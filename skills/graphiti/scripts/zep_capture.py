#!/usr/bin/env python3
"""
Zep Cloud integration for Graphiti auto-extraction.
Captures entities, relationships, and context from conversations.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path

# Try to import zep_cloud, fall back to offline mode if not available
try:
    from zep_cloud.client import AsyncZep
    from zep_cloud import Message
    ZEP_AVAILABLE = True
except ImportError:
    ZEP_AVAILABLE = False

WORKSPACE = Path("/root/claudeclaw-project/workspace")
GRAPH_PATH = WORKSPACE / "memory/ontology/graph.jsonl"
SESSIONS_PATH = WORKSPACE / "memory/context/sessions"

def get_api_key():
    """Load Zep API key from .env or environment."""
    env_path = WORKSPACE / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("ZEP_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("ZEP_API_KEY")

def generate_id(prefix: str) -> str:
    """Generate a unique ID."""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def load_graph():
    """Load existing entities and relations."""
    entities = {}
    relations = []

    if not GRAPH_PATH.exists():
        return entities, relations

    with open(GRAPH_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("op") == "create":
                entity = record.get("entity", {})
                entities[entity.get("id")] = entity
            elif record.get("op") == "relate":
                relations.append(record)

    return entities, relations

def save_entity(entity_type: str, properties: dict, source: str = "zep-auto") -> dict:
    """Save an entity to the graph."""
    entities, _ = load_graph()

    entity_id = generate_id(entity_type[:4].lower())
    timestamp = datetime.now(timezone.utc).isoformat()

    entity = {
        "id": entity_id,
        "type": entity_type,
        "properties": properties,
        "created": timestamp,
        "updated": timestamp,
        "source": source
    }

    with open(GRAPH_PATH, "a") as f:
        json.dump({"op": "create", "entity": entity, "timestamp": timestamp}, f)
        f.write("\n")

    return entity

def save_relation(from_id: str, rel_type: str, to_id: str, properties: dict = None):
    """Save a relationship to the graph."""
    timestamp = datetime.now(timezone.utc).isoformat()

    with open(GRAPH_PATH, "a") as f:
        json.dump({
            "op": "relate",
            "from": from_id,
            "rel": rel_type,
            "to": to_id,
            "properties": properties or {},
            "timestamp": timestamp
        }, f)
        f.write("\n")

async def capture_session(session_id: str, messages: list, user_id: str = "jatin"):
    """
    Capture a conversation session to Zep.

    Args:
        session_id: Unique session identifier
        messages: List of {"role": "user"|"assistant", "content": "..."} dicts
        user_id: User identifier (default: "jatin")
    """
    if not ZEP_AVAILABLE:
        print("Zep Cloud not available - using offline capture only")
        return None

    api_key = get_api_key()
    if not api_key:
        print("No Zep API key found")
        return None

    zep = AsyncZep(api_key=api_key)

    try:
        # Create or get user
        user = await zep.user.add(
            user_id=user_id,
            first_name="Jatin",
            metadata={"workspace": "ai-persona-os"}
        )

        # Create session
        session = await zep.memory.add_session(
            session_id=session_id,
            user_id=user_id,
            metadata={"source": "claude-code"}
        )

        # Add messages
        zep_messages = [
            Message(role=msg["role"], content=msg["content"])
            for msg in messages
        ]
        await zep.memory.add_memory(session_id=session_id, messages=zep_messages)

        # Get extracted facts and entities
        memory = await zep.memory.get_memory(session_id=session_id)

        # Extract entities from facts
        for fact in memory.facts:
            # Auto-detect entity type from fact content
            entity = save_entity("Note", {
                "content": fact.content,
                "category": fact.category if hasattr(fact, 'category') else "general"
            }, source="zep-auto")

        return {
            "session_id": session_id,
            "facts_extracted": len(memory.facts),
            "entities_created": len(memory.facts)
        }

    except Exception as e:
        print(f"Zep error: {e}")
        return None
    finally:
        await zep.close()

def extract_entities_from_text(text: str) -> list:
    """
    Simple entity extraction when Zep is unavailable.
    Looks for patterns like "Person: X", "Company: Y", etc.
    """
    entities = []

    # Simple pattern matching for common entity types
    patterns = {
        "Person": [r"(?:I am|my name is|called)\s+([A-Z][a-z]+)"],
        "Organization": [r"(?:company|business|organization|at)\s+([A-Z][A-Za-z\s]+)"],
        "Project": [r"(?:project|working on|building)\s+([A-Z][A-Za-z\s]+)"],
    }

    import re
    for entity_type, regexes in patterns.items():
        for regex in regexes:
            matches = re.findall(regex, text, re.IGNORECASE)
            for match in matches:
                entities.append({
                    "type": entity_type,
                    "name": match.strip()
                })

    return entities

if __name__ == "__main__":
    # Test the connection
    api_key = get_api_key()
    if api_key:
        print(f"✓ Zep API key found (starts with: {api_key[:20]}...)")
    else:
        print("✗ No Zep API key found")

    print(f"Graph path: {GRAPH_PATH}")
    print(f"Zep available: {ZEP_AVAILABLE}")
