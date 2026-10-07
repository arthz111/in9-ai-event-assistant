# WhatsApp Chatbot for Equipment Rental

Pre-screening chatbot for in9 Equipamentos. Built with Groq API for AI conversation and WhatsApp Cloud API to send and receive messages.

## Features

- Real-time attendance via WhatsApp Cloud API.
- Catalog validation using AI function calling.
- Screening of event type, location, schedule, guest count and equipment.
- Order persistence in PostgreSQL.
- Redis-backed conversation history and rate limiting of 20 messages per client per hour.
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
├── docker-compose.yml — PostgreSQL and API services
├── Dockerfile — API image
├── .env — credentials (ignored by Git)
├── .env.example — credentials template
├── .gitignore — ignored files
└── requirements.txt — project dependencies


## Running the API

Run the API locally with:

```bash
uvicorn ia2_app:app --host 0.0.0.0 --port 8000
```

## Running with Docker

Make sure `.env` contains the Meta and Groq credentials, then start the API and PostgreSQL:

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`. PostgreSQL data is stored in the
`postgres_data` Docker volume and orders are saved in the `orders` table.

## Configuring the Meta Webhook

In the Meta for Developers dashboard, set:

- Callback URL: `https://your-domain.com/webhook`
- Verify token: same value as `META_VERIFY_TOKEN`.
- Subscribed field: `messages`.

Meta sends the `X-Hub-Signature-256` header. The app validates it using `META_APP_SECRET` before processing any message.

## Configuring Evolution API

Set these variables in `.env`:

```env
EVOLUTION_API_URL=http://host.docker.internal:8080
EVOLUTION_API_KEY=your_evolution_api_key
EVOLUTION_INSTANCE=your_instance_name
```

In Evolution API, configure the webhook URL as
`http://host.docker.internal:8000/evolution-webhook` for a local Docker setup.
Enable the `MESSAGES_UPSERT` event. The application sends replies through
`/message/sendText/{instance}`.

Set `SALES_PHONE_NUMBER` in `.env` with the seller's WhatsApp number in international
format, without `+`, spaces or punctuation. When the five triage details are collected,
the order is saved in PostgreSQL and a summary is sent to this number.

## Notes

Conversation history and rate limiting are stored in Redis. Orders are stored in PostgreSQL.
Both services are started automatically by Docker Compose.