# Polymarket Telegram Bot - PRD

## Original Problem Statement
Telegram бот для ручных ставок на Polymarket. Пользователь отправляет ссылку на событие, выбирает рынок (победитель матча/карты), выбирает исход, указывает сумму ставки и подтверждает.

## Implemented Features

### Commands
- `/start` - Приветствие и инструкция
- `/balance` - Баланс USDC.e на кошельке (прямое чтение из Polygon blockchain)
- `/wallet` - Показать текущий кошелек
- `/setwallet` - Сменить кошелек (private key + proxy wallet address)
- `/positions` - Текущие позиции с кнопкой продать
- `/proxy` - Показать текущий прокси
- `/setproxy` - Сменить прокси (формат: host:port:user:pass)
- `/reset` - Сбросить все данные пользователя
- `/cancel` - Отменить текущую операцию

### Betting Flow
1. Пользователь отправляет ссылку Polymarket
2. Бот парсит событие и показывает типы рынков:
   - 🏆 Победитель матча (moneyline)
   - 🎮 Победитель карты (child_moneyline)
3. Пользователь выбирает рынок
4. Бот показывает исходы с процентами (из outcomePrices)
5. Пользователь выбирает исход
6. Бот предлагает сумму: 25% / 50% / 100% / Ввести вручную
7. Пользователь подтверждает
8. Бот размещает market order через CLOB API

### Sell Flow
1. `/positions` показывает открытые ордера
2. Кнопка "Продать" у каждой позиции
3. Выбор: 100% / 50%
4. Подтверждение продажи

## Architecture
```
/app/backend/
├── telegram_bot.py       # Telegram бот (python-telegram-bot)
├── polymarket_client.py  # Polymarket CLOB API клиент с поддержкой прокси
├── db.py                 # MongoDB модели (для user_data)
├── telegram_bot.conf     # Supervisor конфиг
└── .env                  # Credentials
```

## Key Technical Details

### Proxy Support (FIXED - 2026-03-07)
- Решена проблема гео-блокировки (ошибка 403)
- Прокси применяется к внутреннему httpx клиенту py-clob-client через патч `_http_client`
- Используется HTTPTransport с mounts для HTTP/HTTPS
- Зависимость: `httpx[socks]` установлена для поддержки SOCKS5

### Balance Reading
- Баланс USDC.e читается напрямую из Polygon blockchain через RPC
- Не используется API Polymarket (показывает только trading balance)
- Contract: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`

### Market Order Placement
- Используется py-clob-client v0.34.6
- MarketOrderArgs с OrderType.FOK (Fill-Or-Kill)
- Signature type: POLY_PROXY (1)

## Credentials (in .env)
- `TELEGRAM_BOT_TOKEN` - токен Telegram бота
- `POLYMARKET_PRIVATE_KEY` - приватный ключ с reveal.polymarket.com
- `POLYMARKET_FUNDER_ADDRESS` - адрес proxy wallet
- `PROXY` - прокси в формате host:port:user:pass
- `MONGO_URL` - MongoDB connection string
- `DB_NAME` - имя базы данных

## Completed Work

### Session 2026-03-07
- ✅ Исправлена проблема гео-блокировки (403 Forbidden)
- ✅ Реализован патч httpx клиента для py-clob-client
- ✅ Протестирована работа API через прокси (get_balance, get_orders работают)

### Previous Sessions
- ✅ Полный редизайн проекта (GSI бот → Telegram бот)
- ✅ Команды /start, /balance, /wallet, /setwallet
- ✅ Команды /positions, /reset, /cancel
- ✅ Команды /proxy, /setproxy
- ✅ Парсинг ссылок Polymarket (события и рынки)
- ✅ Пошаговый процесс ставки с inline-кнопками
- ✅ Интеграция с Polygon blockchain для баланса
- ✅ Supervisor конфигурация

## Next Steps
1. Пользователю протестировать бота в Telegram с реальной ссылкой
2. Пополнить USDC на кошелек (если пустой)
3. Сделать тестовую ставку на открытом рынке

## Files to Remove (Legacy)
- `/app/backend/server.py` - устаревший FastAPI сервер
- `/app/backend/gsi_server.py` - GSI обработчик
- `/app/backend/trading_engine.py` - движок арбитража
