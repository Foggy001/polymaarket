"""
Polymarket Telegram Bot
Ручные ставки на Polymarket через Telegram
"""

import os
import re
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

from polymarket_client import PolymarketClient

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation
WAITING_PRIVATE_KEY, WAITING_FUNDER_ADDRESS = range(2)
WAITING_CUSTOM_AMOUNT = range(2, 3)

# Global client
polymarket_client: Optional[PolymarketClient] = None

# User data storage (in production use database)
user_wallets: Dict[int, Dict[str, str]] = {}
pending_bets: Dict[int, Dict[str, Any]] = {}


async def init_polymarket_client(private_key: str, funder_address: str) -> PolymarketClient:
    """Initialize Polymarket client with given credentials"""
    client = PolymarketClient(
        private_key=private_key,
        funder_address=funder_address,
        signature_type=1
    )
    await client.initialize()
    return client


async def get_user_client(user_id: int) -> Optional[PolymarketClient]:
    """Get or create Polymarket client for user"""
    global polymarket_client
    
    if user_id in user_wallets:
        wallet = user_wallets[user_id]
        return await init_polymarket_client(wallet['private_key'], wallet['funder_address'])
    elif polymarket_client:
        return polymarket_client
    
    return None


# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    await update.message.reply_text(
        "🎮 *Polymarket Betting Bot*\n\n"
        "Отправьте ссылку на событие Polymarket для ставки.\n\n"
        "*Команды:*\n"
        "/balance - Баланс USDC\n"
        "/wallet - Текущий кошелек\n"
        "/setwallet - Сменить кошелек\n"
        "/positions - Ваши позиции\n\n"
        "Пример ссылки:\n"
        "`https://polymarket.com/sports/dota-2/...`",
        parse_mode='Markdown'
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance"""
    user_id = update.effective_user.id
    client = await get_user_client(user_id)
    
    if not client:
        await update.message.reply_text(
            "❌ Кошелек не настроен.\n"
            "Используйте /setwallet для настройки."
        )
        return
    
    try:
        balance_data = await client.get_balance()
        balance_amount = balance_data.get('balance', '0')
        
        await update.message.reply_text(
            f"💰 *Баланс:* {balance_amount} USDC",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current wallet"""
    user_id = update.effective_user.id
    
    if user_id in user_wallets:
        address = user_wallets[user_id]['funder_address']
    else:
        address = os.environ.get('POLYMARKET_FUNDER_ADDRESS', 'Не настроен')
    
    # Mask address
    if address and len(address) > 10:
        masked = f"{address[:6]}...{address[-4:]}"
    else:
        masked = address
    
    await update.message.reply_text(
        f"👛 *Текущий кошелек:*\n`{masked}`\n\n"
        f"Полный адрес:\n`{address}`",
        parse_mode='Markdown'
    )


async def setwallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start wallet setup"""
    await update.message.reply_text(
        "🔐 *Настройка кошелька*\n\n"
        "Отправьте *Private Key* с reveal.polymarket.com\n\n"
        "⚠️ Ключ будет сохранен безопасно.",
        parse_mode='Markdown'
    )
    return WAITING_PRIVATE_KEY


async def setwallet_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive private key"""
    private_key = update.message.text.strip()
    
    # Add 0x if missing
    if not private_key.startswith('0x'):
        private_key = '0x' + private_key
    
    # Validate format
    if len(private_key) != 66:
        await update.message.reply_text(
            "❌ Неверный формат ключа.\n"
            "Ключ должен быть 64 символа (+ 0x).\n\n"
            "Попробуйте снова:"
        )
        return WAITING_PRIVATE_KEY
    
    # Store temporarily
    context.user_data['private_key'] = private_key
    
    # Delete the message with key for security
    try:
        await update.message.delete()
    except:
        pass
    
    await update.message.reply_text(
        "✅ Ключ получен!\n\n"
        "Теперь отправьте *Proxy Wallet Address*\n"
        "(из polymarket.com → Settings)",
        parse_mode='Markdown'
    )
    return WAITING_FUNDER_ADDRESS


