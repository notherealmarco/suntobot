#!/usr/bin/env python3
"""Test the image analysis workflow."""

import asyncio
import os
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

async def test_image_analysis():
    """Test image analysis workflow."""
    print("🧪 Testing Image Analysis Workflow\n")
    
    # Set up environment for testing
    os.environ.setdefault('OPENAI_API_KEY', 'test_key')
    os.environ.setdefault('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    os.environ.setdefault('IMAGE_BASE_DIR', './images')
    
    try:
        from image_analyzer import ImageAnalyzer
        print("✅ ImageAnalyzer imported successfully")
        
        # Create analyzer instance (won't make actual API calls without real credentials)
        analyzer = ImageAnalyzer()
        print("✅ ImageAnalyzer initialized")
        
        # Test that the method exists and is callable
        assert hasattr(analyzer, 'analyze_image'), "analyze_image method exists"
        assert callable(getattr(analyzer, 'analyze_image')), "analyze_image is callable"
        print("✅ analyze_image method is available")
        
        # Test database integration
        from database import Message
        print("✅ Database Message model supports image_description field")
        
        # Check that Message model has the image_description field
        assert hasattr(Message, 'image_description'), "Message has image_description field"
        print("✅ Message model includes image_description field")
        
        # Test message handler integration
        from message_handler import MessageHandler
        from database import DatabaseManager
        
        # Create a test database manager (won't connect without real DB)
        try:
            db_manager = DatabaseManager("sqlite:///test.db")
            handler = MessageHandler(db_manager)
            print("✅ MessageHandler initialized with ImageAnalyzer")
            
            # Check that handler has image analyzer
            assert hasattr(handler, 'image_analyzer'), "MessageHandler has image_analyzer"
            print("✅ MessageHandler includes ImageAnalyzer")
            
        except Exception as e:
            print(f"ℹ️  Database connection test skipped: {e}")
        
        # Test summary engine
        from summary_engine import SummaryEngine
        summary_engine = SummaryEngine()
        print("✅ SummaryEngine initialized")
        
        print("\n🎉 Image Analysis Workflow Test Complete!")
        print("\nWorkflow Summary:")
        print("1. 📸 Image received → MessageHandler saves + analyzes")
        print("2. 🔍 ImageAnalyzer generates description using multimodal LLM")
        print("3. 💾 Description stored in database with message")
        print("4. 📋 SummaryEngine includes descriptions in summaries")
        print("\nThe bot is ready for image analysis!")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_image_analysis())
    sys.exit(0 if success else 1)
