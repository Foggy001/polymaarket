# Polymarket Telegram Bot - PRD

## Original Problem Statement
Telegram бот для ручных ставок на Polymarket. Пользователь скидывает ссылку на событие, выбирает исход, выбирает сумму ставки и подтверждает.

## Implemented Features

### Commands
- `/start` - Приветствие и инструкция
- `/balance` - Баланс USDC на кошельке
- `/wallet` - Показать текущий кошелек
- `/setwallet` - Сменить кошелек (private key + funder address)
- `/positions` - Текущие позиции с кнопкой продать

### Betting Flow
1. Пользователь отправляет ссылку Polymarket
2. Бот показывает варианты исходов (YES/NO)
3. Пользователь выбирает исход
4. Бот предлагает сумму: 25% / 50% / 100% / Ввести вручную
5. Пользователь подтверждает
6. Бот размещает ставку

### Sell Flow
1. `/positions` показывает позиции
2. Кнопка "Продать" у каждой позиции
3. Выбор: 100% / 50%
4. Подтверждение продажи

## Architecture
- `telegram_bot.py` - Telegram бот (python-telegram-bot)
- `polymarket_client.py` - Polymarket CLOB API клиент
- Supervisor для автозапуска

## Credentials
- Telegram Bot Token: configured
- Polymarket Private Key: configured
- Polymarket Funder Address: configured

## What Was Removed
- GSI (Game State Integration) - автоматические ставки
- Trading Engine с триггерами
- REST API управления ботом

## Next Tasks
1. Тестирование в Telegram
2. Пополнение USDC на кошелек
3. Первая ставка
