"""Discord Reels Reposter - Main Entry Point."""

import os
import logging
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import config

# Configure logging
logging.basicConfig(
    level=config.LOGGING_LEVEL,
    format=config.LOGGING_FORMAT,
    datefmt=config.LOGGING_DATE_FORMAT
)

logger = logging.getLogger(__name__)


def main():
    """Main function to start the Discord bot."""
    
    # Load environment variables
    load_dotenv()
    token = os.getenv('DISCORD_BOT_TOKEN')
    
    if not token:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables!")
        logger.error("Please create a .env file with your bot token:")
        logger.error("DISCORD_BOT_TOKEN=your_bot_token_here")
        return
    
    # Configure bot intents
    intents = discord.Intents.default()
    intents.message_content = True  # Required to read message content
    intents.messages = True
    intents.guilds = True
    
    # Create bot instance
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        """Event handler for when the bot is ready."""
        logger.info(f"Bot connected as {bot.user.name} (ID: {bot.user.id})")
        logger.info(f"Connected to {len(bot.guilds)} guild(s)")
        logger.info("Bot is ready to process Instagram URLs!")
    
    @bot.event
    async def on_error(event, *args, **kwargs):
        """Event handler for errors."""
        logger.error(f"Error in event {event}", exc_info=True)
    
    async def load_cogs():
        """Load all cogs."""
        try:
            await bot.load_extension('cogs.video_handler')
            logger.info("Loaded VideoHandler cog")
        except Exception as e:
            logger.error(f"Failed to load cogs: {str(e)}", exc_info=True)
    
    async def start_bot():
        """Start the bot with cogs loaded."""
        async with bot:
            await load_cogs()
            logger.info("Starting bot...")
            await bot.start(token)
    
    # Run the bot
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
