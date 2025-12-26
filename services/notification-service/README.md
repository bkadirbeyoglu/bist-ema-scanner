# Notification Service

Third microservice in the algorithmic trading system. Consumes order events via SNS/SQS fan-out and generates notifications across multiple channels.

## Architecture

    Order Service → SNS (order-events) → SQS (notifications) → Notification Service
                                                                        │
                                                        ┌───────────────┼───────────────┐
                                                        ▼               ▼               ▼
                                                      Email          Slack           SMS

## Quick Start

    # 1. Start LocalStack (from project root)
    docker compose up -d localstack
    
    # 2. Initialize AWS resources
    ./init-aws.sh
    
    # 3. Install dependencies
    poetry install
    
    # 4. Run tests & start service
    poetry run pytest
    poetry run python demo.py

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/notifications` | List all notifications |
| GET | `/notifications/{id}` | Get specific notification |
| GET | `/notifications/stats` | Notification statistics |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `NOTIFICATION_SERVICE_AWS_ENDPOINT_URL` | `http://localhost:4566` | LocalStack URL |
| `NOTIFICATION_SERVICE_CONSUMER_ENABLED` | `true` | Enable SQS consumer |