# WhatsApp Chatbot for Equipment Rental

Pre-screening chatbot for in9 Equipamentos. Built with Groq API for AI conversation and WhatsApp Cloud API to send and receive messages.

## Features

- Real-time attendance via WhatsApp Cloud API.
- Catalog validation using AI function calling.
- Screening of event type, location, schedule, guest count and equipment.
- Order logging to `pedidos.json`.
- Rate limiting of 20 messages per client per hour.
- Session reset after 30 minutes of inactivity.
- HMAC signature validation from Meta.
- Duplicate message processing protection.

## Requirements

- Python 3.11 or higher.
- A Groq API key.
- A configured app on Meta for Developers with WhatsApp Cloud API.
- A public HTTPS URL for the webhook.

## Environment Variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key |
| `META_VERIFY_TOKEN` | Webhook verification token |
| `META_APP_SECRET` | App secret for HMAC validation |
| `META_ACCESS_TOKEN` | WhatsApp Cloud API access token |
| `META_PHONE_NUMBER_ID` | Phone number ID on Meta for Developers |

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env` with your real credentials. Never publish the `.env` file.

## Project Structure
├── ia2_app.py — main application
├── pedidos.json — logged orders (ignored by Git)
├── .env — credentials (ignored by Git)
├── .env.example — credentials template
├── .gitignore — ignored files
└── requirements.txt — project dependencies


## Running the API

The main file has a dot in its name (`ia2.0.py`), which doesn't work well as a Uvicorn module. Rename it to `ia2_app.py` and run:

```bash
uvicorn ia2_app:app --host 0.0.0.0 --port 8000
```

## Configuring the Meta Webhook

In the Meta for Developers dashboard, set:

- Callback URL: `https://your-domain.com/webhook`
- Verify token: same value as `META_VERIFY_TOKEN`.
- Subscribed field: `messages`.

Meta sends the `X-Hub-Signature-256` header. The app validates it using `META_APP_SECRET` before processing any message.

## Notes

Conversation history and rate limiting are stored in memory. For multiple instances or restarts without losing sessions, replace these dictionaries with Redis or a database.

The `pedidos.json` file is ignored by Git as it may contain personal client data.