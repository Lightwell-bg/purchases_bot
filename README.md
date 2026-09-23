# Group Buys — Telegram Bot

An MVP bot for organizing group purchases inside a regular Telegram group.
A user creates a purchase listing through a dialog in a private chat, the bot
publishes it in the group under its own name, others join via a button, and
the bot automatically recalculates totals and updates the listing.

The bot is purely a coordination tool for participants. It **does not accept
payments**, does not place orders, and does not provide any legal advice on
customs matters.

> Русская версия: [README_RU.md](README_RU.md). The bot's own interface text
> is Russian-only (see [Known MVP limitations](#18-known-mvp-limitations)) —
> this README describes the project in English for contributors.

---

## Table of contents

1. [What the project does](#1-what-the-project-does)
2. [Architecture](#2-architecture)
3. [Requirements](#3-requirements)
4. [Creating a bot via BotFather](#4-creating-a-bot-via-botfather)
5. [Finding MAIN_GROUP_ID](#5-finding-main_group_id)
6. [Adding the bot to a group](#6-adding-the-bot-to-a-group)
7. [Bot permissions](#7-bot-permissions)
8. [Privacy Mode](#8-privacy-mode)
9. [.env configuration](#9-env-configuration)
10. [Local run](#10-local-run)
11. [Docker](#11-docker)
12. [Migrations](#12-migrations)
13. [Logs](#13-logs)
14. [Updating](#14-updating)
15. [SQLite backup](#15-sqlite-backup)
16. [SQLite restore](#16-sqlite-restore)
17. [Core user scenarios](#17-core-user-scenarios)
18. [Known MVP limitations](#18-known-mvp-limitations)

---

## 1. What the project does

- A user starts creating a purchase from the group — via the button in the
  pinned message or the `/buy` command.
- Before creation, the bot shows the rules and requires explicit consent.
- A step-by-step dialog collects the product data: title, link, photo, price,
  currency, allowed variants, organizer's own quantity, deadline, pickup
  location, comment.
- The organizer sees a preview and publishes the listing to the group.
- The listing has a "Join" button leading to the bot's private chat via a
  deep link.
- Anyone joining also accepts the rules, then specifies quantity and variant.
- The bot tallies participants, units, total cost, and an **estimated**
  customs duty, updating the listing after every change.
- The organizer sees the participant list, can edit the purchase, and closes
  the collection when done.
- Total product cost is capped by a configurable limit (€150 by default).

**One purchase = one product or one product category.** Variants (color,
size, length, model) are allowed; mixing unrelated products in one purchase
is not.

### What the bot calculates

| Metric | Formula |
|--------|---------|
| Total units | `organizer_quantity + Σ quantity of active participants` |
| Total cost | `unit_price × total units` |
| Estimated customs duty | `CUSTOMS_FLAT_FEE_EUR` (flat fee) |
| Estimated duty per unit | `CUSTOMS_FLAT_FEE_EUR / total units` |

All amounts are computed with `Decimal`. These figures are informational
only: the actual number of shipments and customs line items depends on the
seller, marketplace, carrier, and customs clearance process.

## 2. Architecture

```
src/
├── main.py                  entry point: migrations, polling, background task
├── bot.py                   Bot and Dispatcher assembly
├── config.py                .env + settings.ini
├── logging_setup.py
├── database/
│   ├── db.py                engine and session factory
│   ├── models.py            User, Purchase, Participant, RulesAcceptance
│   ├── types.py             Money (Decimal) and TZDateTime
│   └── repositories/        users, purchases, participants, rules
├── handlers/                start, group, rules, create_purchase,
│                            join_purchase, participation, manage_purchase,
│                            my_purchases, admin, errors, fallback
├── keyboards/               inline keyboards and CallbackData factories
├── middlewares/             DB session, user registration
├── services/                calculations, availability, purchase_service,
│                            rules_service, telegram_service, deadline_checker
├── states/                  FSM states
├── texts/                   ru.py and rules.md
└── utils/                   parsing, formatting
```

Details — in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
user flows — in [docs/USER_FLOW.md](docs/USER_FLOW.md).

**Stack:** Python 3.12+, aiogram 3, SQLAlchemy 2, SQLite, Alembic,
pydantic-settings, Docker. Long polling, no webhook.

## 3. Requirements

- Python 3.12 or newer (tested on 3.12 in Docker and 3.14 locally)
- or Docker and Docker Compose
- a Telegram account with admin rights in the target group

## 4. Creating a bot via BotFather

1. Open [@BotFather](https://t.me/BotFather) in Telegram.
2. `/newbot` → enter a display name → enter a username (must end with `bot`,
   e.g. `common_buy_bg_bot`).
3. BotFather sends a token like `1234567890:AAF...`. This is a **secret** —
   it only goes into `.env`, never into git.
4. Save the bot's username (without `@`) as `BOT_USERNAME` — needed for deep
   links.
5. Optional but useful:
   - `/setdescription` — bot description;
   - `/setcommands` — command list, e.g.:

     ```
     start - Main menu
     buy - Create a group purchase
     active - Active purchases
     my - My purchases
     cancel - Cancel the current dialog
     ```

   This is optional: the bot registers its own command list on every start
   (`setup_bot_commands` in `src/bot.py`) — separately for private chats and
   groups.

Documentation: <https://core.telegram.org/bots/features#botfather>

## 5. Finding MAIN_GROUP_ID

Three options, pick any.

**Option 1 — via a bot command (easiest).** Add the bot to the group, put
your own Telegram ID into `ADMIN_TELEGRAM_IDS`, start the bot, and send
`/chatid` in the group. The bot replies with the chat ID.

**Option 2 — via getUpdates.** Send any message to the bot in the group
(e.g. `/buy`), then open in a browser:

```
https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
```

Look for `"chat":{"id":-1001234567890,...}`.

**Option 3 — via a third-party bot** such as
[@getmyid_bot](https://t.me/getmyid_bot): add it to the group, it shows the
ID.

A supergroup ID is negative and starts with `-100`. Your own Telegram ID for
`ADMIN_TELEGRAM_IDS` can be found via [@userinfobot](https://t.me/userinfobot).

## 6. Adding the bot to a group

1. Open the group → "Members" → "Add member" → find the bot by username.
2. Make the bot an admin (see the next section).
3. Send `/setup` in the group (from an account listed in
   `ADMIN_TELEGRAM_IDS`) — the bot publishes an invitation message with a
   "➕ Create a group purchase" button.
4. Pin that message in the group.

From then on, new members discover the bot four ways:

- **the "➕ Create your own purchase" button on every listing** — the most
  visible entry point: it's right there where the person is already looking
  at someone else's purchase;
- **an automatic welcome message** — when someone joins the group, the bot
  sends a short message with a "create purchase" button (it self-deletes
  after `group_cleanup_seconds × 10` from `settings.ini`, so it doesn't pile
  up in the feed);
- **the pinned message** from `/setup` — always there;
- **the `/help` command** in the group — a short how-to with the same button.

Commands are visible in the blue "Menu" button next to the input field: the
bot registers them on every start, separately for private chats and groups.

## 7. Bot permissions

Minimum required group admin permissions:

| Permission | Why |
|------------|-----|
| Send messages | publishing listings |
| Edit messages | updating the listing as new participants join |
| Pin messages | optional, if you pin via the bot |
| Delete messages | auto-cleanup of commands/replies from the feed, replacing the listing when a photo is added |

Ban rights, group profile editing, and invite-link permissions are **not
needed** — don't grant them.

## 8. Privacy Mode

The bot is designed to run with Privacy Mode **enabled** (the default state).
With it on, the bot only receives in a group:

- commands addressed to it;
- taps on inline buttons under its own messages;
- its own messages;
- deep-link openings and private messages.

The bot never receives or analyzes regular member chatter. There's no need
to disable Privacy Mode — the whole design assumes it stays on.

Check it: `/mybots` → select the bot → *Bot Settings* → *Group Privacy* →
should say `Enabled`.

**A caveat about admin bots.** Telegram delivers *all* chat messages to a
bot if the bot itself is a group administrator — the Privacy Mode setting
has no effect in that case. The bot already needs admin rights to edit and
delete listings (see section 7), so this is unavoidable. This does **not**
mean the bot starts reading and analyzing chatter: the code handles exactly
one specific case (an exact text match on the persistent reply-keyboard
button "📋 Active purchases", see `src/handlers/group.py`) — everything else
is still ignored.

## 9. .env configuration

Copy the template and fill in the values:

```bash
cp .env.example .env        # Linux/macOS
copy .env.example .env      # Windows
```

| Variable | Required | Description |
|----------|----------|--------------|
| `BOT_TOKEN` | yes | token from BotFather |
| `BOT_USERNAME` | yes | bot username without `@`, needed for deep links |
| `MAIN_GROUP_ID` | yes | ID of the group to publish to, e.g. `-1001234567890` |
| `ADMIN_TELEGRAM_IDS` | no | admin Telegram IDs, comma-separated |
| `DATABASE_URL` | no | defaults to `sqlite+aiosqlite:///./data/bot.db` |
| `RUN_MIGRATIONS_ON_START` | no | `true` — run `alembic upgrade head` on startup |
| `RULES_VERSION` | no | rules version; bumping it invalidates all prior consents |
| `BUSINESS_SETTINGS_FILE` | no | path to the business-parameters ini file |
| `TIMEZONE` | no | timezone for displayed dates, defaults to `Europe/Sofia` |
| `DEADLINE_CHECK_INTERVAL_SECONDS` | no | deadline check interval, defaults to 300 |
| `LOG_LEVEL` | no | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FILE` | no | path to the log file |

**Business parameters live separately, in `settings.ini`** — not secrets,
this file can stay in git and be edited without rebuilding the image:

```ini
[business]
customs_flat_fee_eur = 3
purchase_limit_eur = 150

[limits]
max_items_per_participant = 100
max_deadline_days = 365

[group]
group_cleanup_seconds = 90
```

> `.env` is never committed (it's in `.gitignore`) and doesn't arrive with a
> code update. If you add a variable, add it to `.env.example` right away —
> otherwise it silently goes missing on the next server deployment. Check
> for drift (output should be empty):
>
> ```bash
> diff <(sed -E 's/=.*/=<V>/' .env) <(sed -E 's/=.*/=<V>/' .env.example)
> ```

## 10. Local run

```bash
python -m venv .venv
```

Windows:

```bash
source .venv/Scripts/activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
cp .env.example .env          # and fill in the values
alembic upgrade head
python -m src.main
```

You don't have to run migrations manually: with `RUN_MIGRATIONS_ON_START=true`
the app runs them itself on startup.

Tests:

```bash
pytest
```

## 11. Docker

```bash
docker compose build
docker compose up -d
```

Logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

The database lives in `./data`, logs in `./logs` — both directories are
mounted into the container, so data survives rebuilds. `settings.ini` is
mounted too — business-parameter edits take effect after
`docker compose restart`, no rebuild needed.

The container restarts automatically (`restart: unless-stopped`).

## 12. Migrations

Create a migration after changing the models:

```bash
alembic revision --autogenerate -m "description of the change"
```

Apply:

```bash
alembic upgrade head
```

Roll back one step:

```bash
alembic downgrade -1
```

Check that models and schema match:

```bash
alembic check
```

Current revision:

```bash
alembic current
```

In Docker: `docker compose exec bot alembic upgrade head`.

SQLite doesn't fully support `ALTER TABLE`, so `migrations/env.py` enables
`render_as_batch=True` — Alembic recreates tables automatically as needed.

## 13. Logs

Written simultaneously to stdout (visible via `docker compose logs`) and to
`logs/bot.log` with rotation (5 MB, 3 files).

Logged: application start/stop, user Telegram ID, purchase creation and
publishing, joining, editing, leaving, closing, Telegram API and DB errors.
`BOT_TOKEN` and the contents of `.env` are never logged.

Level is set via `LOG_LEVEL`. For debugging:

```bash
LOG_LEVEL=DEBUG python -m src.main
```

## 14. Updating

```bash
git pull
docker compose build
docker compose up -d
docker compose logs -f
```

Locally:

```bash
git pull
pip install -r requirements.txt
alembic upgrade head
python -m src.main
```

After updating, check `.env` against `.env.example` — new variables may have
been added in the code.

## 15. SQLite backup

```bash
mkdir -p backups
cp data/bot.db backups/bot-$(date +%F-%H%M).db
```

More correct — using SQLite's own tooling, which is safe under concurrent
writes:

```bash
sqlite3 data/bot.db ".backup 'backups/bot-$(date +%F-%H%M).db'"
```

In Docker:

```bash
docker compose exec bot cp /app/data/bot.db /app/data/bot-backup.db
mv data/bot-backup.db backups/bot-$(date +%F-%H%M).db
```

`backups/` is in `.gitignore`. For regular backups, one cron line is enough:

```
0 3 * * * cd /opt/purchases_bot && cp data/bot.db backups/bot-$(date +\%F).db
```

## 16. SQLite restore

```bash
docker compose down
cp backups/bot-2026-08-27-0300.db data/bot.db
docker compose up -d
docker compose logs -f
```

Locally — the same, except instead of `docker compose` you stop and start
`python -m src.main`. Before restoring, save the current file:
`cp data/bot.db data/bot.db.broken`.

## 17. Core user scenarios

1. **Creation.** Group → button or `/buy` → rules → 10-step wizard →
   preview → publish to the group.
2. **Joining.** Listing → "🛒 Join" → rules → quantity, variant, comment →
   confirmation. The group listing updates.
3. **Editing a request.** "📦 My purchases" → your purchase → "✏️ Edit".
   Available while the collection is still open.
4. **Leaving.** Same screen → "❌ Leave" with confirmation.
5. **Management.** Organizer: participants, field edits, closing the
   collection, cancelling the purchase.
6. **Closing.** "🔒 Close collection" → confirmation → the listing is marked
   "COLLECTION CLOSED", the join button disappears, participants are
   notified.
7. **Auto-closing.** Expired purchases are closed by a background task.
8. **Browsing active purchases.** "📋 Active purchases" in the private-chat
   main menu, the `/active` command, or the same button on the persistent
   group keyboard — a paginated list of all open purchases with an "Open"
   link on each.
9. **Administration.** Users listed in `ADMIN_TELEGRAM_IDS` get two extra
   buttons in the private-chat main menu: "📊 Statistics" and "🗂 All
   purchases". Statistics show counts for every purchase status plus the
   user count. "All purchases" is a paginated list of every purchase (except
   drafts) with a button into that purchase's management panel — even if
   the admin isn't the organizer: full field editing, closing, and
   cancelling are all available there, exactly like the organizer's own
   view. The `/stats` and `/purchases` commands still work as before,
   independently of the menu buttons.

Detailed flow diagrams — in [docs/USER_FLOW.md](docs/USER_FLOW.md).

## 18. Known MVP limitations

**Functional**

- No payments, balances, or fees — participants settle up directly with the
  organizer outside the bot.
- One purchase = one product. No mixed-cart support for unrelated products.
- Customs duty is a flat fee per purchase. The bot doesn't know and doesn't
  attempt to guess the real number of shipments or customs line items.
- The `purchase_limit_eur` limit is defined in euros but applied to the
  purchase's own currency total without conversion — the bot has no
  exchange-rate source. For non-EUR purchases this is an approximate bound.
- Currency can't be changed after publishing — otherwise totals would drift
  out of sync.
- One bot instance serves one group (`MAIN_GROUP_ID`).
- **The interface is Russian-only** — all bot-facing text lives in
  `src/texts/ru.py`; there is no i18n layer.
- The `ORDERED`, `SHIPPED`, `RECEIVED`, `COMPLETED` statuses exist in the
  data model but aren't used in the UI yet.

**Technical**

- FSM state is kept in memory: an unfinished draft is lost on restart.
  Purchases and requests already saved to the database are unaffected.
- SQLite, single process — fine up to a few thousand purchases; beyond that,
  PostgreSQL would be needed.
- Long polling, no webhook.
- Photos are stored as Telegram `file_id`s; if the user deletes the original
  message containing the photo, the `file_id` may stop working.
- Broadcast notifications are sent sequentially with a 50 ms pause between
  each — on very large purchases, notifications won't arrive instantly.
- The "Open listing in the group" link is only generated for supergroups
  (ID starting with `-100`).
- Telegram bots have no "private" messages in a group: any reply from the
  bot is visible to everyone. That's why routine chatter (commands and
  replies to them) is auto-deleted after `group_cleanup_seconds`
  (`settings.ini`). This requires the "Delete messages" permission — without
  it, those messages simply stay in the feed.
- Product links are capped at 2048 characters.
- If a group listing is deleted manually, the bot stops updating it and
  reports this in the organizer panel.
