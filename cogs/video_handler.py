"""Discord cog for handling video URL messages."""

import logging
import os
import discord
from discord.ext import commands
from utils.validators import extract_video_urls
from utils.downloader import download_video, cleanup_file
from utils.compressor import compress_video
import config

logger = logging.getLogger(__name__)


class VideoHandler(commands.Cog):
    """Cog that listens for video URLs and re-embeds them."""
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("VideoHandler cog initialized")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listen for messages containing video URLs (Instagram, TikTok, etc.).
        
        Args:
            message: The Discord message object
        """
        # Ignore bot's own messages to prevent loops
        if message.author == self.bot.user:
            return
        
        # Only process messages in guild (server) channels, not DMs
        if not message.guild:
            return
        
        # Extract all supported video URLs from the message
        urls = extract_video_urls(message.content)
        
        # If no supported URLs found, ignore the message
        if not urls:
            return
        
        logger.info(f"Processing {len(urls)} video URL(s) from message in {message.guild.name}")
        
        # Process each URL
        for url, platform in urls:
            await self.process_video_url(message, url, platform)
    
    async def process_video_url(self, message: discord.Message, url: str, platform: str = "Unknown"):
        """
        Download and re-embed a video from a URL.
        
        Args:
            message: The original Discord message
            url: The video URL to process
            platform: The platform name (Instagram, TikTok, etc.)
        """
        # Add "downloading" reaction
        try:
            await message.add_reaction("⏬")
        except discord.errors.Forbidden:
            logger.warning("Missing permission to add reactions")
        
        # Download the video
        video_info = download_video(url)
        
        # If download failed
        if video_info is None:
            await self.handle_download_error(message, url, platform)
            return
        
        filepath = video_info['filepath']
        filesize = video_info['filesize']
        title = video_info['title']
        
        # Check file size and compress if needed
        if filesize > config.MAX_FILE_SIZE:
            if config.ENABLE_COMPRESSION:
                logger.info(f"Video exceeds size limit ({filesize / 1024 / 1024:.2f}MB), attempting compression...")
                
                # Update reaction to show compression is happening
                try:
                    await message.add_reaction("🔄")
                except discord.errors.Forbidden:
                    pass
                
                # Attempt to compress the video
                compressed_path = compress_video(filepath, config.MAX_FILE_SIZE, config.MAX_COMPRESSION_ATTEMPTS)
                
                if compressed_path:
                    # Compression successful, use compressed file
                    cleanup_file(filepath)  # Remove original
                    filepath = compressed_path
                    filesize = os.path.getsize(filepath)
                    logger.info(f"Compression successful! New size: {filesize / 1024 / 1024:.2f}MB")
                else:
                    # Compression failed
                    logger.warning("Compression failed, video still too large")
                    await self.handle_compression_failed(message, filesize)
                    cleanup_file(filepath)
                    return
            else:
                # Compression disabled, reject the file
                await self.handle_file_too_large(message, filesize)
                cleanup_file(filepath)
                return
        
        # Upload the video
        try:
            # Create a Discord File object
            with open(filepath, 'rb') as f:
                discord_file = discord.File(f, filename=f"{title[:50]}.mp4")  # Limit filename length
                
                # Reply to the original message with the video
                await message.reply(file=discord_file)
            
            # Add success reaction
            try:
                await message.add_reaction("✅")
            except discord.errors.Forbidden:
                pass
            
            logger.info(f"Successfully uploaded video from {url}")
            
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to upload video: {str(e)}")
            await message.reply(f"Failed to upload video - Discord error: {str(e)}")
            try:
                await message.add_reaction("❌")
            except discord.errors.Forbidden:
                pass
        
        except Exception as e:
            logger.error(f"Unexpected error uploading video: {str(e)}")
            await message.reply("An unexpected error occurred while uploading the video.")
            try:
                await message.add_reaction("❌")
            except discord.errors.Forbidden:
                pass
        
        finally:
            # Always clean up the temporary file
            cleanup_file(filepath)
    
    async def handle_download_error(self, message: discord.Message, url: str, platform: str = "Unknown"):
        """
        Handle a download error.
        
        Args:
            message: The original Discord message
            url: The URL that failed to download
            platform: The platform name
        """
        await message.reply(
            f"Unable to download video from {platform}. The video may be private, deleted, or the platform is blocking the request."
        )
        try:
            await message.add_reaction("❌")
        except discord.errors.Forbidden:
            pass
        logger.warning(f"Download failed for {url}")
    
    async def handle_file_too_large(self, message: discord.Message, filesize: int):
        """
        Handle a file that exceeds the size limit.
        
        Args:
            message: The original Discord message
            filesize: The size of the file in bytes
        """
        size_mb = filesize / 1024 / 1024
        limit_mb = config.MAX_FILE_SIZE / 1024 / 1024
        
        await message.reply(
            f"Video is too large to upload ({size_mb:.2f}MB exceeds {limit_mb:.0f}MB limit)."
        )
        try:
            await message.add_reaction("❌")
        except discord.errors.Forbidden:
            pass
        logger.warning(f"Video exceeds size limit: {size_mb:.2f}MB > {limit_mb:.0f}MB")
    
    async def handle_compression_failed(self, message: discord.Message, filesize: int):
        """
        Handle a file that could not be compressed enough.
        
        Args:
            message: The original Discord message
            filesize: The original size of the file in bytes
        """
        size_mb = filesize / 1024 / 1024
        limit_mb = config.MAX_FILE_SIZE / 1024 / 1024
        
        await message.reply(
            f"Video is too large ({size_mb:.2f}MB) and could not be compressed enough to fit the {limit_mb:.0f}MB limit. "
            f"Try posting a shorter video or lowering the quality."
        )
        try:
            await message.add_reaction("❌")
        except discord.errors.Forbidden:
            pass
        logger.warning(f"Compression failed: {size_mb:.2f}MB could not be reduced to {limit_mb:.0f}MB")


async def setup(bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(VideoHandler(bot))
