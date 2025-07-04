#!/usr/bin/env python3
"""
Script to run Alembic migrations with environment variables
This handles reading DATABASE_URL from .env or environment
"""

import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print(
            "  python run_migration.py revision --autogenerate -m 'migration message'"
        )
        print("  python run_migration.py upgrade head")
        print("  python run_migration.py downgrade -1")
        print("  python run_migration.py current")
        print("  python run_migration.py history")
        sys.exit(1)

    # Ensure DATABASE_URL is set
    if not os.getenv("DATABASE_URL"):
        print("Warning: DATABASE_URL environment variable not set!")
        print("Please set it in your .env file or environment")
        print("Example: DATABASE_URL=postgresql://user:password@localhost/dbname")
        sys.exit(1)

    # Run alembic command
    import subprocess

    cmd = ["uv", "run", "alembic"] + sys.argv[1:]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
