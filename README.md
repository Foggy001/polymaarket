# Dota 2 Arbitrage Bot - Инструкция по настройке

## 🎮 Настройка GSI (Game State Integration) в Dota 2

### Шаг 1: Создайте файл конфигурации GSI

1. Найдите папку Dota 2:
   - **Windows**: `C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\cfg\`
   - **Linux**: `~/.steam/steam/steamapps/common/dota 2 beta/game/dota/cfg/`
   - **Mac**: `~/Library/Application Support/Steam/steamapps/common/dota 2 beta/game/dota/cfg/`

2. Создайте папку `gamestate_integration` если её нет

3. Создайте файл `gamestate_integration_arbitrage.cfg` с содержимым:

```
"dota2-arbitrage-bot"
{
    "uri"           "https://polygon-trader-1.preview.emergentagent.com/api/gsi"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "30.0"
    "data"
    {
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
        "events"        "1"
        "buildings"     "1"
        "league"        "1"
        "draft"         "1"
        "wearables"     "0"
    }
    "auth"
    {
        "token"         "dota2arbitragebot"
    }
}
```

### Шаг 2: Запустите Dota 2 с GSI

Добавьте параметр запуска в Steam:
1. Откройте Steam → Библиотека → Dota 2 → ПКМ → Свойства
2. В "Параметры запуска" добавьте: `-gamestateintegration`
3. Запустите игру

### Шаг 3: Смотрите матч как spectator

1. Откройте Dota 2
2. Перейдите в Watch → Live Games
3. Выберите матч с близкими коэффициентами (разница 0.3-0.4)
4. Бот начнет получать данные автоматически

---

## 🤖 API Endpoints

### Управление ботом
- `POST /api/bot/start` - Запустить бота
- `POST /api/bot/stop` - Остановить бота
- `GET /api/bot/status` - Статус бота и текущей игры
- `GET /api/bot/config` - Текущая конфигурация
- `POST /api/bot/config` - Обновить конфигурацию

### Polymarket
- `GET /api/markets/dota2` - Доступные Dota 2 рынки
- `POST /api/markets/select/{slug}` - Выбрать рынок для ставок
- `GET /api/balance` - Баланс на Polymarket

### Данные
- `POST /api/gsi` - Endpoint для GSI данных (автоматически)
- `GET /api/trades` - История ставок

---

## ⚡ Триггеры для ставки

Бот ставит когда **ВСЕ 3 условия** выполнены:

| Условие | Значение |
|---------|----------|
| Gold Advantage | ≥ 2000 |
| Kills (за 30 сек) | ≥ 3 |
| Время игры | ≥ 5 минут |

---

## 💰 Конфигурация

```json
{
  "gold_advantage_threshold": 2000,
  "kills_threshold": 3,
  "min_game_time": 300,
  "bet_amount": 5.0
}
```

Для изменения отправьте POST на `/api/bot/config`:

```bash
curl -X POST https://polygon-trader-1.preview.emergentagent.com/api/bot/config \
  -H "Content-Type: application/json" \
  -d '{"gold_advantage_threshold": 3000, "kills_threshold": 4, "min_game_time": 300, "bet_amount": 10.0}'
```

---

## ⚠️ Важно

1. **USDC на proxy wallet** - Пополните баланс на Polymarket перед использованием
2. **DotaTV delay** - Стандартная задержка 2 минуты от live игры
3. **Рынки** - Убедитесь что на Polymarket есть активный рынок для вашего матча
4. **Cooldown** - Между ставками минимум 60 секунд
