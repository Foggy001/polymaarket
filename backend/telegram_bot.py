"""
Polymarket Telegram Bot v2
Ручные ставки на Polymarket через Telegram
"""

import os
import re
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from dotenv import load_dotenv
# Load .env from the same directory as this script
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

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
user_proxies: Dict[int, str] = {}  # User proxies

# Default proxy
DEFAULT_PROXY = os.environ.get('PROXY', '163.5.176.118:45228:5GEF73OD:SD63124L')
# Default signature type (2 = POLY_GNOSIS_SAFE for MetaMask login)
DEFAULT_SIGNATURE_TYPE = int(os.environ.get('SIGNATURE_TYPE', '2'))

logger.info(f"Loaded SIGNATURE_TYPE={DEFAULT_SIGNATURE_TYPE}")


async def get_user_client(user_id: int) -> Optional[PolymarketClient]:
    """Get Polymarket client for user"""
    # Get proxy
    proxy = user_proxies.get(user_id, DEFAULT_PROXY)
    
    if user_id in user_wallets:
        wallet = user_wallets[user_id]
        client = PolymarketClient(
            private_key=wallet['private_key'],
            funder_address=wallet['funder_address'],
            signature_type=wallet.get('signature_type', DEFAULT_SIGNATURE_TYPE),
            proxy=proxy
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
            signature_type=DEFAULT_SIGNATURE_TYPE,
            proxy=proxy
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
        "/proxy - Текущий прокси\n"
        "/setproxy - Сменить прокси\n"
        "/reset - Сбросить все данные\n\n"
        "Пример ссылки:\n"
        "`https://polymarket.com/esports/dota-2/...`",
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
    """Show positions from Polymarket Data API"""
    user_id = update.effective_user.id
    
    # Get wallet address
    if user_id in user_wallets:
        wallet_address = user_wallets[user_id]['funder_address']
    else:
        wallet_address = os.environ.get('POLYMARKET_FUNDER_ADDRESS')
    
    if not wallet_address:
        await update.message.reply_text("❌ Кошелек не настроен. /setwallet")
        return
    
    await update.message.reply_text("🔍 Загружаю позиции...")
    
    try:
        import httpx
        
        async with httpx.AsyncClient(timeout=15) as http:
            # Get positions from Data API
            resp = await http.get(
                f"https://data-api.polymarket.com/positions",
                params={"user": wallet_address}
            )
            
            if resp.status_code != 200:
                await update.message.reply_text(f"❌ Ошибка API: {resp.status_code}")
                return
            
            positions_data = resp.json()
        
        if not positions_data:
            await update.message.reply_text("📊 Нет активных позиций.")
            return
        
        text = "📊 *Ваши позиции:*\n\n"
        keyboard = []
        
        for i, pos in enumerate(positions_data[:10]):
            outcome = pos.get('outcome', 'N/A')
            size = float(pos.get('size', 0))
            current_value = float(pos.get('currentValue', 0))
            pnl = float(pos.get('cashPnl', 0))
            title = pos.get('title', '')[:30]
            token_id = pos.get('asset', '')
            
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            
            text += f"*{i+1}. {title}...*\n"
            text += f"   {outcome}: {size:.1f} shares\n"
            text += f"   💰 ${current_value:.2f} {pnl_emoji} P&L: ${pnl:.2f}\n\n"
            
            if token_id:
                keyboard.append([InlineKeyboardButton(
                    f"🔴 Продать #{i+1}",
                    callback_data=f"sellpos_{i}"
                )])
        
        # Store positions for selling
        pending_bets[user_id] = {'positions': positions_data}
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
    except Exception as e:
        logger.error(f"Positions error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
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
        "• Незавершенные ставки\n"
        "• Прокси",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current proxy"""
    user_id = update.effective_user.id
    current_proxy = user_proxies.get(user_id, DEFAULT_PROXY)
    
    if current_proxy:
        parts = current_proxy.split(':')
        if len(parts) >= 2:
            masked = f"{parts[0]}:{parts[1]}:***:***"
        else:
            masked = current_proxy
    else:
        masked = "Не настроен"
    
    await update.message.reply_text(
        f"🌐 *Текущий прокси:*\n`{masked}`",
        parse_mode='Markdown'
    )


async def setproxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set proxy"""
    user_id = update.effective_user.id
    user_states[user_id] = 'waiting_proxy'
    
    await update.message.reply_text(
        "🌐 *Настройка прокси*\n\n"
        "Отправьте прокси в формате:\n"
        "`host:port:user:password`\n\n"
        "или без авторизации:\n"
        "`host:port`\n\n"
        "/cancel - отменить",
        parse_mode='Markdown'
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
            'funder_address': funder_address,
            'signature_type': DEFAULT_SIGNATURE_TYPE  # Use signature_type=2 for MetaMask
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
    
    elif state == 'waiting_fork_price':
        # Receiving fork limit price
        try:
            price = float(text.replace('%', '').replace(',', '.'))
            # If user entered percentage (like 10), convert to decimal
            if price > 1:
                price = price / 100
        except ValueError:
            await update.message.reply_text("❌ Введите число. Например: 0.10 или 10")
            return
        
        if price <= 0 or price >= 1:
            await update.message.reply_text("❌ Цена должна быть от 0.01 до 0.99")
            return
        
        fork = pending_bets.get(user_id, {}).get('fork', {})
        if not fork:
            await update.message.reply_text("❌ Данные вилки не найдены")
            del user_states[user_id]
            return
        
        original_amount = fork.get('original_amount', 0)
        
        # Calculate fork amount: amount that covers original bet
        # If original bet wins: we lose fork_amount
        # If fork wins: we get fork_amount / price
        # To cover original: fork_amount / price >= original_amount
        # So: fork_amount >= original_amount * price
        fork_amount = original_amount * price
        
        # Round up to ensure coverage
        fork_amount = round(fork_amount + 0.01, 2)
        
        # Minimum 1 USDC
        if fork_amount < 1:
            fork_amount = 1.0
        
        pending_bets[user_id]['fork']['price'] = price
        pending_bets[user_id]['fork']['amount'] = fork_amount
        del user_states[user_id]
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="fork_confirm_yes"),
                InlineKeyboardButton("❌ Отмена", callback_data="fork_confirm_no")
            ]
        ]
        
        await update.message.reply_text(
            f"🔀 *Вилка - подтверждение*\n\n"
            f"Исход: *{fork['opposite_outcome']}*\n"
            f"Цена лимитки: *{price:.2f}* ({price*100:.0f}%)\n"
            f"Сумма: *{fork_amount:.2f} USDC*\n\n"
            f"_(автоматически рассчитано для покрытия ставки {original_amount:.2f} USDC)_",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif state == 'waiting_proxy':
        # Receiving proxy
        proxy_str = text.strip()
        parts = proxy_str.split(':')
        
        if len(parts) not in [2, 4]:
            await update.message.reply_text(
                "❌ Неверный формат.\n\n"
                "Используйте: `host:port:user:pass`\n"
                "или: `host:port`",
                parse_mode='Markdown'
            )
            return
        
        user_proxies[user_id] = proxy_str
        del user_states[user_id]
        
        # Delete message with proxy for security
        try:
            await update.message.delete()
        except:
            pass
        
        await update.message.reply_text(
            f"✅ *Прокси настроен!*\n\n"
            f"`{parts[0]}:{parts[1]}:***:***`",
            parse_mode='Markdown'
        )
        return
    
    # Check if it's a Polymarket link
    if 'polymarket.com' in text:
        await handle_polymarket_link(update, context)
        return


async def handle_polymarket_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Polymarket links"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Extract slug - support various URL formats:
    # /event/slug
    # /sports/dota-2/slug
    # /esports/dota-2/tournament/slug
    # /esports/dota-2/esl-one/slug
    match = re.search(r'polymarket\.com/(?:event/|(?:sports|esports)/[^/]+/(?:[^/]+/)?)?([a-zA-Z0-9-]+)(?:\?|$)', text)
    if not match:
        # Try to get last path segment as slug
        match = re.search(r'polymarket\.com/.+/([a-zA-Z0-9-]+)(?:\?|$)', text)
    
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
        import json as json_lib
        import httpx
        
        # Fetch EVENT with all related markets
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(f"https://gamma-api.polymarket.com/events?slug={slug}")
            events = resp.json()
        
        if not events:
            await update.message.reply_text("❌ Событие не найдено")
            return
        
        event = events[0] if isinstance(events, list) else events
        all_markets = event.get('markets', [])
        
        if not all_markets:
            await update.message.reply_text("❌ Нет доступных рынков")
            return
        
        # Store all markets
        pending_bets[user_id] = {
            'event': event,
            'all_markets': all_markets,
            'slug': slug
        }
        
        # Group markets by type - only match winner and map winner
        market_types = {
            'moneyline': '🏆 Победитель матча',
            'child_moneyline': '🎮 Победитель карты',
        }
        
        # Create menu with market categories
        keyboard = []
        added_types = set()
        
        for m in all_markets:
            mtype = m.get('sportsMarketType', 'other')
            if mtype in market_types and mtype not in added_types:
                added_types.add(mtype)
                keyboard.append([
                    InlineKeyboardButton(
                        market_types[mtype],
                        callback_data=f"mtype_{mtype}"
                    )
                ])
        
        event_title = event.get('title', 'Событие')
        
        await update.message.reply_text(
            f"🎯 *{event_title}*\n\n"
            f"Всего рынков: {len(all_markets)}\n\n"
            f"Выберите тип ставки:",
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
    outcome_name = bet.get('outcome_name', 'N/A')
    amount = bet.get('amount', 0)
    
    keyboard = [[
        InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ Отмена", callback_data="confirm_no")
    ]]
    
    question = market.get('question', 'N/A')
    
    text = (
        f"📋 *Подтверждение:*\n\n"
        f"{question}\n\n"
        f"Исход: *{outcome_name}*\n"
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
        if user_id in user_proxies:
            del user_proxies[user_id]
        context.user_data.clear()
        await query.edit_message_text("✅ Все данные сброшены!\n\n/setwallet - настроить кошелек")
        return
    
    if data == "reset_no":
        await query.edit_message_text("❌ Сброс отменен")
        return
    
    # Market type selection
    if data.startswith("mtype_"):
        import json as json_lib
        mtype = data.replace("mtype_", "")
        all_markets = pending_bets[user_id].get('all_markets', [])
        
        market_types = {
            'moneyline': '🏆 Победитель матча',
            'child_moneyline': '🎮 Победитель карты',
        }
        
        # Filter markets by type
        filtered = [m for m in all_markets if m.get('sportsMarketType') == mtype]
        
        if not filtered:
            await query.edit_message_text("❌ Нет рынков этого типа")
            return
        
        # Store filtered markets
        pending_bets[user_id]['filtered_markets'] = filtered
        
        # Show markets list
        keyboard = []
        for i, m in enumerate(filtered[:15]):  # Limit to 15
            question = m.get('question', 'Unknown')
            # Shorten question for button
            short_q = question[:40] + "..." if len(question) > 40 else question
            keyboard.append([
                InlineKeyboardButton(short_q, callback_data=f"market_{i}")
            ])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_types")])
        
        type_name = market_types.get(mtype, 'Другие')
        await query.edit_message_text(
            f"*{type_name}*\n\nВыберите рынок:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Back to market types
    if data == "back_to_types":
        all_markets = pending_bets[user_id].get('all_markets', [])
        event = pending_bets[user_id].get('event', {})
        
        market_types = {
            'moneyline': '🏆 Победитель матча',
            'child_moneyline': '🎮 Победитель карты',
        }
        
        keyboard = []
        added_types = set()
        
        for m in all_markets:
            mtype = m.get('sportsMarketType', 'other')
            if mtype in market_types and mtype not in added_types:
                added_types.add(mtype)
                keyboard.append([InlineKeyboardButton(market_types[mtype], callback_data=f"mtype_{mtype}")])
        
        await query.edit_message_text(
            f"🎯 *{event.get('title', 'Событие')}*\n\nВыберите тип ставки:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Market selection
    if data.startswith("market_"):
        import json as json_lib
        market_idx = int(data.replace("market_", ""))
        filtered_markets = pending_bets[user_id].get('filtered_markets', [])
        
        if market_idx >= len(filtered_markets):
            await query.edit_message_text("❌ Рынок не найден")
            return
        
        market = filtered_markets[market_idx]
        pending_bets[user_id]['market'] = market
        
        question = market.get('question', 'Unknown')
        
        # Parse outcomes
        outcomes_raw = market.get('outcomes', '["Yes", "No"]')
        prices_raw = market.get('outcomePrices', '["0", "0"]')
        tokens_raw = market.get('clobTokenIds', '[]')
        
        if isinstance(outcomes_raw, str):
            outcomes = json_lib.loads(outcomes_raw)
        else:
            outcomes = outcomes_raw
            
        if isinstance(prices_raw, str):
            outcome_prices = json_lib.loads(prices_raw)
        else:
            outcome_prices = prices_raw
            
        if isinstance(tokens_raw, str):
            tokens = json_lib.loads(tokens_raw)
        else:
            tokens = tokens_raw
        
        pending_bets[user_id]['outcomes'] = outcomes
        pending_bets[user_id]['tokens'] = tokens
        pending_bets[user_id]['prices'] = outcome_prices
        
        # Show outcomes
        keyboard = []
        for i, outcome in enumerate(outcomes):
            if i < len(tokens):
                price = float(outcome_prices[i]) if i < len(outcome_prices) else 0
                price_percent = int(price * 100)
                keyboard.append([
                    InlineKeyboardButton(
                        f"{outcome} ({price_percent}%)",
                        callback_data=f"bet_{i}_{tokens[i][:25]}"
                    )
                ])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_markets")])
        
        await query.edit_message_text(
            f"🎯 *{question}*\n\nВыберите исход:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Back to markets list
    if data == "back_to_markets":
        import json as json_lib
        filtered = pending_bets[user_id].get('filtered_markets', [])
        
        keyboard = []
        for i, m in enumerate(filtered[:15]):
            question = m.get('question', 'Unknown')
            short_q = question[:40] + "..." if len(question) > 40 else question
            keyboard.append([InlineKeyboardButton(short_q, callback_data=f"market_{i}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_types")])
        
        await query.edit_message_text(
            "Выберите рынок:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Bet outcome selection
    if data.startswith("bet_"):
        parts = data.split("_")
        outcome_index = int(parts[1])
        token_id = parts[2]
        
        # Get full token ID from stored data
        outcomes = pending_bets[user_id].get('outcomes', [])
        tokens = pending_bets[user_id].get('tokens', [])
        
        if outcome_index < len(tokens):
            full_token_id = tokens[outcome_index]
            outcome_name = outcomes[outcome_index] if outcome_index < len(outcomes) else f"Outcome {outcome_index}"
        else:
            full_token_id = token_id
            outcome_name = f"Outcome {outcome_index}"
        
        pending_bets[user_id]['outcome_index'] = outcome_index
        pending_bets[user_id]['outcome_name'] = outcome_name
        pending_bets[user_id]['token_id'] = full_token_id
        
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
        
        await query.edit_message_text(
            f"Выбрано: *{outcome_name}*\n\n"
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
            token_id = bet.get('token_id')
            amount = bet['amount']
            outcome_name = bet.get('outcome_name', 'Unknown')
            
            result = await client.place_market_order(
                token_id=token_id,
                side="BUY",
                amount=amount,
                price_limit=0.99
            )
            
            if result.get('success'):
                # Store bet info for potential fork
                pending_bets[user_id] = {
                    'last_bet': {
                        'token_id': token_id,
                        'amount': amount,
                        'outcome_name': outcome_name,
                        'outcome_index': bet.get('outcome_index', 0),
                        'market': bet.get('market', {}),
                        'tokens': bet.get('tokens', []),
                        'outcomes': bet.get('outcomes', []),
                        'prices': bet.get('prices', [])
                    }
                }
                
                # Add fork button
                keyboard = [[InlineKeyboardButton("🔀 Сделать вилку", callback_data="fork_start")]]
                
                await query.edit_message_text(
                    f"✅ *Ставка принята!*\n\n"
                    f"Исход: {outcome_name}\n"
                    f"Сумма: {amount:.2f} USDC\n"
                    f"Order: `{result.get('order_id', 'N/A')}`",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.edit_message_text(f"❌ Ошибка: {result.get('error')}")
                if user_id in pending_bets:
                    del pending_bets[user_id]
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
            if user_id in pending_bets:
                del pending_bets[user_id]
        return
    
    if data == "confirm_no":
        if user_id in pending_bets:
            del pending_bets[user_id]
        await query.edit_message_text("❌ Ставка отменена")
        return
    
    # Fork (Вилка) handlers
    if data == "fork_start":
        last_bet = pending_bets.get(user_id, {}).get('last_bet', {})
        if not last_bet:
            await query.edit_message_text("❌ Данные о ставке не найдены")
            return
        
        outcome_index = last_bet.get('outcome_index', 0)
        tokens = last_bet.get('tokens', [])
        outcomes = last_bet.get('outcomes', [])
        
        # Find opposite outcome
        if len(tokens) < 2:
            await query.edit_message_text("❌ Нет противоположного исхода для вилки")
            return
        
        opposite_index = 1 if outcome_index == 0 else 0
        opposite_token = tokens[opposite_index]
        opposite_outcome = outcomes[opposite_index] if opposite_index < len(outcomes) else "Opposite"
        
        # Store fork info
        pending_bets[user_id]['fork'] = {
            'opposite_token': opposite_token,
            'opposite_outcome': opposite_outcome,
            'original_amount': last_bet.get('amount', 0)
        }
        
        user_states[user_id] = 'waiting_fork_price'
        
        await query.edit_message_text(
            f"🔀 *Вилка*\n\n"
            f"Противоположный исход: *{opposite_outcome}*\n\n"
            f"Введите цену лимитки (например: 0.10 для 10%):",
            parse_mode='Markdown'
        )
        return
    
    if data.startswith("fork_confirm_"):
        action = data.replace("fork_confirm_", "")
        
        if action == "no":
            if user_id in pending_bets:
                del pending_bets[user_id]
            await query.edit_message_text("❌ Вилка отменена")
            return
        
        if action == "yes":
            fork = pending_bets.get(user_id, {}).get('fork', {})
            if not fork:
                await query.edit_message_text("❌ Данные вилки не найдены")
                return
            
            await query.edit_message_text("⏳ Создаю лимитку...")
            
            try:
                client = await get_user_client(user_id)
                
                result = await client.place_limit_order(
                    token_id=fork['opposite_token'],
                    side="BUY",
                    price=fork['price'],
                    size=fork['amount']
                )
                
                if result.get('success'):
                    await query.edit_message_text(
                        f"✅ *Вилка создана!*\n\n"
                        f"Исход: {fork['opposite_outcome']}\n"
                        f"Цена: {fork['price']}\n"
                        f"Сумма: {fork['amount']:.2f} USDC\n"
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
    
    # Sell position from /positions
    if data.startswith("sellpos_"):
        pos_idx = int(data.replace("sellpos_", ""))
        positions_data = pending_bets.get(user_id, {}).get('positions', [])
        
        if pos_idx >= len(positions_data):
            await query.edit_message_text("❌ Позиция не найдена")
            return
        
        pos = positions_data[pos_idx]
        token_id = pos.get('asset', '')
        size = float(pos.get('size', 0))
        outcome = pos.get('outcome', 'N/A')
        title = pos.get('title', '')[:30]
        
        # Store for selling
        pending_bets[user_id]['sell_position'] = {
            'token_id': token_id,
            'size': size,
            'outcome': outcome,
            'title': title
        }
        
        keyboard = [
            [
                InlineKeyboardButton("100%", callback_data="dosellpos_100"),
                InlineKeyboardButton("50%", callback_data="dosellpos_50")
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="sell_cancel")]
        ]
        
        await query.edit_message_text(
            f"🔴 *Продать позицию*\n\n"
            f"{title}...\n"
            f"Исход: {outcome}\n"
            f"Размер: {size:.1f} shares\n\n"
            f"Сколько продать?",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("dosellpos_"):
        percent = int(data.replace("dosellpos_", ""))
        sell_info = pending_bets.get(user_id, {}).get('sell_position', {})
        
        if not sell_info:
            await query.edit_message_text("❌ Данные о позиции потеряны")
            return
        
        token_id = sell_info['token_id']
        size = sell_info['size']
        sell_amount = size * (percent / 100)
        
        await query.edit_message_text(f"⏳ Продаю {sell_amount:.1f} shares...")
        
        try:
            client = await get_user_client(user_id)
            result = await client.place_market_order(
                token_id=token_id,
                side="SELL",
                amount=sell_amount,
                price_limit=0.01
            )
            
            if result.get('success'):
                await query.edit_message_text(
                    f"✅ *Продано!*\n\n"
                    f"Shares: {sell_amount:.1f}\n"
                    f"Order ID: `{result.get('order_id', 'N/A')[:20]}...`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(f"❌ Ошибка: {result.get('error')}")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
        return
    
    # Sell (old handler for backward compatibility)
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
    app.add_handler(CommandHandler('proxy', proxy))
    app.add_handler(CommandHandler('setproxy', setproxy))
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
