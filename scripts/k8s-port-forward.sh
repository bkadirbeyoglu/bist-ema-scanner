#!/bin/bash
# k8s-port-forward.sh - Forward all trading system ports
# Usage: ./scripts/k8s-port-forward.sh
# Stop: Ctrl+C

NAMESPACE="trading-system"

echo "🚀 Starting port forwards..."
echo "   Market Data:  http://localhost:8001"
echo "   Order:        http://localhost:8002"
echo "   Notification: http://localhost:8003"
echo ""
echo "Press Ctrl+C to stop."
echo ""

kubectl port-forward -n $NAMESPACE svc/market-data-service 8001:8001 &
PID1=$!
kubectl port-forward -n $NAMESPACE svc/order-service 8002:8002 &
PID2=$!
kubectl port-forward -n $NAMESPACE svc/notification-service 8003:8003 &
PID3=$!

trap "echo ''; echo 'Stopping...'; kill $PID1 $PID2 $PID3 2>/dev/null; exit 0" SIGINT
wait
