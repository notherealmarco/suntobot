#!/usr/bin/env python3
"""Setup script for SuntoBot."""

import os
import sys
import subprocess
import shutil


def check_python_version():
    """Check if Python version is adequate."""
    if sys.version_info < (3, 9):
        print("Error: Python 3.9 or higher is required")
        sys.exit(1)
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} detected")


def check_uv():
    """Check if uv is installed."""
    if not shutil.which("uv"):
        print("Error: uv is not installed. Please install it first:")
        print("  curl -LsSf https://astral.sh/uv/install.sh | sh")
        sys.exit(1)
    print("✓ uv found")


def install_dependencies():
    """Install project dependencies."""
    print("Installing dependencies...")
    try:
        subprocess.run(["uv", "sync"], check=True)
        print("✓ Dependencies installed")
    except subprocess.CalledProcessError:
        print("Error: Failed to install dependencies")
        sys.exit(1)


def create_env_file():
    """Create .env file from template if it doesn't exist."""
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            shutil.copy(".env.example", ".env")
            print("✓ Created .env file from template")
            print("  Please edit .env with your configuration")
        else:
            print("Warning: .env.example not found")
    else:
        print("✓ .env file already exists")


def create_images_dir():
    """Create images directory."""
    os.makedirs("images", exist_ok=True)
    print("✓ Images directory created")


def run_tests():
    """Run basic tests."""
    print("Running tests...")
    try:
        subprocess.run(
            ["uv", "run", "python", "-m", "pytest", "test_bot.py", "-v"], check=True
        )
        print("✓ Tests passed")
    except subprocess.CalledProcessError:
        print("Warning: Some tests failed")


def main():
    """Main setup function."""
    print("Setting up SuntoBot...")

    check_python_version()
    check_uv()
    install_dependencies()
    create_env_file()
    create_images_dir()
    run_tests()

    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Edit .env with your configuration")
    print("2. Set up PostgreSQL database")
    print("3. Run the bot: uv run python main.py")


if __name__ == "__main__":
    main()
