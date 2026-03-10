#!/usr/bin/env python3
"""
test_setup.py: Simple test to validate the backtesting library setup.
Tests basic functionality without requiring live API access.
"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

def test_imports():
    """Test that all required packages can be imported."""
    print("Testing imports...")
    
    try:
        import pandas as pd
        print("✓ pandas imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import pandas: {e}")
        return False
    
    try:
        import numpy as np
        print("✓ numpy imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import numpy: {e}")
        return False
    
    try:
        import vectorbt as vbt
        print("✓ vectorbt imported successfully")
        print(f"  Version: {vbt.__version__}")
    except ImportError as e:
        print(f"✗ Failed to import vectorbt: {e}")
        return False
    
    try:
        import yaml
        print("✓ yaml imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import yaml: {e}")
        return False
    
    try:
        import clickhouse_connect
        print("✓ clickhouse_connect imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import clickhouse_connect: {e}")
        return False
    
    try:
        import oandapyV20
        print("✓ oandapyV20 imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import oandapyV20: {e}")
        return False
    
    return True


def test_config():
    """Test that config file can be loaded."""
    print("\nTesting configuration...")
    
    try:
        import yaml
        config_path = Path(__file__).parent / "config.yaml"
        
        if not config_path.exists():
            print(f"✗ Config file not found: {config_path}")
            return False
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        print("✓ Config loaded successfully")
        
        # Validate config structure
        required_keys = ["data", "clickhouse", "strategies", "simulation"]
        for key in required_keys:
            if key not in config:
                print(f"✗ Missing required config key: {key}")
                return False
            print(f"  ✓ Found config key: {key}")
        
        # Check strategies
        strategies = config["strategies"]
        expected_strategies = ["trend_following", "scalping", "breakout", "mean_reversion"]
        for strategy in expected_strategies:
            if strategy in strategies and strategies[strategy].get("enabled", False):
                print(f"  ✓ Strategy enabled: {strategy}")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        return False


def test_sql_schema():
    """Test that SQL schema file exists."""
    print("\nTesting SQL schema...")
    
    sql_path = Path(__file__).parent / "scripts" / "create_tables.sql"
    
    if not sql_path.exists():
        print(f"✗ SQL schema file not found: {sql_path}")
        return False
    
    with open(sql_path) as f:
        sql = f.read()
    
    # Check for required tables
    required_tables = ["backtests", "backtest_trades", "backtest_grid_results"]
    for table in required_tables:
        if table in sql:
            print(f"  ✓ Found table definition: {table}")
        else:
            print(f"  ✗ Missing table definition: {table}")
            return False
    
    print("✓ SQL schema is valid")
    return True


def test_vectorbt_basic():
    """Test basic VectorBT functionality."""
    print("\nTesting VectorBT basic functionality...")
    
    try:
        import pandas as pd
        import numpy as np
        import vectorbt as vbt
        
        # Create sample data
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        close = pd.Series(np.random.uniform(100, 110, 100), index=dates, name='close')
        
        # Test MA calculation
        ma = vbt.MA.run(close, window=10)
        print("  ✓ Moving Average calculation works")
        
        # Test RSI calculation
        rsi = vbt.RSI.run(close, window=14)
        print("  ✓ RSI calculation works")
        
        # Test BBANDS calculation
        bb = vbt.BBANDS.run(close, window=20)
        print("  ✓ Bollinger Bands calculation works")
        
        # Test simple portfolio
        entries = close > close.rolling(10).mean()
        exits = close < close.rolling(10).mean()
        pf = vbt.Portfolio.from_signals(close, entries, exits)
        print("  ✓ Portfolio simulation works")
        
        print("✓ VectorBT basic functionality is working")
        return True
        
    except Exception as e:
        print(f"✗ VectorBT test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Forex Backtesting Library - Setup Validation")
    print("=" * 60)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Configuration", test_config()))
    results.append(("SQL Schema", test_sql_schema()))
    results.append(("VectorBT Functionality", test_vectorbt_basic()))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:.<40} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n✓ All tests passed! Setup is ready.")
        return 0
    else:
        print("\n✗ Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
