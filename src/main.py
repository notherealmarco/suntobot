import asyncio
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import Config
from database import DatabaseManager
from summary_engine import SummaryEngine
from message_handler import MessageHandler as MsgHandler
from command_handler import CommandHandler as CmdHandler


# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class SuntoBot:
    """Main bot application."""

    def __init__(self):
        # Validate configuration
        Config.validate()

        # Initialize components
        self.db_manager = DatabaseManager(Config.DATABASE_URL)
        self.summary_engine = SummaryEngine()
        self.message_handler = MsgHandler(self.db_manager)
        self.command_handler = CmdHandler(self.db_manager, self.summary_engine)

        # Initialize Telegram application
        self.application = (
            Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        )

        # Register handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register bot handlers."""
        # Command handlers
        self.application.add_handler(
            CommandHandler("start", self.command_handler.handle_start_command)
        )
        self.application.add_handler(
            CommandHandler("help", self.command_handler.handle_help_command)
        )
        self.application.add_handler(
            CommandHandler("sunto", self.command_handler.handle_summary_command)
        )

        # Message handler for all text and photo messages
        self.application.add_handler(
            MessageHandler(
                filters.TEXT | filters.PHOTO, self.message_handler.handle_message
            )
        )

        # Error handler
        self.application.add_error_handler(self._error_handler)

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        logger.error(
            f"Exception while handling an update: {context.error}",
            exc_info=context.error,
        )

    async def run(self):
        """Run the bot."""
        logger.info("Starting SuntoBot...")
        logger.info(f"Monitoring groups: {Config.WHITELISTED_GROUPS}")

        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("SuntoBot is running! Press Ctrl+C to stop.")

        # Keep the bot running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()


async def main():
    """Main entry point."""
    try:
        bot = SuntoBot()
        await bot.run()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
