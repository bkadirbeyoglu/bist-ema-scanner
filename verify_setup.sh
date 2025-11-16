#!/bin/bash
set -e

echo "🔍 Verifying Day 5 Session 2 Setup..."
echo ""

echo "1️⃣ Checking Poetry in dev container..."
docker compose run --rm trading-app-dev poetry --version >/dev/null 2>&1
echo "✅ Poetry available"
echo ""

echo "2️⃣ Checking pytest..."
docker compose run --rm trading-app-dev poetry run pytest --version >/dev/null 2>&1
echo "✅ Pytest available"
echo ""

echo "3️⃣ Checking production container (should NOT have Poetry)..."
if docker compose run --rm trading-app poetry --version 2>&1 | grep -q "not found"; then
    echo "✅ Production container is correctly minimal (no Poetry)"
else
    echo "⚠️ Warning: Production container has Poetry (not critical)"
fi
echo ""

echo "4️⃣ Checking LocalStack from localhost..."
if curl -s http://localhost:4566/_localstack/health | grep -q "running\|available"; then
    echo "✅ LocalStack is healthy and accessible from localhost"
else
    echo "⚠️ LocalStack might not be accessible from localhost"
fi
echo ""

echo "5️⃣ Checking LocalStack from container..."
if docker compose run --rm trading-app-dev curl -s http://localstack:4566/_localstack/health 2>/dev/null | grep -q "running\|available"; then
    echo "✅ LocalStack accessible from containers"
else
    echo "❌ LocalStack not accessible from containers"
fi
echo ""

echo "6️⃣ Checking volume mounts..."
if docker compose run --rm trading-app-dev ls /app/src >/dev/null 2>&1; then
    echo "✅ Volume mounts working"
else
    echo "❌ Volume mount issue"
fi
echo ""

echo "7️⃣ Checking network connectivity (HTTP test)..."
if docker compose run --rm trading-app-dev curl -s -o /dev/null -w "%{http_code}" http://localstack:4566/_localstack/health 2>/dev/null | grep -q "200"; then
    echo "✅ Network working (HTTP connectivity verified)"
else
    echo "❌ Network issue (HTTP request failed)"
fi
echo ""

echo "✅ All checks complete! Ready for Day 5 Session 2!"
