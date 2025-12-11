"""Configuration constants for the Discord video bot."""

import os
import re
import logging

# File size limit (8MB for non-boosted servers)
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB in bytes

# Temporary download directory
TEMP_DIR = "./temp_downloads"

# Supported platforms
SUPPORTED_PLATFORMS = ["instagram", "tiktok", "youtube"]

# Instagram URL patterns
INSTAGRAM_PATTERNS = [
    re.compile(r'https?://(?:www\.)?instagram\.com/reel/([A-Za-z0-9_-]+)/?.*'),
    re.compile(r'https?://(?:www\.)?instagram\.com/p/([A-Za-z0-9_-]+)/?.*'),
]

# TikTok URL patterns
TIKTOK_PATTERNS = [
    re.compile(r'https?://(?:www\.)?tiktok\.com/@[^/]+/video/(\d+)/?.*'),
    re.compile(r'https?://(?:vm\.)?tiktok\.com/([A-Za-z0-9]+)/?.*'),  # Short links
    re.compile(r'https?://(?:www\.)?tiktok\.com/t/([A-Za-z0-9]+)/?.*'),  # Another short link format
]

# YouTube Shorts URL patterns
YOUTUBE_PATTERNS = [
    re.compile(r'https?://(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]+)/?.*'),
    re.compile(r'https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]+)/?.*'),  # Short links that might be Shorts
]

# yt-dlp download options for medium quality
YTDL_OPTIONS = {
    'format': 'best[height<=720][ext=mp4]/best[ext=mp4]/best',  # Medium quality, prefer MP4
    'outtmpl': os.path.join(TEMP_DIR, '%(id)s.%(ext)s'),  # Save with video ID
    'quiet': True,  # Suppress yt-dlp output
    'no_warnings': True,
    'noplaylist': True,  # Don't download playlists
}

# Video compression settings
ENABLE_COMPRESSION = True  # Automatically compress videos that exceed MAX_FILE_SIZE
MAX_COMPRESSION_ATTEMPTS = 3  # Number of compression attempts with different settings

# Logging configuration
LOGGING_LEVEL = logging.INFO
LOGGING_FORMAT = '[%(asctime)s] %(levelname)s: %(message)s'
LOGGING_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
