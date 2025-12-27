#!/bin/bash
# k8s-debug.sh - Quick debugging overview
# Usage: ./scripts/k8s-debug.sh [namespace]

NAMESPACE="${1:-trading-system}"

echo "=================================="
echo "K8s Debug: $NAMESPACE"
echo "=================================="

echo ""
echo "📦 Pods:"
kubectl get pods -n $NAMESPACE -o wide

echo ""
echo "🔌 Services:"
kubectl get services -n $NAMESPACE

echo ""
echo "📊 Endpoints:"
kubectl get endpoints -n $NAMESPACE

echo ""
echo "📋 Recent Events:"
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -10

echo ""
echo "💾 Resource Usage:"
kubectl top pods -n $NAMESPACE 2>/dev/null || echo "(metrics-server starting...)"

echo ""
echo "=================================="
echo "Commands:"
echo "  kubectl logs <pod> -n $NAMESPACE"
echo "  kubectl exec -it <pod> -n $NAMESPACE -- sh"
echo "  kubectl describe pod <pod> -n $NAMESPACE"
echo "=================================="
