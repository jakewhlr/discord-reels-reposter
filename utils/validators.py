"""URL validation and extraction utilities."""

import logging
from typing import List, Tuple
import config

logger = logging.getLogger(__name__)


def is_instagram_url(url: str) -> bool:
    """
    Check if a URL is an Instagram Reel or post URL.
    
    Args:
        url: The URL to check
        
    Returns:
        True if the URL matches Instagram patterns, False otherwise
    """
    for pattern in config.INSTAGRAM_PATTERNS:
        if pattern.match(url):
            return True
    return False


def is_tiktok_url(url: str) -> bool:
    """
    Check if a URL is a TikTok video URL.
    
    Args:
        url: The URL to check
        
    Returns:
        True if the URL matches TikTok patterns, False otherwise
    """
    for pattern in config.TIKTOK_PATTERNS:
        if pattern.match(url):
            return True
    return False


def is_supported_url(url: str) -> Tuple[bool, str]:
    """
    Check if a URL is from a supported platform.
    
    Args:
        url: The URL to check
        
    Returns:
        Tuple of (is_supported, platform_name)
    """
    if is_instagram_url(url):
        return True, "Instagram"
    elif is_tiktok_url(url):
        return True, "TikTok"
    return False, ""


def extract_video_urls(message: str) -> List[Tuple[str, str]]:
    """
    Extract all supported video URLs from a message.
    
    Args:
        message: The message text to search
        
    Returns:
        List of tuples (url, platform_name) for all supported URLs found
    """
    urls = []
    words = message.split()
    
    for word in words:
        is_supported, platform = is_supported_url(word)
        if is_supported:
            urls.append((word, platform))
            logger.info(f"Detected {platform} URL: {word}")
    
    return urls


# Keep backward compatibility
def extract_instagram_urls(message: str) -> List[str]:
    """
    Extract all Instagram URLs from a message.
    
    Args:
        message: The message text to search
        
    Returns:
        List of Instagram URLs found in the message
    """
    urls = []
    words = message.split()
    
    for word in words:
        if is_instagram_url(word):
            urls.append(word)
            logger.info(f"Detected Instagram URL: {word}")
    
    return urls