async def setwallet_funder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive funder address"""
    user_id = update.effective_user.id
    funder_address = update.message.text.strip()
    
    # Validate format
    if not funder_address.startswith('0x') or len(funder_address) != 42:
        await update.message.reply_text(
            "❌ Неверный формат адреса.\n"
            "Адрес должен начинаться с 0x и быть 42 символа.\n\n"
            "Попробуйте снова:"
        )
        return WAITING_FUNDER_ADDRESS
    
    private_key = context.user_data.get('private_key')
    
    # Save wallet
    user_wallets[user_id] = {
        'private_key': private_key,
        'funder_address': funder_address
    }
    
    # Test connection
    try:
        client = await init_polymarket_client(private_key, funder_address)
        balance_data = await client.get_balance()
        balance_amount = balance_data.get('balance', '0')
        
        await update.message.reply_text(
            f"✅ *Кошелек настроен!*\n\n"
            f"Адрес: `{funder_address[:6]}...{funder_address[-4:]}`\n"
            f"Баланс: {balance_amount} USDC",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Кошелек сохранен, но есть проблема:\n{str(e)}"
        )
    
    return ConversationHandler.END


async def setwallet_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel wallet setup"""
    await update.message.reply_text("❌ Настройка отменена.")
    return ConversationHandler.END


