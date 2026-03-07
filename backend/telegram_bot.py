"""
Polymarket Telegram Bot v2
Ручные ставки на Polymarket через Telegram
"""

import os
import re
import logging
from typing import Optional, Dict, Any, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
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

# User data storage
user_wallets: Dict[int, Dict[str, str]] = {}
pending_bets: Dict[int, Dict[str, Any]] = {}
user_states: Dict[int, str] = {}  # Track conversation state


async def get_user_client(user_id: int) -> Optional[PolymarketClient]:
    """Get Polymarket client for user"""
    if user_id in user_wallets:
        wallet = user_wallets[user_id]
        client = PolymarketClient(
            private_key=wallet['private_key'],
            funder_address=wallet['funder_address'],
            signature_type=1
        )
        await client.initialize()
        return client
    
    # Use default from env
    private_key = os.environ.get('POLYMARKET_PRIVATE_KEY')
    funder_address = os.environ.get('POLYMARKET_FUNDER_ADDRESS')
    
    if private_key and funder_address:
        client = PolymarketClient(
            private_key=private_key,
            funder_address=funder_address,
            signature_type=1
        )
        await client.initialize()
        return client
    
    return None


async def get_wallet_balance(wallet_address: str) -> float:
    """Get USDC.e balance directly from Polygon blockchain"""
    import httpx
    
    USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{
            "to": USDC_E,
            "data": f"0x70a08231000000000000000000000000{wallet_address[2:].lower()}"
        }, "latest"],
        "id": 1
    }
    
    rpcs = [
        "https://polygon-bor-rpc.publicnode.com",
        "https://1rpc.io/matic",
        "https://polygon.drpc.org"
    ]
    
    async with httpx.AsyncClient(timeout=10) as client:
        for rpc in rpcs:
            try:
                resp = await client.post(rpc, json=payload)
                result = resp.json()
                if 'result' in result and result['result']:
                    balance_wei = int(result['result'], 16)
                    return balance_wei / 1e6  # USDC has 6 decimals
            except Exception as e:
                logger.error(f"RPC {rpc} error: {e}")
                continue
    
    return 0.0


# === COMMANDS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    await update.message.reply_text(
        "🎮 *Polymarket Betting Bot*\n\n"
        "Отправьте ссылку на событие Polymarket для ставки.\n\n"
        "*Команды:*\n"
        "/balance - Баланс USDC\n"
        "/wallet - Текущий кошелек\n"
        "/setwallet - Сменить кошелек\n"
        "/positions - Ваши позиции\n"
        "/reset - Сбросить все данные\n\n"
        "Пример ссылки:\n"
        "`https://polymarket.com/sports/dota-2/...`",
        parse_mode='Markdown'
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance"""
    user_id = update.effective_user.id
    
    # Get wallet address
    if user_id in user_wallets:
        wallet_address = user_wallets[user_id]['funder_address']
    else:
        wallet_address = os.environ.get('POLYMARKET_FUNDER_ADDRESS')
    
    if not wallet_address:
        await update.message.reply_text("❌ Кошелек не настроен. /setwallet")
        return
    
    try:
        # Get balance from blockchain
        balance_amount = await get_wallet_balance(wallet_address)
        
        await update.message.reply_text(
            f"💰 *Баланс:* {balance_amount:.2f} USDC.e\n\n"
            f"Кошелек: `{wallet_address[:6]}...{wallet_address[-4:]}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current wallet"""
    user_id = update.effective_user.id
    
    if user_id in user_wallets:
        address = user_wallets[user_id]['funder_address']
    else:
        address = os.environ.get('POLYMARKET_FUNDER_ADDRESS', 'Не настроен')
    
    if address and len(address) > 10:
        masked = f"{address[:6]}...{address[-4:]}"
    else:
        masked = address
    
    await update.message.reply_text(
        f"👛 *Кошелек:* `{masked}`\n\n"
        f"Полный: `{address}`",
        parse_mode='Markdown'
    )


