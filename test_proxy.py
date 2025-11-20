#!/usr/bin/env python3
"""
Quick test script to verify Gemini proxy integration works.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rdg.gemini_proxy import call_gemini_via_proxy, is_proxy_enabled, GeminiProxyError

def test_proxy():
    """Test the proxy connection and authentication"""
    print("Testing Gemini Proxy Integration")
    print("-" * 50)

    # Check if proxy is enabled
    if not is_proxy_enabled():
        print("❌ Proxy mode is not enabled in .env file")
        print("   Set USE_GEMINI_PROXY=true to enable")
        return False

    print("✓ Proxy mode enabled")

    # Test with a simple prompt
    # Note: This will fail if GEMINI_API_KEY is not valid, but will
    # verify authentication works
    try:
        print("\nAttempting to call proxy with test prompt...")
        result = call_gemini_via_proxy(
            prompt="Say hello in one word",
            model="gemini-2.0-flash-exp",
            max_tokens=10
        )

        if result:
            print(f"✓ Proxy call successful!")
            print(f"  Response: {result}")
            return True
        else:
            print("❌ Proxy returned empty response")
            return False

    except GeminiProxyError as e:
        error_msg = str(e)

        # These are expected errors if API key is not set
        if "Invalid Gemini API key" in error_msg:
            print("⚠️  Proxy authentication works, but Gemini API key is invalid")
            print("   Update GEMINI_API_KEY in .env file with a real key to complete test")
            print("   (Authentication to proxy itself is working!)")
            return True  # Auth to proxy worked, just API key issue
        elif "gcloud" in error_msg:
            print(f"❌ gcloud authentication issue: {error_msg}")
            return False
        else:
            print(f"❌ Proxy error: {error_msg}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_proxy()
    sys.exit(0 if success else 1)
