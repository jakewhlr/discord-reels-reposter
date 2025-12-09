"""Video compression utilities using ffmpeg."""

import logging
import os
import ffmpeg
from typing import Optional
import config

logger = logging.getLogger(__name__)


def compress_video(input_path: str, target_size_bytes: int, max_attempts: int = 3) -> Optional[str]:
    """
    Compress a video to fit within a target file size.
    
    This function uses an iterative approach, trying different compression levels
    until the video fits within the target size or max attempts is reached.
    
    Args:
        input_path: Path to the input video file
        target_size_bytes: Target file size in bytes
        max_attempts: Maximum number of compression attempts with different settings
        
    Returns:
        Path to the compressed video file, or None if compression failed
    """
    logger.info(f"Starting compression for {input_path} (target: {target_size_bytes / 1024 / 1024:.2f}MB)")
    
    # Create output path
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_compressed{ext}"
    
    # Get video duration and current size
    try:
        probe = ffmpeg.probe(input_path)
        duration = float(probe['format']['duration'])
        current_size = int(probe['format']['size'])
        
        logger.info(f"Original video: {current_size / 1024 / 1024:.2f}MB, duration: {duration:.2f}s")
        
    except Exception as e:
        logger.error(f"Failed to probe video: {str(e)}")
        return None
    
    # Calculate target bitrate (with safety margin)
    # Formula: (target_size_bytes * 8) / duration = bits per second
    # We use 90% of target to leave room for audio and container overhead
    safety_margin = 0.85
    target_bitrate = int((target_size_bytes * 8 * safety_margin) / duration)
    
    # Try different compression settings
    compression_levels = [
        {'video_bitrate': target_bitrate, 'crf': 28, 'preset': 'medium'},
        {'video_bitrate': int(target_bitrate * 0.8), 'crf': 32, 'preset': 'fast'},
        {'video_bitrate': int(target_bitrate * 0.6), 'crf': 35, 'preset': 'veryfast'},
    ]
    
    for attempt, settings in enumerate(compression_levels[:max_attempts], 1):
        logger.info(f"Compression attempt {attempt}/{max_attempts} with bitrate={settings['video_bitrate']/1000:.0f}kbps, crf={settings['crf']}")
        
        try:
            # Remove previous attempt if exists
            if os.path.exists(output_path):
                os.remove(output_path)
            
            # Compress video with ffmpeg
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(
                stream,
                output_path,
                video_bitrate=settings['video_bitrate'],
                vcodec='libx264',
                crf=settings['crf'],
                preset=settings['preset'],
                acodec='aac',
                audio_bitrate='96k',  # Reduce audio bitrate
                **{'movflags': 'faststart'}  # Optimize for streaming
            )
            
            # Run compression (overwrite output, suppress ffmpeg output)
            ffmpeg.run(stream, overwrite_output=True, quiet=True)
            
            # Check output file size
            if os.path.exists(output_path):
                output_size = os.path.getsize(output_path)
                logger.info(f"Compressed video size: {output_size / 1024 / 1024:.2f}MB")
                
                if output_size <= target_size_bytes:
                    logger.info(f"Compression successful on attempt {attempt}")
                    return output_path
                else:
                    logger.info(f"Still too large ({output_size / 1024 / 1024:.2f}MB > {target_size_bytes / 1024 / 1024:.2f}MB), trying more aggressive compression")
            
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error during compression attempt {attempt}: {e.stderr.decode() if e.stderr else str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during compression attempt {attempt}: {str(e)}")
    
    # If we exhausted all attempts, clean up and return None
    logger.warning(f"Failed to compress video to target size after {max_attempts} attempts")
    if os.path.exists(output_path):
        os.remove(output_path)
    
    return None


def get_video_info(filepath: str) -> Optional[dict]:
    """
    Get information about a video file.
    
    Args:
        filepath: Path to the video file
        
    Returns:
        Dictionary containing video information, or None if probe failed
    """
    try:
        probe = ffmpeg.probe(filepath)
        video_info = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        
        return {
            'duration': float(probe['format']['duration']),
            'size': int(probe['format']['size']),
            'bitrate': int(probe['format'].get('bit_rate', 0)),
            'width': int(video_info.get('width', 0)) if video_info else 0,
            'height': int(video_info.get('height', 0)) if video_info else 0,
        }
    except Exception as e:
        logger.error(f"Failed to get video info: {str(e)}")
        return None