async def setwallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start wallet setup"""
    user_id = update.effective_user.id
    user_states[user_id] = 'waiting_private_key'
    
    await update.message.reply_text(
        "🔐 *Настройка кошелька*\n\n"
        "Шаг 1/2: Отправьте *Private Key*\n"
        "(с reveal.polymarket.com)\n\n"
        "/cancel - отменить",
        parse_mode='Markdown'
    )


async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show positions"""
    user_id = update.effective_user.id
    
    try:
        client = await get_user_client(user_id)
        if not client:
            await update.message.reply_text("❌ Кошелек не настроен. /setwallet")
            return
        
        orders = await client.get_open_orders()
        
        if not orders:
            await update.message.reply_text("📊 Нет активных позиций.")
            return
        
        text = "📊 *Ваши позиции:*\n\n"
        keyboard = []
        
        for i, order in enumerate(orders[:10]):
            token_id = order.get('asset_id', order.get('tokenID', 'N/A'))
            size = order.get('size', '0')
            price = order.get('price', '0')
            
            text += f"{i+1}. @ ${price} - {size} shares\n"
            keyboard.append([InlineKeyboardButton(f"🔴 Продать #{i+1}", callback_data=f"sell_{token_id[:30]}")])
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
    except Exception as e:
        logger.error(f"Positions error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset command"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, сбросить", callback_data="reset_yes"),
            InlineKeyboardButton("❌ Отмена", callback_data="reset_no")
        ]
    ]
    
    await update.message.reply_text(
        "⚠️ *Сбросить все данные?*\n\n"
        "• Настройки кошелька\n"
        "• Незавершенные ставки",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel any operation"""
    user_id = update.effective_user.id
    
    if user_id in user_states:
        del user_states[user_id]
    if user_id in pending_bets:
        del pending_bets[user_id]
    
    await update.message.reply_text("❌ Отменено.")


# === MESSAGE HANDLERS ===

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Check if user is in a conversation state
    state = user_states.get(user_id)
    
    if state == 'waiting_private_key':
        # Receiving private key
        private_key = text
        if not private_key.startswith('0x'):
            private_key = '0x' + private_key
        
        if len(private_key) != 66:
            await update.message.reply_text("❌ Неверный ключ. Должен быть 64 символа.\nПопробуйте снова:")
            return
        
        context.user_data['private_key'] = private_key
        user_states[user_id] = 'waiting_funder_address'
        
        # Try to delete message with key
        try:
            await update.message.delete()
        except:
            pass
        
        await update.message.reply_text(
            "✅ Ключ получен!\n\n"
            "Шаг 2/2: Отправьте *Proxy Wallet Address*\n"
            "(из polymarket.com → Settings)",
            parse_mode='Markdown'
        )
        return
    
    elif state == 'waiting_funder_address':
        # Receiving funder address
        funder_address = text
        
        if not funder_address.startswith('0x') or len(funder_address) != 42:
            await update.message.reply_text("❌ Неверный адрес. Должен начинаться с 0x.\nПопробуйте снова:")
            return
        
        private_key = context.user_data.get('private_key')
        
        user_wallets[user_id] = {
            'private_key': private_key,
            'funder_address': funder_address
        }
        
        del user_states[user_id]
        
        await update.message.reply_text(
            f"✅ *Кошелек настроен!*\n\n"
            f"Адрес: `{funder_address[:6]}...{funder_address[-4:]}`",
            parse_mode='Markdown'
        )
        return
    
    elif state == 'waiting_custom_amount':
        # Receiving custom amount
        try:
            amount = float(text.replace('$', '').replace(',', '.'))
        except ValueError:
            await update.message.reply_text("❌ Введите число. Например: 10")
            return
        
        if amount < 1:
            await update.message.reply_text("❌ Минимум 1 USDC")
            return
        
        pending_bets[user_id]['amount'] = amount
        del user_states[user_id]
        
        await show_bet_confirmation(update, user_id)
        return
    
    # Check if it's a Polymarket link
    if 'polymarket.com' in text:
        await handle_polymarket_link(update, context)
        return


async def handle_polymarket_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Polymarket links"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Extract slug
    match = re.search(r'polymarket\.com/(?:event/|sports/[^/]+/)?([a-zA-Z0-9-]+)', text)
    if not match:
        await update.message.reply_text("❌ Не могу распознать ссылку")
        return
    
    slug = match.group(1)
    logger.info(f"Parsed slug: {slug}")
    
    client = await get_user_client(user_id)
    if not client:
        await update.message.reply_text("❌ Кошелек не настроен. /setwallet")
        return
    
    await update.message.reply_text("🔍 Загружаю...")
    
    try:
        market = await client.fetch_market_by_slug(slug)
        
        if not market:
            await update.message.reply_text("❌ Событие не найдено")
            return
        
        pending_bets[user_id] = {'market': market, 'slug': slug}
        
        question = market.get('question', 'Unknown')
        yes_token = market.get('yes_token_id')
        no_token = market.get('no_token_id')
        
        keyboard = []
        if yes_token:
            keyboard.append([InlineKeyboardButton("✅ YES", callback_data=f"bet_yes_{yes_token[:30]}")])
        if no_token:
            keyboard.append([InlineKeyboardButton("❌ NO", callback_data=f"bet_no_{no_token[:30]}")])
        
        await update.message.reply_text(
            f"🎯 *{question}*\n\nВыберите исход:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Link error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def show_bet_confirmation(update_or_query, user_id: int):
    """Show bet confirmation"""
    bet = pending_bets.get(user_id, {})
    market = bet.get('market', {})
    outcome = bet.get('outcome', 'N/A')
    amount = bet.get('amount', 0)
    
    outcome_text = "YES ✅" if outcome == "yes" else "NO ❌"
    
    keyboard = [[
        InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ Отмена", callback_data="confirm_no")
    ]]
    
    text = (
        f"📋 *Подтверждение:*\n\n"
        f"{market.get('question', 'N/A')}\n"
        f"Исход: *{outcome_text}*\n"
        f"Сумма: *{amount:.2f} USDC*"
    )
    
    if hasattr(update_or_query, 'message'):
        await update_or_query.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


# === CALLBACK HANDLERS ===

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    logger.info(f"Callback: {data} from user {user_id}")
    
    # Reset
    if data == "reset_yes":
        if user_id in user_wallets:
            del user_wallets[user_id]
        if user_id in pending_bets:
            del pending_bets[user_id]
        if user_id in user_states:
            del user_states[user_id]
        context.user_data.clear()
        await query.edit_message_text("✅ Все данные сброшены!\n\n/setwallet - настроить кошелек")
        return
    
    if data == "reset_no":
        await query.edit_message_text("❌ Сброс отменен")
        return
    
    # Bet outcome selection
    if data.startswith("bet_"):
        parts = data.split("_")
        outcome = parts[1]  # yes or no
        token_id = parts[2]
        
        pending_bets[user_id]['outcome'] = outcome
        pending_bets[user_id]['token_id'] = token_id
        
        # Get wallet address
        if user_id in user_wallets:
            wallet_address = user_wallets[user_id]['funder_address']
        else:
            wallet_address = os.environ.get('POLYMARKET_FUNDER_ADDRESS')
        
        balance = await get_wallet_balance(wallet_address)
        pending_bets[user_id]['balance'] = balance
        
        keyboard = [
            [
                InlineKeyboardButton("25%", callback_data="amount_25"),
                InlineKeyboardButton("50%", callback_data="amount_50"),
                InlineKeyboardButton("100%", callback_data="amount_100")
            ],
            [InlineKeyboardButton("💵 Ввести сумму", callback_data="amount_custom")]
        ]
        
        outcome_text = "YES ✅" if outcome == "yes" else "NO ❌"
        
        await query.edit_message_text(
            f"Выбрано: *{outcome_text}*\n\n"
            f"💰 Баланс: {balance:.2f} USDC.e\n\n"
            f"Сумма ставки:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Amount selection
    if data.startswith("amount_"):
        amount_type = data.split("_")[1]
        
        if amount_type == "custom":
            user_states[user_id] = 'waiting_custom_amount'
            await query.edit_message_text("💵 Введите сумму в USDC:")
            return
        
        balance = pending_bets[user_id].get('balance', 0)
        
        percent = int(amount_type)
        amount = balance * (percent / 100)
        
        if amount < 1:
            await query.edit_message_text(f"❌ Недостаточно средств.\nБаланс: {balance:.2f} USDC.e")
            return
        
        pending_bets[user_id]['amount'] = amount
        await show_bet_confirmation(query, user_id)
        return
    
    # Confirm bet
    if data == "confirm_yes":
        bet = pending_bets.get(user_id)
        if not bet:
            await query.edit_message_text("❌ Ставка не найдена")
            return
        
        await query.edit_message_text("⏳ Размещаю ставку...")
        
        try:
            client = await get_user_client(user_id)
            market = bet['market']
            token_id = market.get('yes_token_id') if bet['outcome'] == 'yes' else market.get('no_token_id')
            amount = bet['amount']
            
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
                    f"Order: `{result.get('order_id', 'N/A')}`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(f"❌ Ошибка: {result.get('error')}")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
        finally:
            if user_id in pending_bets:
                del pending_bets[user_id]
        return
    
    if data == "confirm_no":
        if user_id in pending_bets:
            del pending_bets[user_id]
        await query.edit_message_text("❌ Ставка отменена")
        return
    
    # Sell
    if data.startswith("sell_"):
        token_id = data.replace("sell_", "")
        
        keyboard = [
            [
                InlineKeyboardButton("100%", callback_data=f"dosell_100_{token_id}"),
                InlineKeyboardButton("50%", callback_data=f"dosell_50_{token_id}")
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="sell_cancel")]
        ]
        
        await query.edit_message_text(
            "🔴 *Продать позицию*\n\nСколько продать?",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("dosell_"):
        parts = data.split("_")
        percent = parts[1]
        token_id = parts[2]
        
        await query.edit_message_text("⏳ Продаю...")
        
        try:
            client = await get_user_client(user_id)
            result = await client.place_market_order(
                token_id=token_id,
                side="SELL",
                amount=1,
                price_limit=0.01
            )
            
            if result.get('success'):
                await query.edit_message_text("✅ Продано!")
            else:
                await query.edit_message_text(f"❌ Ошибка: {result.get('error')}")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
        return
    
    if data == "sell_cancel":
        await query.edit_message_text("❌ Отменено")
        return


def main():
    """Start the bot"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    app = Application.builder().token(token).build()
    
    # Commands
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('balance', balance))
    app.add_handler(CommandHandler('wallet', wallet))
    app.add_handler(CommandHandler('setwallet', setwallet))
    app.add_handler(CommandHandler('positions', positions))
    app.add_handler(CommandHandler('reset', reset))
    app.add_handler(CommandHandler('cancel', cancel))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Starting Telegram bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
