# Dota 2 Arbitrage Bot - PRD

## Original Problem Statement
Арбитражный бот для Polymarket по игре Dota 2 в лайве. Бот должен успевать покупать до изменения коэффициентов, используя GSI (Game State Integration) от Dota 2 для получения live данных.

## User Choices
- **Источник данных**: Dota 2 GSI (Game State Integration) - бесплатный, live данные
- **Логика триггеров**: Простая формула (все 3 условия должны выполняться)
- **Gold advantage threshold**: 2000
- **Kills threshold**: 3 (за 30 секунд)
- **Min game time**: 5 минут (300 секунд)
- **Bet amount**: 5 USDC (фиксированный)
- **Интерфейс**: Backend only с логами

## Architecture

### Components
1. **GSI Server** (`gsi_server.py`) - обработка данных из Dota 2 клиента
2. **Polymarket Client** (`polymarket_client.py`) - интеграция с Polymarket CLOB API
3. **Trading Engine** (`trading_engine.py`) - логика триггеров и выполнения ставок
4. **FastAPI Server** (`server.py`) - REST API для управления ботом

### Data Flow
```
Dota 2 Client (spectate mode)
    ↓
GSI → POST /api/gsi
    ↓
Trading Engine анализирует:
  - Gold advantage
  - Recent kills
  - Game time
    ↓
Триггер → Polymarket API → Ставка
```

## What's Been Implemented (2026-03-04)

### Core Features
- ✅ GSI endpoint для приема данных из Dota 2
- ✅ Polymarket CLOB API интеграция (py-clob-client v0.34.6)
- ✅ Автоматическая деривация API credentials
- ✅ Trading engine с 3-условным триггером
- ✅ REST API для управления ботом
- ✅ MongoDB для логирования сделок
- ✅ Конфигурируемые пороги триггеров

### API Endpoints
- GET /api/health
- GET /api/balance
- POST /api/bot/start
- POST /api/bot/stop
- GET /api/bot/status
- GET/POST /api/bot/config
- POST /api/gsi
- GET /api/markets/dota2
- POST /api/markets/select/{slug}
- GET /api/trades

### Credentials Configured
- Polymarket private key: ✅
- Polymarket proxy wallet: ✅
- Signature type: POLY_PROXY (1)

## Prioritized Backlog

### P0 (Critical)
- [ ] Пополнить USDC на proxy wallet для реальных ставок

### P1 (High)
- [ ] Добавить webhook уведомления о ставках (Telegram/Discord)
- [ ] Логирование в файл для анализа
- [ ] Мониторинг нескольких матчей одновременно

### P2 (Medium)
- [ ] Web UI для мониторинга
- [ ] Статистика win/loss по ставкам
- [ ] Автоматический выбор рынков по названию команд

### P3 (Low)
- [ ] AI-анализ для улучшения триггеров
- [ ] Бэктестинг на исторических данных

## Next Tasks
1. Пополнить баланс USDC на Polymarket proxy wallet
2. Настроить GSI в Dota 2 клиенте
3. Выбрать активный рынок на Polymarket
4. Протестировать на live матче
