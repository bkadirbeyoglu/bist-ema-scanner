# ============================================
# ENVIRONMENT-SPECIFIC COMMANDS
# ============================================

dev:  ## Start development environment
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

dev-build:  ## Rebuild and start development
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

dev-logs:  ## View development logs
	docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

dev-down:  ## Stop development environment
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

test:  ## Run tests in test environment
	docker compose -f docker-compose.yml -f docker-compose.test.yml up --abort-on-container-exit
	docker compose -f docker-compose.yml -f docker-compose.test.yml down -v

test-build:  ## Rebuild and run tests
	docker compose -f docker-compose.yml -f docker-compose.test.yml build
	docker compose -f docker-compose.yml -f docker-compose.test.yml up --abort-on-container-exit
	docker compose -f docker-compose.yml -f docker-compose.test.yml down -v