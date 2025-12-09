"""Video download utilities using yt-dlp."""

import logging
import os
import yt_dlp
from typing import Optional, Dict
import config

logger = logging.getLogger(__name__)


def download_video(url: str) -> Optional[Dict[str, any]]:
    """
    Download a video from the given URL using yt-dlp.
    
    Args:
        url: The URL of the video to download
        
    Returns:
        Dictionary containing:
            - 'filepath': Path to the downloaded file
            - 'filesize': Size of the file in bytes
            - 'title': Title of the video
        Returns None if download fails
    """
    logger.info(f"Downloading video from: {url}")
    
    try:
        # Ensure temp directory exists
        os.makedirs(config.TEMP_DIR, exist_ok=True)
        
        # Download the video
        with yt_dlp.YoutubeDL(config.YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Get the filepath
            filepath = ydl.prepare_filename(info)
            
            # Get file size
            filesize = os.path.getsize(filepath)
            
            # Get video title
            title = info.get('title', 'Unknown')
            
            logger.info(f"Download complete - Size: {filesize / 1024 / 1024:.2f}MB, Title: {title}")
            
            return {
                'filepath': filepath,
                'filesize': filesize,
                'title': title
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download failed for {url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading {url}: {str(e)}")
        return None


def cleanup_file(filepath: str) -> None:
    """
    Delete a file from the filesystem.
    
    Args:
        filepath: Path to the file to delete
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Cleaned up temporary file: {filepath}")
    except Exception as e:
        logger.warning(f"Failed to clean up file {filepath}: {str(e)}")
