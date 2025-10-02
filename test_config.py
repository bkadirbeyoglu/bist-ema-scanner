# test_config.py - Quick test that .env works
"""
Quick test to verify environment configuration is working.
Run this before proceeding with the session.
"""

from dotenv import load_dotenv
import os

def test_config():
    """Test that .env file loads correctly."""
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Try to get API key
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    
    if not api_key:
        print("❌ ERROR: ALPHA_VANTAGE_API_KEY not found!")
        print("📝 Steps to fix:")
        print("   1. Make sure .env file exists")
        print("   2. Add line: ALPHA_VANTAGE_API_KEY=your_actual_key")
        print("   3. Replace 'your_actual_key' with real key from Alpha Vantage")
        return False
    
    if api_key == "your_key_here" or api_key == "your_actual_key_here":
        print("⚠️  WARNING: Using placeholder API key!")
        print("📝 Replace with real key from: https://www.alphavantage.co/support/#api-key")
        return False
    
    print(f"✅ Configuration loaded successfully!")
    print(f"📊 API Key: {api_key[:8]}... (hidden for security)")
    print(f"🌍 Environment: {os.getenv('ENVIRONMENT', 'not set')}")
    return True

if __name__ == "__main__":
    success = test_config()
    exit(0 if success else 1)