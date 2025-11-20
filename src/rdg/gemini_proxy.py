"""
Gemini Proxy Client for RDG

This module provides a client for calling Gemini API through the serverless
proxy instead of making direct API calls. This is useful for:

1. Centralizing API quota management
2. Enabling team-wide caching (future)
3. Monitoring usage across the team
4. Using a shared API key without exposing it in local .env files

Usage:
    from rdg.gemini_proxy import call_gemini_via_proxy

    result = call_gemini_via_proxy(
        prompt="Generate documentation for...",
        model="gemini-2.0-flash-exp"
    )
"""

import os
import requests
import subprocess
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Configuration
USE_PROXY = os.getenv('USE_GEMINI_PROXY', 'false').lower() == 'true'
PROXY_URL = os.getenv(
    'GEMINI_PROXY_URL',
    'https://us-central1-redthenblack-docs.cloudfunctions.net/geminiProxy'
)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')


class GeminiProxyError(Exception):
    """Custom exception for Gemini proxy errors"""
    pass


def get_gcloud_auth_token() -> Optional[str]:
    """
    Get GCP authentication token using gcloud CLI.

    Returns:
        The authentication token or None if gcloud is not available

    Raises:
        GeminiProxyError: If gcloud is not authenticated or available
    """
    try:
        result = subprocess.run(
            ['gcloud', 'auth', 'print-identity-token'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            raise GeminiProxyError(
                "gcloud authentication failed. Please run 'gcloud auth login' first."
            )
    except FileNotFoundError:
        raise GeminiProxyError(
            "gcloud CLI not found. Please install gcloud: "
            "https://cloud.google.com/sdk/docs/install"
        )
    except subprocess.TimeoutExpired:
        raise GeminiProxyError("gcloud command timed out")


def call_gemini_via_proxy(
    prompt: str,
    model: str = "gemini-2.0-flash-exp",
    max_tokens: int = 8192,
    api_key: Optional[str] = None,
    proxy_url: Optional[str] = None
) -> str:
    """
    Calls Gemini API through the serverless proxy.

    Args:
        prompt: The prompt to send to Gemini
        model: The model to use (default: gemini-2.0-flash-exp)
        max_tokens: Maximum tokens in response (default: 8192)
        api_key: API key (uses GEMINI_API_KEY env var if not provided)
        proxy_url: Proxy endpoint URL (uses GEMINI_PROXY_URL env var if not provided)

    Returns:
        The generated text response from Gemini

    Raises:
        GeminiProxyError: If the API call fails
        ValueError: If API key is not provided
    """
    # Use provided values or fall back to env vars
    if api_key is None:
        api_key = GEMINI_API_KEY

    if proxy_url is None:
        proxy_url = PROXY_URL

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable not set and no api_key provided. "
            "Please set GEMINI_API_KEY in your .env file."
        )

    if not proxy_url:
        raise ValueError(
            "GEMINI_PROXY_URL environment variable not set and no proxy_url provided."
        )

    # Get authentication token
    auth_token = get_gcloud_auth_token()

    # Build request
    payload = {
        'prompt': prompt,
        'apiKey': api_key,
        'model': model,
        'maxTokens': max_tokens
    }

    # Build headers with authentication
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {auth_token}'
    }

    try:
        # Make request to proxy
        response = requests.post(
            proxy_url,
            json=payload,
            headers=headers,
            timeout=120  # 2 minute timeout for long generations
        )

        # Check for HTTP errors
        response.raise_for_status()

        # Parse response
        data = response.json()

        if 'error' in data:
            raise GeminiProxyError(f"Proxy returned error: {data['error']}")

        return data['result']

    except requests.exceptions.Timeout:
        raise GeminiProxyError(
            f"Request to Gemini proxy timed out after 120 seconds. "
            f"Try reducing prompt size or max_tokens."
        )
    except requests.exceptions.ConnectionError:
        raise GeminiProxyError(
            f"Could not connect to Gemini proxy at {proxy_url}. "
            f"Check your internet connection and proxy URL."
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise GeminiProxyError("Invalid Gemini API key")
        elif e.response.status_code == 429:
            raise GeminiProxyError("API quota exceeded - too many requests")
        else:
            error_msg = e.response.json().get('error', str(e))
            raise GeminiProxyError(f"HTTP {e.response.status_code}: {error_msg}")
    except Exception as e:
        raise GeminiProxyError(f"Unexpected error calling Gemini proxy: {str(e)}")


def is_proxy_enabled() -> bool:
    """Check if proxy mode is enabled via environment variable"""
    return USE_PROXY


def get_proxy_url() -> Optional[str]:
    """Get the configured proxy URL"""
    return PROXY_URL if PROXY_URL else None
