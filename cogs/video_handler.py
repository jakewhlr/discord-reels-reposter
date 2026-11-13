"""Discord cog for handling video URL messages."""

import logging
import os
import discord
from discord.ext import commands
from utils.validators import extract_video_urls
from utils.downloader import download_video, cleanup_file, sanitize_filename
from utils.embeds import build_video_embed
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
        
        # If download failed outright
        if video_info is None:
            await self.handle_download_error(message, url, platform)
            return
        
        error = video_info.get('error')
        
        # The link simply isn't a video (Reddit text/image post, tweet with no
        # media). A Reddit share link gives no hint either way, so the only
        # sane behaviour is to drop it silently rather than reply with noise.
        if error == 'novideo':
            await self.clear_progress_reaction(message)
            logger.info(f"Ignoring non-video {platform} link: {url}")
            return
        
        # The platform demanded a login -- actionable for the operator
        if error == 'auth':
            await self.handle_auth_required(message, url, platform)
            return
        
        # Too long to ever fit in the upload limit
        if error == 'duration':
            await self.handle_too_long(message, video_info.get('duration', 0))
            return
        
        filepath = video_info['filepath']
        filesize = video_info['filesize']
        title = video_info['title']
        metadata = video_info.get('metadata') or {}
        
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
            # Keep the real container extension -- a merged download may be
            # .mkv/.webm rather than .mp4, and a mismatched name stops
            # Discord from playing it inline.
            ext = os.path.splitext(filepath)[1] or '.mp4'
            filename = f"{sanitize_filename(title)}{ext}"
            
            # Caption/author/stats ride along in a rich embed; the video
            # itself stays a normal attachment so Discord plays it inline.
            embed = None
            if config.ENABLE_EMBEDS:
                try:
                    embed = build_video_embed(metadata, platform)
                except Exception as e:
                    # An embed is a nicety -- never let it block the repost
                    logger.warning(f"Failed to build embed for {url}: {str(e)}")
            
            # Create a Discord File object
            with open(filepath, 'rb') as f:
                discord_file = discord.File(f, filename=filename)
                
                # Reply to the original message with the video
                await message.reply(file=discord_file, embed=embed)
            
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
    
    async def clear_progress_reaction(self, message: discord.Message):
        """
        Remove the bot's own "downloading" reaction.
        
        Used when the bot decides to bail silently, so a message doesn't sit
        there looking like a download is still in flight.
        
        Args:
            message: The original Discord message
        """
        try:
            await message.remove_reaction("⏬", self.bot.user)
        except (discord.errors.Forbidden, discord.errors.NotFound):
            pass
    
    async def handle_auth_required(self, message: discord.Message, url: str, platform: str):
        """
        Handle a video that is gated behind a login.
        
        Args:
            message: The original Discord message
            url: The URL that could not be fetched
            platform: The platform name
        """
        hint = config.PLATFORM_FAILURE_HINTS.get(
            platform, f"{platform} requires a logged-in session for this video."
        )
        
        await message.reply(
            f"Can't fetch this {platform} video without being logged in.\n-# {hint}"
        )
        try:
            await message.add_reaction("🔒")
        except discord.errors.Forbidden:
            pass
        logger.warning(f"Auth required for {url}")
    
    async def handle_download_error(self, message: discord.Message, url: str, platform: str = "Unknown"):
        """
        Handle a download error.
        
        Args:
            message: The original Discord message
            url: The URL that failed to download
            platform: The platform name
        """
        reply = (
            f"Unable to download video from {platform}. "
            "The video may be private, deleted, or the platform is blocking the request."
        )
        
        # Login-gated platforms get an extra nudge about cookies
        hint = config.PLATFORM_FAILURE_HINTS.get(platform)
        if hint:
            reply += f"\n-# {hint}"
        
        await message.reply(reply)
        try:
            await message.add_reaction("❌")
        except discord.errors.Forbidden:
            pass
        logger.warning(f"Download failed for {url}")
    
    async def handle_too_long(self, message: discord.Message, duration: int):
        """
        Handle a video that is too long to be worth downloading.
        
        Args:
            message: The original Discord message
            duration: The video duration in seconds
        """
        limit_min = config.MAX_DURATION_SECONDS / 60
        
        await message.reply(
            f"Video is too long to repost ({duration / 60:.1f} min exceeds the "
            f"{limit_min:.0f} min limit)."
        )
        try:
            await message.add_reaction("❌")
        except discord.errors.Forbidden:
            pass
        logger.warning(f"Video too long: {duration}s > {config.MAX_DURATION_SECONDS}s")
    
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
