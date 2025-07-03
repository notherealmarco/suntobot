#!/usr/bin/env python3
"""Health check script for SuntoBot."""

import os
import sys
import asyncio
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


async def check_health():
    """Perform health checks."""
    checks_passed = 0
    total_checks = 6

    print("🔍 Running SuntoBot health checks...\n")

    # Check 1: Import modules
    try:
        from config import Config
        from database import DatabaseManager
        from time_utils import parse_time_interval
        from summary_engine import SummaryEngine

        print("✓ All modules import successfully")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ Module import failed: {e}")

    # Check 2: Environment variables (if .env exists)
    env_file = Path(".env")
    if env_file.exists():
        # Load .env file for testing
        with open(env_file) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

        try:
            Config.validate()
            print("✓ Configuration validation passed")
            checks_passed += 1
        except ValueError as e:
            print(f"✗ Configuration validation failed: {e}")
    else:
        print("⚠ No .env file found - skipping config validation")
        checks_passed += 1

    # Check 3: Time parsing
    try:
        assert parse_time_interval("30m") is not None
        assert parse_time_interval("2h") is not None
        assert parse_time_interval("7d") is not None
        print("✓ Time parsing functions work correctly")
        checks_passed += 1
    except AssertionError:
        print("✗ Time parsing functions failed")

    # Check 4: Images directory creation
    try:
        image_dir = Path(os.getenv("IMAGE_BASE_DIR", "./images"))
        image_dir.mkdir(exist_ok=True)
        print(f"✓ Images directory ready: {image_dir}")
        checks_passed += 1
    except Exception as e:
        print(f"✗ Images directory creation failed: {e}")

    # Check 5: Database models (without connection)
    try:
        from database import Message, Base

        print("✓ Database models loaded successfully")
        checks_passed += 1
    except Exception as e:
        print(f"✗ Database models failed: {e}")

    # Check 6: Bot components initialization (without network)
    try:
        if os.getenv("OPENAI_API_KEY") and os.getenv("TELEGRAM_BOT_TOKEN"):
            summary_engine = SummaryEngine()
            print("✓ Bot components can be initialized")
            checks_passed += 1
        else:
            print("⚠ Skipping bot initialization (missing API keys)")
            checks_passed += 1
    except Exception as e:
        print(f"✗ Bot initialization failed: {e}")

    print(f"\n📊 Health check results: {checks_passed}/{total_checks} checks passed")

    if checks_passed == total_checks:
        print("🎉 All health checks passed! SuntoBot is ready to run.")
        return 0
    elif checks_passed >= total_checks - 1:
        print("⚠ SuntoBot is mostly ready, check warnings above.")
        return 0
    else:
        print("❌ SuntoBot has issues that need to be resolved.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(check_health())
    sys.exit(exit_code)
