#!/bin/bash
# =============================================================================
# LocalStack initialization script for Notification Service
# 
# This script:
# 1. Creates the notifications SQS queue
# 2. Subscribes it to the order-events SNS topic (created in Day 11)
# 3. Sets up the filter policy to receive only order events
#
# Run this after LocalStack is healthy and Day 11's SNS topic exists.
# =============================================================================

set -e  # Exit on error

LOCALSTACK_URL="${AWS_ENDPOINT_URL:-http://localhost:4566}"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"  # LocalStack default

echo "🔧 Setting up Notification Service AWS resources..."
echo "   LocalStack URL: $LOCALSTACK_URL"
echo "   Region: $REGION"

# -----------------------------------------------------------------------------
# Step 1: Create the notifications SQS queue
# -----------------------------------------------------------------------------
echo ""
echo "📬 Creating SQS queue: notifications..."

aws --endpoint-url="$LOCALSTACK_URL" --region="$REGION" \
    sqs create-queue \
    --queue-name notifications \
    --attributes '{
        "VisibilityTimeout": "30",
        "MessageRetentionPeriod": "86400",
        "ReceiveMessageWaitTimeSeconds": "20"
    }' \
    2>/dev/null || echo "   Queue may already exist, continuing..."

QUEUE_URL=$(aws --endpoint-url="$LOCALSTACK_URL" --region="$REGION" \
    sqs get-queue-url --queue-name notifications --query 'QueueUrl' --output text)

QUEUE_ARN="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:notifications"

echo "   Queue URL: $QUEUE_URL"
echo "   Queue ARN: $QUEUE_ARN"

# -----------------------------------------------------------------------------
# Step 2: Get the SNS topic ARN (created in Day 11)
# -----------------------------------------------------------------------------
echo ""
echo "🔍 Looking for SNS topic: order-events..."

TOPIC_ARN="arn:aws:sns:${REGION}:${ACCOUNT_ID}:order-events"

# Check if topic exists
if aws --endpoint-url="$LOCALSTACK_URL" --region="$REGION" \
    sns get-topic-attributes --topic-arn "$TOPIC_ARN" >/dev/null 2>&1; then
    echo "   Found topic: $TOPIC_ARN"
else
    echo "   ⚠️  Topic not found. Creating it..."
    aws --endpoint-url="$LOCALSTACK_URL" --region="$REGION" \
        sns create-topic --name order-events
    echo "   Created topic: $TOPIC_ARN"
fi

# -----------------------------------------------------------------------------
# Step 3: Set queue policy to allow SNS to send messages
# -----------------------------------------------------------------------------
echo ""
echo "🔐 Setting queue policy for SNS access..."

POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "sns.amazonaws.com"},
      "Action": "sqs:SendMessage",
      "Resource": "$QUEUE_ARN",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "$TOPIC_ARN"
        }
      }
    }
  ]
}
EOF
)

aws --endpoint-url="$LOCALSTACK_URL" --region="$REGION" \
    sqs set-queue-attributes \
    --queue-url "$QUEUE_URL" \
    --attributes "{\"Policy\": $(echo "$POLICY" | jq -c '.' | jq -R)}"

echo "   Policy set successfully"

# -----------------------------------------------------------------------------
# Step 4: Subscribe queue to SNS topic with filter policy
# -----------------------------------------------------------------------------
echo ""
echo "📡 Subscribing queue to SNS topic..."

# Filter policy: only receive order-related events
FILTER_POLICY='{"event_type": ["OrderCreatedEvent", "OrderFilledEvent", "OrderCancelledEvent", "OrderRejectedEvent"]}'

SUBSCRIPTION_ARN=$(aws --endpoint-url="$LOCALSTACK_URL" --region="$REGION" \
    sns subscribe \
    --topic-arn "$TOPIC_ARN" \
    --protocol sqs \
    --notification-endpoint "$QUEUE_ARN" \
    --attributes "{\"FilterPolicy\": $(echo "$FILTER_POLICY" | jq -c '.' | jq -R), \"RawMessageDelivery\": \"false\"}" \
    --query 'SubscriptionArn' --output text)

echo "   Subscription ARN: $SUBSCRIPTION_ARN"

# -----------------------------------------------------------------------------
# Step 5: Verify setup
# -----------------------------------------------------------------------------
echo ""
echo "✅ Verification:"

echo "   Queues:"
aws --endpoint-url="$LOCALSTACK_URL" --region="$REGION" \
    sqs list-queues --query 'QueueUrls' --output table

echo ""
echo "   SNS Subscriptions:"
aws --endpoint-url="$LOCALSTACK_URL" --region="$REGION" \
    sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" \
    --query 'Subscriptions[*].[Protocol,Endpoint]' --output table

echo ""
echo "🎉 Notification Service AWS resources ready!"
echo ""
echo "To test, publish a message to the SNS topic:"
echo "  aws --endpoint-url=$LOCALSTACK_URL sns publish \\"
echo "    --topic-arn $TOPIC_ARN \\"
echo "    --message '{\"event_type\":\"OrderFilledEvent\",\"order_id\":\"test\"}' \\"
echo "    --message-attributes '{\"event_type\":{\"DataType\":\"String\",\"StringValue\":\"OrderFilledEvent\"}}'"