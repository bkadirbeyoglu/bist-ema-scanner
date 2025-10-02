#!/usr/bin/env python3
"""
Simple test runner for the trading system.
This is optional - you can also just use pytest directly.
"""

import sys
import json
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest


def run_tests():
    """Run all tests with coverage"""
    args = [
        '-vv',  # Very verbose
        '-s',   # Show print statements
        '--cov=src/trading_system',  # Coverage
        '--cov-report=term-missing',  # Show missed lines
        '--cov-report=html',  # Generate HTML report
        'tests/',  # Test directory
    ]
    return pytest.main(args)


def setup_vs_code_debugging():
    """Create VS Code debug configuration"""
    launch_config = {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "Debug Tests",
                "type": "python",
                "request": "launch",
                "module": "pytest",
                "args": [
                    "tests/",
                    "-vv",
                    "-s"
                ],
                "console": "integratedTerminal",
                "justMyCode": False
            }
        ]
    }
    
    vscode_dir = Path(".vscode")
    vscode_dir.mkdir(exist_ok=True)
    
    launch_file = vscode_dir / "launch.json"
    with open(launch_file, 'w', encoding='utf-8') as f:
        json.dump(launch_config, f, indent=2)
    
    print(f"Created {launch_file}")
    print("To debug: Set breakpoints and press F5 in VS Code")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test runner")
    parser.add_argument('command', choices=['test', 'setup'], 
                       help='test: run tests, setup: create VS Code config')
    
    args = parser.parse_args()
    
    if args.command == 'test':
        exit_code = run_tests()
        sys.exit(exit_code)
    elif args.command == 'setup':
        setup_vs_code_debugging()