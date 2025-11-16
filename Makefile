# ============================================================
# DEVELOPMENT COMMANDS
# ============================================================

.PHONY: dev dev-down dev-restart dev-logs dev-shell

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

dev-down:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

dev-restart: dev-down dev

dev-logs:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

dev-shell:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm trading-app bash

# ============================================================
# TESTING COMMANDS
# ============================================================

.PHONY: test test-unit test-integration test-sqs test-file

# Remove the old 'test' target (line 18) and keep only this one:
test:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm trading-app poetry run pytest $(ARGS)

test-unit:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm trading-app poetry run pytest tests/unit/ -v

test-sqs:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml exec trading-app poetry run pytest tests/integration/aws/test_sqs_event_bus.py -v -s

.PHONY: test-integration
test-integration:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml exec trading-app poetry run pytest tests/integration/ -v

test-file:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm trading-app poetry run pytest $(FILE) -v -s

# ============================================================
# BUILD COMMANDS
# ============================================================

.PHONY: build build-dev build-prod

build:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml build

build-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml build trading-app

build-prod:
	docker compose -f docker-compose.yml build trading-app