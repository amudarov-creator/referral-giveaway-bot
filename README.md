# Referral Giveaway Bot

Честный Telegram-бот для реферальных розыгрышей в каналах с:

- персональными invite-ссылками (`createChatInviteLink`);
- атрибуцией только по `ChatMemberUpdated.invite_link` (без угадывания);
- криптографическим commit-reveal розыгрышем;
- объяснимым антифродом и апелляциями;
- append-only аудитом;
- PostgreSQL как единственным источником истины.

## Архитектура

```
Telegram → aiogram handlers → services → SQLAlchemy (PostgreSQL)
                              ↘ Redis (rate limit, FSM)
```

### Состояния конкурса

`draft → scheduled → active → ended → verification → finalized`  
(+ `paused`, `cancelled`)

После перехода в `active` правила, даты и призы считаются замороженными. Любое изменение — только через отмену с записью в audit.

### Реферальная атрибуция

1. Участник запрашивает персональную ссылку → бот вызывает `createChatInviteLink` с уникальным `name`.
2. Бот — администратор канала с правом управлять invite-ссылками и подписан на `chat_member`.
3. При вступлении Telegram присылает `ChatMemberUpdated` с полем `invite_link` **только** если пользователь реально вошёл по этой ссылке.
4. Если `invite_link` отсутствует или неизвестен — реферал **не засчитывается** (никогда не угадываем).
5. Уникальное ограничение `(giveaway_id, invitee_id)` гарантирует ≤ 1 реферал на человека в рамках конкурса.
6. Самоприглашение, повторные вступления, дубликаты update — идемпотентны и не дают лишних билетов.

**Ограничение платформы:** для публичных каналов Telegram иногда не передаёт `invite_link`, если пользователь вошёл через username. В этом случае бот честно не засчитывает реферал. Рекомендуется использовать приватные каналы/группы или требовать вступление строго по ссылке.

### Commit-reveal розыгрыш

1. До фиксации снимка: `seed = secrets.token_hex(32)`, публикуется `SHA-256(seed:giveaway_id)`.
2. После окна проверки: снимок участников + `snapshot_hash`.
3. Раскрытие seed → `weighted_csprng_v1` (HMAC-DRBG + rejection sampling).
4. Публикация seed, snapshot_hash, protocol_hash и списка победителей.
5. Независимая проверка: `DrawService.verify_protocol(...)`.

Используется только CSPRNG-производный поток; `random.random()` и timestamp не применяются.

### Антифрод

Проверяются: саморефералы, burst-вступления, аномальная концентрация, повторная атрибуция.  
**Не** используются: возраст аккаунта как единственный критерий, username/аватар как доказательство, IP, телефоны, CAPTCHA как «доказательство человечности».

Подозрительные случаи → `FraudCase` + статус `suspicious`; билеты не участвуют в розыгрыше до ручного решения.

## Стек

| Компонент | Версия |
|-----------|--------|
| Python | ≥ 3.12 |
| aiogram | ≥ 3.15 |
| SQLAlchemy | ≥ 2.0.36 |
| asyncpg | ≥ 0.30 |
| Alembic | ≥ 1.14 |
| Redis | ≥ 5.2 / Redis 7 |
| PostgreSQL | 16 |

## Быстрый старт

```bash
cp .env.example .env
# Заполните BOT_TOKEN, ADMIN_IDS, пароли

docker compose up -d db redis
docker compose --profile migrate run --rm migrate
docker compose up -d bot
```

Polling по умолчанию. Для webhook:

```env
BOT_MODE=webhook
WEBHOOK_HOST=https://your.domain
WEBHOOK_SECRET=<long-random>
```

Бот должен быть администратором целевого канала с правом **Invite users via link**.

## Команды

**Участник:** `/start`, `/help`, `/rules`, `/mystats`, `/leaderboard`, `/appeal`, кнопка «Get referral link».

**Админ (только `ADMIN_IDS`):**  
`/new_giveaway`, `/set_dates`, `/add_prize`, `/set_rules`, `/activate`, `/end`, `/commit_seed`, `/finalize`, `/cancel`.

Все админ-операции проверяются на сервере независимо от UI.

## Модель угроз (кратко)

| Угроза | Мера |
|--------|------|
| SQL injection | Параметризованные запросы SQLAlchemy |
| Подделка callback | Серверная проверка admin_ids |
| Гонки билетов | Unique constraints + транзакции |
| Повтор update | Идемпотентная обработка + unique (giveaway, invitee) |
| Подмена user_id | Только из Telegram update |
| Webhook spoofing | secret_token |
| Утечка токенов | env only, не логируем |
| Повторный розыгрыш | Idempotent finalize, статус FINALIZED |
| Изменение правил | Freeze после activate + audit |
| Rate abuse | Redis limiter |

Hash-цепочка audit_log выявляет правки, но не защищает от администратора, контролирующего всю инфраструктуру. Публикуйте commitment и результаты во внешнем канале.

## Тесты

```bash
pip install -e ".[dev]"
pytest tests/ -v --tb=short
```

Покрыто: воспроизводимость draw, one-prize invariant, property-based тесты, commitment roundtrip.

Интеграционные тесты с живым Telegram API требуют отдельного тестового бота и канала — в CI по умолчанию не запускаются.

## Данные и retention

Хранятся только: Telegram user id, username/имя (для отображения), факты вступления по ссылке, билеты, audit.  
IP, телефоны, переписки не собираются.  
`DATA_RETENTION_DAYS` — срок хранения после финализации (по умолчанию 365). Экспорт/удаление — через админ-экспорт и обращение пользователя.

## Оставшиеся риски

1. **Публичные каналы** — Telegram может не прислать `invite_link`.
2. **Администратор инфраструктуры** может подменить БД/seed до публикации commitment.
3. **Массовые фейковые аккаунты** — эвристики снижают риск, но не гарантируют 100% detection.
4. **Задержки update** — окно verification mitigates, но не исключает late events.
5. **Seed в БД до reveal** — доступен администратору БД; публикуйте commitment сразу и храните seed в HSM/KMS при повышенных требованиях.

## Чек-лист безопасного запуска

- [ ] Сменить все пароли и `WEBHOOK_SECRET`
- [ ] `ADMIN_IDS` содержит только доверенные Telegram ID
- [ ] Бот — админ канала с минимальными правами (invite links)
- [ ] `allowed_updates` включает `chat_member`
- [ ] HTTPS и secret для webhook
- [ ] Резервное копирование PostgreSQL настроено и проверено restore
- [ ] Правила конкурса опубликованы **до** `/activate`
- [ ] Seed commitment опубликован в канале **до** `/finalize`
- [ ] Health-check и мониторинг логов подключены

## Структура проекта

```
app/
  core/          config, logging
  db/            session, base
  models/        ORM
  services/      referral, draw, fraud, invite_links, audit, crypto
  handlers/      user, admin, chat_member
  middlewares/   db, auth, rate_limit
  main.py
alembic/
tests/
docker-compose.yml
Dockerfile
.env.example
```

## Лицензия

MIT
