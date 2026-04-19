# Spreadsheet Template

## Sheet 1: `interpreters`

Use one row per person.

| Column | Required | Example | Notes |
|---|---|---|---|
| `id` | yes | `1` | Stable unique ID |
| `full_name` | yes | `John Jones` | Person's display name |
| `service_type` | yes | `Interpreter` | Must be `Interpreter` or `Translator` |
| `short_bio` | yes | `Court and business interpreter with 8 years of experience.` | Keep this brief |
| `languages` | yes | `English, French, Arabic` | Comma-separated list |
| `phone` | no | `+971500000000` | Displayed to users |
| `email` | no | `john@example.com` | Displayed to users |
| `telegram_link` | no | `https://t.me/johnjones` | Full link preferred |
| `whatsapp_link` | no | `https://wa.me/971500000000` | Full link preferred |
| `is_active` | yes | `true` | Only active rows should appear |

## Sheet 2: `priority_rules`

Use one row per priority override.

| Column | Required | Example | Notes |
|---|---|---|---|
| `id` | yes | `1` | Stable unique ID |
| `service_type` | yes | `Interpreter` | Match the user search type |
| `language_pair_key` | yes | `Arabic|English` | Alphabetically normalized |
| `person_id` | yes | `1` | Links to `interpreters.id` |
| `priority_rank` | yes | `1` | Lower number means higher rank |
| `is_active` | yes | `true` | Turn rules on or off easily |

## Normalization Rules

To keep the MVP simple:
- store language names consistently
- use the same spelling everywhere
- sort the two searched languages alphabetically to make the pair key

Examples:
- `English` + `Arabic` becomes `Arabic|English`
- `French` + `English` becomes `English|French`

## Example

### `interpreters`

| id | full_name | service_type | short_bio | languages | phone | email | telegram_link | whatsapp_link | is_active |
|---|---|---|---|---|---|---|---|---|---|
| 1 | John Jones | Interpreter | Conference interpreter for English and French. | English, French | +971500000001 | john@example.com | https://t.me/johnjones | https://wa.me/971500000001 | true |
| 2 | Sara Ali | Translator | Legal translator working in Arabic and English. | Arabic, English | +971500000002 | sara@example.com | https://t.me/saraali | https://wa.me/971500000002 | true |

### `priority_rules`

| id | service_type | language_pair_key | person_id | priority_rank | is_active |
|---|---|---|---|---|---|
| 1 | Interpreter | English|French | 1 | 1 | true |

## Recommended Maintenance Process

1. Keep the spreadsheet as the master source.
2. Export to CSV when updating the bot data.
3. Validate spelling of languages before upload.
4. Keep `id` values stable even if rows are edited.
