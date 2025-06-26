import os
from dotenv import load_dotenv
import asyncio
import random
import logging
import certifi
import ssl
from html import escape
import aiohttp
from telegram import Bot, Update
from telegram.ext import (
    Application,
    filters,
    MessageHandler,
    ContextTypes,
    CommandHandler
)
from telegram.constants import ParseMode

load_dotenv()

BOT_TOKEN = os.getenv('bot_token')
# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

MET_BASE_URL = "https://collectionapi.metmuseum.org/public/collection/v1"
HEADERS = {"User-Agent": "MetArtTelegramBot/1.0"}

async def fetch_json(session: aiohttp.ClientSession, url: str, params: dict = None) -> dict:
    """Fetch JSON data from an API endpoint asynchronously"""
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        async with session.get(url, params=params, headers=HEADERS, ssl=ssl_context) as response:
            response.raise_for_status()
            return await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.error(f"API request failed: {e}")
        return None

async def get_random_met_object() -> dict:
    """Fetch a random public domain art object with images"""
    search_params = {
        "hasImages": "true",
        "isPublicDomain": "true",
        "q": "*"
    }
    
    async with aiohttp.ClientSession() as session:
        # Get list of object IDs
        search_data = await fetch_json(
            session,
            f"{MET_BASE_URL}/search",
            search_params
        )
        
        if not search_data or not search_data.get('objectIDs'):
            return None
        
        # Select random object ID
        random_id = random.choice(search_data['objectIDs'])
        
        # Get object details
        object_data = await fetch_json(
            session,
            f"{MET_BASE_URL}/objects/{random_id}"
        )
        
        return object_data

def format_art_info(object_data: dict) -> str:
    """Format object information into HTML for Telegram"""
    fields = {
        "Title": object_data.get("title"),
        "Artist": object_data.get("artistDisplayName"),
        "Date": object_data.get("objectDate"),
        "Culture": object_data.get("culture"),
        "Period": object_data.get("period"),
        "Medium": object_data.get("medium"),
        "Country": object_data.get("country"),
    }
    
    # Filter out empty fields and escape values
    info_lines = [
        f"<b>{key}</b>: {escape(str(value))}" 
        for key, value in fields.items() 
        if value
    ]
    
    # Add object URL
    if object_url := object_data.get("objectURL"):
        info_lines.append(f'\n<a href="{object_url}">View on Met website</a>')
    
    return "\n".join(info_lines)

def get_best_image_url(object_data: dict) -> str:
    """Get the best available image URL with fallbacks"""
    return (
        object_data.get('primaryImageSmall') or
        object_data.get('primaryImage') or
        (object_data.get('additionalImages') or [None])[0]
    )

async def get_met_art_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a random Met art piece to the user"""
    user = update.effective_user
    logger.info(f"Art request from {user.full_name} ({user.id})")
    
    # Send typing indicator to show activity
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, 
        action="upload_photo"
    )
    
    # Fetch art object
    met_object = await get_random_met_object()
    
    if not met_object:
        await update.message.reply_text("🚫 Couldn't fetch artwork. Please try again later.")
        return
    
    # Get image and info
    image_url = get_best_image_url(met_object)
    caption = format_art_info(met_object)
    
    # Send result
    if image_url:
        try:
            await update.message.reply_photo(
                photo=image_url,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send image: {e}")
            await update.message.reply_text(
                f"🖼️ Image available at: {image_url}\n\n{caption}",
                parse_mode=ParseMode.HTML
            )
    else:
        await update.message.reply_text(
            f"❌ No image available for this artwork\n\n{caption}",
            parse_mode=ParseMode.HTML
        )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message with typing indicator"""
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, 
        action="typing"
    )
    await asyncio.sleep(0.5)  # Simulate processing time
    await update.message.reply_text(update.message.text)

def main() -> None:
    """Start the bot"""
    # Create Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_handler(CommandHandler('art', get_met_art_item))
    
    # Start polling
    logger.info("Bot is running...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()