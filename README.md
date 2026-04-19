# Interpreter Finder Telegram Bot

This project is a working MVP for a public Telegram bot that helps users quickly find interpreters and translators by language pair.

## What The Bot Does

- asks whether the user needs an `Interpreter` or `Translator`
- asks for two languages
- searches a manually maintained CSV dataset
- ignores language direction in the MVP
- applies manual priority overrides per language pair
- shows results in pages of 5
- displays contact details immediately

## Tech Stack

- Python 3.12
- CSV files for the MVP data source
- Python standard library for Telegram Bot API access and configuration loading

I intentionally kept the runtime dependency-free for this MVP. That makes the project easier to run on this machine and easier to hand over later.

## Project Structure

```text
telegram-interpreter-bot/
  app/
    bot.py
    config.py
    data_loader.py
    formatters.py
    keyboards.py
    search.py
  data/
    interpreters.csv
    priority_rules.csv
  tests/
    test_search.py
  .env.example
  main.py
  MVP_PLAN.md
  README.md
  SPREADSHEET_TEMPLATE.md
  requirements.txt
```

## Local Setup

1. Create a Telegram bot with BotFather and copy the token.
2. In BotFather, set a name and username for the bot.
3. Optional but recommended: set the bot description and about text in BotFather so users understand what the bot does.
4. Create a local env file:

```powershell
Copy-Item .env.example .env
```

5. Put your bot token into `.env`.
6. Start the bot:

```powershell
python main.py
```

Or on this machine, the easiest option is:

```powershell
double-click START BOT.cmd
```

You can also use:

```powershell
.\run_bot.ps1
```

## Railway Deploy

This project is ready for Railway using the included [Dockerfile](/C:/Users/trans/Codex/telegram-interpreter-bot/Dockerfile) and [railway.toml](/C:/Users/trans/Codex/telegram-interpreter-bot/railway.toml).

### What You Need

- a GitHub repository with this project
- a Railway account
- your Telegram bot token

### Fastest Deploy Path

1. Push this project to GitHub.
2. In Railway, click `New Project`.
3. Choose `Deploy from GitHub repo`.
4. Select this repository.
5. Railway should detect the included Dockerfile automatically.
6. Add this environment variable in Railway:
   - `TELEGRAM_BOT_TOKEN`
7. Deploy the service.

### Optional Railway Variables

You usually do not need these because the defaults already point to the local CSV files in the repo, but you can set them explicitly if you want:

- `INTERPRETERS_CSV=data/interpreters.csv`
- `PRIORITY_RULES_CSV=data/priority_rules.csv`

### Railway Notes

- This bot is a long-running worker, so Railway should run it as a normal service.
- No web port is required for this bot.
- If you update the CSV files in GitHub and redeploy, the bot will use the new data.
- If you change only the Railway environment variables, Railway can restart the service without code changes.

## Data Maintenance

- Edit `data/interpreters.csv` to add or update interpreters and translators.
- Edit `data/priority_rules.csv` to force certain people to appear first for a specific service type and language pair.
- Keep language names spelled consistently.

## Bot Commands

- `/start` starts a new search
- `/search` starts a new search
- `/languages` shows the current supported languages from the CSV file
- `/about` explains the bot
- `/cancel` stops the current search

## Tests

Run:

```powershell
python -m unittest discover -s tests
```

## Notes

- Telegram does not support true drop-down menus, so this MVP uses button keyboards where practical and also accepts typed language input.
- The bot reloads the CSV files on each search, so data edits can be picked up without restarting the code.
- Typed languages are validated against the current CSV dataset so spelling mistakes do not silently return bad results.
- The bot currently uses Telegram long polling through the raw Bot API, which keeps deployment simple for the MVP.

See [MVP_PLAN.md](/C:/Users/trans/Codex/telegram-interpreter-bot/MVP_PLAN.md) for the delivery plan and [SPREADSHEET_TEMPLATE.md](/C:/Users/trans/Codex/telegram-interpreter-bot/SPREADSHEET_TEMPLATE.md) for the manual data format.
