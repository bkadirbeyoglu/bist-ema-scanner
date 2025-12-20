#!/bin/bash
# =============================================================================
# LocalStack Initialization Script
# Creates SQS queue for trading signals
# =============================================================================

set -e

echo "🚀 Initializing LocalStack resources..."

# Create the trading signals queue
awslocal sqs create-queue \
    --queue-name trading-signals \
    --attributes '{
        "VisibilityTimeout": "30",
        "MessageRetentionPeriod": "86400"
    }'

echo "✅ Created queue: trading-signals"

# List queues to verify
echo "📋 Available queues:"
awslocal sqs list-queues

echo "✅ LocalStack initialization complete!"