async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user positions"""
    user_id = update.effective_user.id
    client = await get_user_client(user_id)
    
    if not client:
        await update.message.reply_text(
            "❌ Кошелек не настроен.\n"
            "Используйте /setwallet для настройки."
        )
        return
    
    try:
        # Get open orders and positions
        orders = await client.get_open_orders()
        
        if not orders:
            await update.message.reply_text(
                "📊 *Ваши позиции:*\n\n"
                "Нет активных позиций.",
                parse_mode='Markdown'
            )
            return
        
        text = "📊 *Ваши позиции:*\n\n"
        keyboard = []
        
        for i, order in enumerate(orders[:10]):  # Limit to 10
            token_id = order.get('asset_id', order.get('tokenID', 'N/A'))
            size = order.get('size', order.get('original_size', '0'))
            price = order.get('price', '0')
            side = order.get('side', 'N/A')
            
            text += f"{i+1}. {side} @ ${price}\n"
            text += f"   Size: {size} shares\n"
            text += f"   Token: `{token_id[:16]}...`\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"🔴 Продать #{i+1}",
                    callback_data=f"sell_{token_id[:32]}_{size}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def handle_polymarket_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Polymarket links"""
    text = update.message.text
    user_id = update.effective_user.id
    
    # Extract slug from URL
    match = re.search(r'polymarket\.com/(?:event/|sports/[^/]+/)?([a-zA-Z0-9-]+)', text)
    if not match:
        return  # Not a valid link
    
    slug = match.group(1)
    logger.info(f"Parsed slug: {slug}")
    
    client = await get_user_client(user_id)
    if not client:
        await update.message.reply_text(
            "❌ Кошелек не настроен.\n"
            "Используйте /setwallet для настройки."
        )
        return
    
    await update.message.reply_text("🔍 Загружаю событие...")
    
    try:
        # Fetch market data
        market = await client.fetch_market_by_slug(slug)
        
        if not market:
            # Try to fetch from gamma API directly
            markets = await fetch_markets_by_slug(slug)
            if markets:
                market = markets[0]
        
        if not market:
            await update.message.reply_text("❌ Событие не найдено.")
            return
        
        # Store for later use
        pending_bets[user_id] = {
            'market': market,
            'slug': slug
        }
        
        # Create buttons for outcomes
        keyboard = []
        
        question = market.get('question', 'Unknown')
        yes_token = market.get('yes_token_id')
        no_token = market.get('no_token_id')
        
        if yes_token:
            keyboard.append([
                InlineKeyboardButton("✅ YES", callback_data=f"outcome_yes_{yes_token[:32]}")
            ])
        if no_token:
            keyboard.append([
                InlineKeyboardButton("❌ NO", callback_data=f"outcome_no_{no_token[:32]}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎯 *{question}*\n\n"
            f"Выберите исход:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error fetching market: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def fetch_markets_by_slug(slug: str) -> List[Dict]:
    """Fetch markets from Gamma API"""
    import httpx
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://gamma-api.polymarket.com/markets",
            params={"slug": slug}
        )
        if response.status_code == 200:
            return response.json()
    return []


async def handle_outcome_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle outcome selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if not data.startswith('outcome_'):
        return
    
    parts = data.split('_')
    outcome = parts[1]  # yes or no
    token_id = parts[2]
    
    # Store selection
    if user_id not in pending_bets:
        pending_bets[user_id] = {}
    
    pending_bets[user_id]['outcome'] = outcome
    pending_bets[user_id]['token_id'] = token_id
    
    # Get balance
    client = await get_user_client(user_id)
    balance_data = await client.get_balance()
    balance = float(balance_data.get('balance', 0))
    
    # Create amount buttons
    keyboard = [
        [
            InlineKeyboardButton("25%", callback_data="amount_25"),
            InlineKeyboardButton("50%", callback_data="amount_50"),
            InlineKeyboardButton("100%", callback_data="amount_100")
        ],
        [
            InlineKeyboardButton("💵 Ввести сумму", callback_data="amount_custom")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    outcome_text = "YES ✅" if outcome == "yes" else "NO ❌"
    
    await query.edit_message_text(
        f"Выбрано: *{outcome_text}*\n\n"
        f"💰 Баланс: {balance:.2f} USDC\n\n"
        f"Выберите сумму ставки:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def handle_amount_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle amount selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if not data.startswith('amount_'):
        return
    
    amount_type = data.split('_')[1]
    
    client = await get_user_client(user_id)
    balance_data = await client.get_balance()
    balance = float(balance_data.get('balance', 0))
    
    if amount_type == 'custom':
        pending_bets[user_id]['waiting_amount'] = True
        await query.edit_message_text(
            "💵 Введите сумму в USDC:\n\n"
            f"(Баланс: {balance:.2f} USDC)"
        )
        return
    
    # Calculate amount
    percent = int(amount_type)
    amount = balance * (percent / 100)
    
    if amount < 1:
        await query.edit_message_text(
            f"❌ Недостаточно средств.\n"
            f"Минимум: 1 USDC\n"
            f"Баланс: {balance:.2f} USDC"
        )
        return
    
    pending_bets[user_id]['amount'] = amount
    
    # Confirm bet
    await show_bet_confirmation(query, user_id)


async def handle_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom amount input"""
    user_id = update.effective_user.id
    
    if user_id not in pending_bets or not pending_bets[user_id].get('waiting_amount'):
        return
    
    try:
        amount = float(update.message.text.strip().replace('$', '').replace(',', '.'))
    except ValueError:
        await update.message.reply_text("❌ Введите число. Например: 10 или 5.5")
        return
    
    if amount < 1:
        await update.message.reply_text("❌ Минимальная ставка: 1 USDC")
        return
    
    client = await get_user_client(user_id)
    balance_data = await client.get_balance()
    balance = float(balance_data.get('balance', 0))
    
    if amount > balance:
        await update.message.reply_text(
            f"❌ Недостаточно средств.\n"
            f"Запрошено: {amount:.2f} USDC\n"
            f"Баланс: {balance:.2f} USDC"
        )
        return
    
    pending_bets[user_id]['amount'] = amount
    pending_bets[user_id]['waiting_amount'] = False
    
    # Show confirmation
    bet = pending_bets[user_id]
    market = bet.get('market', {})
    outcome = bet.get('outcome', 'N/A')
    
    outcome_text = "YES ✅" if outcome == "yes" else "NO ❌"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_bet"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_bet")
        ]
    ]
    
    await update.message.reply_text(
        f"📋 *Подтверждение ставки:*\n\n"
        f"Событие: {market.get('question', 'N/A')}\n"
        f"Исход: *{outcome_text}*\n"
        f"Сумма: *{amount:.2f} USDC*\n\n"
        f"Подтвердить?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_bet_confirmation(query, user_id: int):
    """Show bet confirmation"""
    bet = pending_bets[user_id]
    market = bet.get('market', {})
    outcome = bet.get('outcome', 'N/A')
    amount = bet.get('amount', 0)
    
    outcome_text = "YES ✅" if outcome == "yes" else "NO ❌"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_bet"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_bet")
        ]
    ]
    
    await query.edit_message_text(
        f"📋 *Подтверждение ставки:*\n\n"
        f"Событие: {market.get('question', 'N/A')}\n"
        f"Исход: *{outcome_text}*\n"
        f"Сумма: *{amount:.2f} USDC*\n\n"
        f"Подтвердить?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_bet_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bet confirmation"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data == 'cancel_bet':
        if user_id in pending_bets:
            del pending_bets[user_id]
        await query.edit_message_text("❌ Ставка отменена.")
        return
    
    if data != 'confirm_bet':
        return
    
    bet = pending_bets.get(user_id)
    if not bet:
        await query.edit_message_text("❌ Ставка не найдена. Попробуйте заново.")
        return
    
    await query.edit_message_text("⏳ Размещаю ставку...")
    
    try:
        client = await get_user_client(user_id)
        
        token_id = bet['market'].get('yes_token_id') if bet['outcome'] == 'yes' else bet['market'].get('no_token_id')
        amount = bet['amount']
        
        # Place order
        result = await client.place_market_order(
            token_id=token_id,
            side="BUY",
            amount=amount,
            price_limit=0.99
        )
        
        if result.get('success'):
            await query.edit_message_text(
                f"✅ *Ставка принята!*\n\n"
                f"Сумма: {amount:.2f} USDC\n"
                f"Order ID: `{result.get('order_id', 'N/A')}`",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ Ошибка размещения:\n{result.get('error', 'Unknown error')}"
            )
        
    except Exception as e:
        logger.error(f"Error placing bet: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")
    
    finally:
        if user_id in pending_bets:
            del pending_bets[user_id]


async def handle_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle sell button"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if not data.startswith('sell_'):
        return
    
    parts = data.split('_')
    token_id = parts[1]
    size = parts[2] if len(parts) > 2 else "all"
    
    keyboard = [
        [
            InlineKeyboardButton("100%", callback_data=f"sellconf_100_{token_id}"),
            InlineKeyboardButton("50%", callback_data=f"sellconf_50_{token_id}")
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_sell")
        ]
    ]
    
    await query.edit_message_text(
        f"🔴 *Продать позицию*\n\n"
        f"Сколько продать?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_sell_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm sell"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data == 'cancel_sell':
        await query.edit_message_text("❌ Продажа отменена.")
        return
    
    if not data.startswith('sellconf_'):
        return
    
    parts = data.split('_')
    percent = int(parts[1])
    token_id = parts[2]
    
    await query.edit_message_text("⏳ Продаю...")
    
    try:
        client = await get_user_client(user_id)
        
        # Place sell order
        result = await client.place_market_order(
            token_id=token_id,
            side="SELL",
            amount=1,  # Will need to get actual amount
            price_limit=0.01
        )
        
        if result.get('success'):
            await query.edit_message_text(
                f"✅ *Позиция продана!*\n\n"
                f"Order ID: `{result.get('order_id', 'N/A')}`",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ Ошибка: {result.get('error', 'Unknown')}"
            )
            
    except Exception as e:
        logger.error(f"Error selling: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")


def main():
    """Start the bot"""
    global polymarket_client
    
    # Get token from environment
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    # Initialize default Polymarket client
    private_key = os.environ.get('POLYMARKET_PRIVATE_KEY')
    funder_address = os.environ.get('POLYMARKET_FUNDER_ADDRESS')
    
    # Create application
    app = Application.builder().token(token).build()
    
    # Wallet setup conversation
    wallet_conv = ConversationHandler(
        entry_points=[CommandHandler('setwallet', setwallet_start)],
        states={
            WAITING_PRIVATE_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, setwallet_private_key)],
            WAITING_FUNDER_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, setwallet_funder)]
        },
        fallbacks=[CommandHandler('cancel', setwallet_cancel)]
    )
    
    # Add handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('balance', balance))
    app.add_handler(CommandHandler('wallet', wallet))
    app.add_handler(CommandHandler('positions', positions))
    app.add_handler(wallet_conv)
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(handle_outcome_selection, pattern='^outcome_'))
    app.add_handler(CallbackQueryHandler(handle_amount_selection, pattern='^amount_'))
    app.add_handler(CallbackQueryHandler(handle_bet_confirmation, pattern='^(confirm_bet|cancel_bet)$'))
    app.add_handler(CallbackQueryHandler(handle_sell, pattern='^sell_'))
    app.add_handler(CallbackQueryHandler(handle_sell_confirm, pattern='^(sellconf_|cancel_sell)'))
    
    # Message handlers
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'polymarket\.com'),
        handle_polymarket_link
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_custom_amount
    ))
    
    logger.info("Starting Telegram bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
