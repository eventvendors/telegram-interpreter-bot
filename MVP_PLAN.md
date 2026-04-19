# MVP Plan

## Product Goal

Build a public Telegram bot that helps users quickly find interpreters and translators by language pair.

## MVP Scope

Included:
- public Telegram access
- English-only bot interface
- search by service type
- search by language pair
- language selection from Telegram buttons where practical
- fallback to typing if needed
- results shown in pages of 5
- immediate display of contact information
- manual spreadsheet-based data source
- manual priority overrides per language pair

Not included in MVP:
- availability tracking
- direction-sensitive translation logic
- advanced filters
- admin web panel
- payment flow
- user accounts
- analytics dashboard

## Suggested Architecture

### App Layer
- Python Telegram bot using `python-telegram-bot`
- conversation flow with inline keyboard buttons

### Data Layer
- `interpreters.csv` for the main records
- `priority_rules.csv` for search ordering overrides

### Search Layer
- normalize service type
- normalize languages
- match records containing both requested languages
- ignore language order in MVP
- apply pair-specific priority rules first
- then show remaining matches in default order

## Ranking Rules

For MVP, ranking should work like this:

1. Normalize the query pair alphabetically.
   Example:
   - `English + French`
   - `French + English`
   Both become the same search key.

2. Check whether there are any priority rules for that pair and service type.

3. If a rule exists, move matching people to the top in the configured order.

4. Show all other matching people after the prioritized ones.

This supports requests like:
- always put John Jones at the top for `English-French`

## Data Model

### Main Interpreter/Translator Table

Each row should contain:
- `id`
- `full_name`
- `service_type`
- `short_bio`
- `languages`
- `phone`
- `email`
- `telegram_link`
- `whatsapp_link`
- `is_active`

### Priority Rules Table

Each row should contain:
- `id`
- `service_type`
- `language_pair_key`
- `person_id`
- `priority_rank`
- `is_active`

## Search Logic

The MVP matching rule should be:
- exact match on service type
- exact inclusion of both selected languages in the person's language list
- no translation direction handling

Example:
- user selects `Interpreter`
- user selects `English` and `Arabic`
- match any active interpreter whose language list contains both `English` and `Arabic`

## Bot Flow

### Main User Journey

1. `/start`
2. Welcome message
3. Ask: `What do you need?`
   - Interpreter
   - Translator
4. Ask for first language
5. Ask for second language
6. Run search
7. Show page `1`
8. Let user move to:
   - next page
   - previous page
   - page numbers
   - start new search

### Result Card Format

Each result should display:
- full name
- short bio
- languages
- phone
- email
- Telegram link
- WhatsApp link

## Delivery Plan

### Phase 1: Planning and Setup
- create project structure
- define CSV schema
- define search and ranking rules
- prepare sample data

### Phase 2: Working Bot MVP
- implement Telegram bot flow
- load CSV files
- implement search
- implement pagination
- implement priority ranking

### Phase 3: MVP Hardening
- add input validation
- add friendly empty-result messages
- add logging
- add deployment config

## Suggested Repository Structure

```text
telegram-interpreter-bot/
  app/
    bot.py
    config.py
    data_loader.py
    search.py
    keyboards.py
    formatters.py
  data/
    interpreters.csv
    priority_rules.csv
  tests/
    test_search.py
  .env.example
  requirements.txt
  README.md
```

## Suggested Tech Stack

### Strong Recommendation

- Python 3.12
- `python-telegram-bot`
- `pandas`
- `python-dotenv`
- CSV files for MVP storage

### Why Not a Full Database Yet

You said the simplest solution is preferred and the dataset will be manually created.

That makes CSV or spreadsheet-backed storage the best MVP choice because:
- easy to edit
- easy to inspect
- no database administration
- enough for early testing

Later, we can move to:
- SQLite if you want a local lightweight database
- PostgreSQL if the project grows

## Risks and Practical Notes

- Telegram drop-downs are not true drop-down menus, but inline buttons work well.
- If the language list becomes large, typing with validation may become easier than buttons.
- Contact details shown immediately means personal data is visible to all bot users, so consent from listed people matters.
- CSV is fine for MVP, but editing discipline is important because spelling differences can break matching.

## Recommended Next Build Step

Build the bot with:
- fixed service type buttons
- typed language input with normalization
- CSV-based search
- inline pagination buttons

That is the fastest path to a usable first version.
