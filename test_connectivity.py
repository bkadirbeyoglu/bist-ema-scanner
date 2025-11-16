#!/usr/bin/env python3
"""Test network connectivity to other services."""
import socket
import sys

def test_dns_resolution(hostname):
    """Test if a hostname can be resolved to an IP address."""
    try:
        ip_address = socket.gethostbyname(hostname)
        print(f"✓ DNS: {hostname} resolves to {ip_address}")
        return True
    except socket.gaierror as e:
        print(f"✗ DNS: {hostname} resolution failed: {e}")
        return False

def test_port_connectivity(hostname, port):
    """Test if a service port is reachable."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((hostname, port))
        sock.close()
        
        if result == 0:
            print(f"✓ TCP: {hostname}:{port} is reachable")
            return True
        else:
            print(f"✗ TCP: {hostname}:{port} is NOT reachable (error code: {result})")
            return False
    except Exception as e:
        print(f"✗ TCP: Error connecting to {hostname}:{port}: {e}")
        return False

def main():
    """Run all connectivity tests."""
    print("=" * 60)
    print("Docker Network Connectivity Test")
    print("=" * 60)
    print()
    
    # Services to test: (hostname, port, description)
    services = [
        ("postgres", 5432, "PostgreSQL Database"),
        ("redis", 6379, "Redis Cache"),
        ("localstack", 4566, "LocalStack AWS Emulator"),
    ]
    
    all_passed = True
    
    for hostname, port, description in services:
        print(f"Testing {description} ({hostname}:{port})...")
        dns_ok = test_dns_resolution(hostname)
        if dns_ok:
            port_ok = test_port_connectivity(hostname, port)
            all_passed = all_passed and port_ok
        else:
            all_passed = False
        print()
    
    print("=" * 60)
    if all_passed:
        print("✓ All connectivity tests PASSED")
        sys.exit(0)
    else:
        print("✗ Some connectivity tests FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
