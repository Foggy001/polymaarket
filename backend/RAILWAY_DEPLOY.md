# Polymarket Telegram Bot - Railway Deploy

## Быстрый деплой на Railway (5 минут)

### Шаг 1: Сохранить код на GitHub

В интерфейсе Emergent нажмите **"Save to GitHub"** (иконка GitHub в чате).

---

### Шаг 2: Создать аккаунт Railway

1. Перейдите на https://railway.app
2. Нажмите **"Login"** → войдите через GitHub

---

### Шаг 3: Создать проект

1. Нажмите **"New Project"**
2. Выберите **"Deploy from GitHub repo"**
3. Найдите ваш репозиторий и выберите его
4. Railway автоматически обнаружит Python проект

---

### Шаг 4: Настроить переменные окружения

В Railway dashboard → ваш проект → **Variables** → добавьте:

```
TELEGRAM_BOT_TOKEN=8685153443:AAGGxd024FJwgeztLd-qoMbVE_vJ7zvNbPc
POLYMARKET_PRIVATE_KEY=0xdf715552313ee0110cbc51ec4e046d1a8ec4711ef5dda9895339ef6975c530d5
POLYMARKET_FUNDER_ADDRESS=0xFDB59729a94377f454ada54e487eEF880dA3313E
SIGNATURE_TYPE=2
PROXY=163.5.176.118:45228:5GEF73OD:SD63124L
```

---

### Шаг 5: Настроить Root Directory

Если код в папке `backend`:
1. Settings → **Root Directory** → введите `backend`
2. Или переименуйте `requirements-railway.txt` в `requirements.txt`

---

### Шаг 6: Деплой

1. Railway автоматически начнет деплой
2. Проверьте логи в разделе **Deployments**
3. Бот должен запуститься и работать 24/7

---

## Проверка работы

После деплоя:
1. Откройте Telegram
2. Отправьте `/start` боту
3. Если бот отвечает — всё работает!

---

## Стоимость

Railway бесплатный tier:
- 500 часов/месяц (достаточно для бота)
- $5 кредитов бесплатно каждый месяц

Бот потребляет ~$2-3/месяц, так что бесплатного tier хватит.

---

## Если что-то не работает

1. Проверьте логи в Railway Dashboard → Deployments → View Logs
2. Убедитесь что все переменные окружения добавлены
3. Проверьте что Root Directory указывает на папку с `telegram_bot.py`
