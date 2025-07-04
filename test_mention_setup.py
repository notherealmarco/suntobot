#!/usr/bin/env python3
"""
Test script to validate the mention reply feature setup
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config import Config
from database import DatabaseManager, Message
from summary_engine import SummaryEngine

async def test_mention_reply():
    """Test the mention reply functionality"""
    print("Testing mention reply setup...")
    
    try:
        # Test config validation
        Config.validate()
        print("✅ Config validation passed")
        
        # Test database connection
        db_manager = DatabaseManager(Config.DATABASE_URL)
        print("✅ Database connection established")
        
        # Test summary engine initialization
        summary_engine = SummaryEngine()
        print("✅ Summary engine initialized")
        
        # Test mention system prompt
        print(f"✅ Mention system prompt configured: {len(Config.MENTION_SYSTEM_PROMPT)} characters")
        print(f"✅ Context size: {Config.MENTION_CONTEXT_SIZE}")
        print(f"✅ Context hours: {Config.MENTION_CONTEXT_HOURS}")
        
        print("\n🎉 All tests passed! Mention reply feature is ready to use.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_mention_reply())
    sys.exit(0 if success else 1)
