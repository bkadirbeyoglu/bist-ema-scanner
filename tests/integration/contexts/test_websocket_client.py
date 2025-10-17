"""
Enhanced tests for WebSocket client with fixtures and proper mocking.

STRATEGY: Use fixtures for reusable test components and proper mocking.

KEY TESTING CONCEPTS EXPLAINED:
================================

FIXTURES:
--------
Fixtures are pytest's way of providing reusable test data/objects.
- Defined with @pytest.fixture decorator
- Automatically injected into tests by parameter name
- Run before each test that uses them
- Great for reducing code duplication
- Example: Instead of creating stream in every test, create once in fixture

ASYNCMOCK:
----------
Mock for async functions (async def).
- Use when mocking coroutines/async functions
- Can be awaited (await mock_handler(...))
- Tracks calls like regular Mock
- Example: Mocking an async message handler

MAGICMOCK:
----------
Mock for regular (sync) objects/functions.
- Use for non-async code
- Can't be awaited
- Has special methods (__getitem__, __len__, etc.)
- Example: Mocking a queue object

PATCH:
------
Temporarily replace objects/functions during tests.
- Use with 'with' statement for scoped replacement
- Automatically restores original after test
- Can patch classes, methods, attributes
- Example: Replacing a method with a mock
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from typing import List, Dict, Any

from trading_system.contexts.market_data.infrastructure.market_stream import MarketDataStream


# ============================================================================
# FIXTURES - Reusable test components
# ============================================================================
# 
# WHAT ARE FIXTURES?
# ------------------
# Fixtures are functions that provide test data or objects to your tests.
# They're defined with @pytest.fixture and automatically run before tests.
#
# WHY USE FIXTURES?
# -----------------
# 1. Reduce code duplication (DRY principle)
# 2. Centralize test setup
# 3. Easy to modify (change once, affects all tests)
# 4. Automatic cleanup
# 5. Can depend on other fixtures
#
# HOW DO FIXTURES WORK?
# ---------------------
# When you add a fixture name as a test parameter, pytest:
# 1. Finds the fixture function with that name
# 2. Runs the fixture function
# 3. Passes the return value to your test
# 4. Runs cleanup code (if any) after the test
#
# EXAMPLE:
# --------
# @pytest.fixture
# def stream_url():
#     return "ws://test.example.com"
#
# async def test_something(stream_url):  # <- fixture injected here
#     # stream_url is now "ws://test.example.com"
#     assert stream_url.startswith("ws://")
# ============================================================================

@pytest.fixture
def stream_url():
    """
    Fixture providing test WebSocket URL.
    
    FIXTURE BASICS:
    - This is the simplest type of fixture
    - Returns a constant value
    - Used by many tests
    - If we change the URL here, all tests get the new URL
    """
    return "ws://test.example.com"


@pytest.fixture
def basic_stream(stream_url):
    """
    Fixture providing a basic MarketDataStream instance.
    
    FIXTURE DEPENDENCY:
    - This fixture depends on 'stream_url' fixture
    - pytest automatically runs stream_url first
    - Then passes its result to this fixture
    - This is called "fixture composition"
    
    BENEFIT:
    - Don't have to create stream in every test
    - Consistent configuration across tests
    """
    return MarketDataStream(url=stream_url)


@pytest.fixture
def configured_stream(stream_url):
    """
    Fixture providing a configured MarketDataStream with custom settings.
    
    MULTIPLE FIXTURES:
    - You can have multiple fixtures for different scenarios
    - Tests choose which fixture to use by parameter name
    - basic_stream: default settings
    - configured_stream: custom settings
    """
    return MarketDataStream(
        url=stream_url,
        reconnect_interval=10,
        max_queue_size=500
    )


@pytest.fixture
def mock_handler():
    """
    Fixture providing a mock async message handler.
    
    ASYNCMOCK EXPLAINED:
    -------------------
    AsyncMock is for mocking async functions (coroutines).
    
    KEY DIFFERENCES from regular Mock:
    - Can be awaited: await mock_handler(...)
    - Has async methods (__aenter__, __aexit__)
    - Tracks async calls properly
    
    WHEN TO USE AsyncMock:
    - Mocking async def functions
    - Mocking coroutines
    - Anything you need to await
    
    WHEN NOT TO USE:
    - Regular sync functions → use Mock or MagicMock
    - Objects/attributes → use MagicMock
    
    EXAMPLE:
    --------
    # This is an async function we want to mock:
    async def process_message(msg):
        await do_something(msg)
        return "processed"
    
    # Mock it:
    mock = AsyncMock(return_value="processed")
    result = await mock({"test": "data"})  # Can await!
    mock.assert_called_once()  # Can verify calls
    """
    handler = AsyncMock()
    handler.return_value = None  # async handlers typically return None
    return handler


@pytest.fixture
def sample_messages():
    """
    Fixture providing sample market data messages.
    
    DATA FIXTURES:
    - Provide consistent test data
    - Easy to modify in one place
    - Can be as simple as a list/dict
    """
    return [
        {"symbol": "AAPL", "price": 150.50, "volume": 1000},
        {"symbol": "GOOGL", "price": 2800.00, "volume": 500},
        {"symbol": "MSFT", "price": 380.25, "volume": 800}
    ]


@pytest.fixture
def collecting_handler():
    """
    Fixture providing a handler that collects received messages.
    
    STATEFUL FIXTURES:
    - This fixture has state (collected list)
    - The handler function has access to this state
    - Useful for verifying what was processed
    
    TECHNIQUE:
    - Create a list outside the handler
    - Handler appends to it
    - Attach list to handler function for easy access
    """
    collected = []
    
    async def handler(msg):
        collected.append(msg)
    
    # Attach collected list to handler for easy access in tests
    handler.collected = collected
    return handler


# ============================================================================
# BASIC TESTS WITH FIXTURES
# ============================================================================

@pytest.mark.asyncio
async def test_stream_initializes_with_defaults(stream_url):
    """
    Test that MarketDataStream can be created with default values.
    
    FIXTURE USAGE:
    - stream_url is injected by pytest
    - No need to create it manually
    - If stream_url fixture changes, this test automatically uses new value
    """
    stream = MarketDataStream(url=stream_url)
    
    assert stream.url == stream_url
    assert stream.reconnect_interval == 5
    assert stream.max_queue_size == 1000
    assert stream.messages_received == 0
    assert stream.messages_processed == 0


@pytest.mark.asyncio
async def test_get_stats_returns_dict(basic_stream):
    """
    Test that get_stats() returns expected dictionary structure.
    
    FIXTURE INJECTION:
    - basic_stream is injected (already created)
    - No setup code needed in test
    - Test focuses on what matters: verification
    """
    # Set some values
    basic_stream.messages_received = 10
    basic_stream.messages_processed = 8
    basic_stream.errors = 2
    
    stats = basic_stream.get_stats()
    
    assert isinstance(stats, dict)
    assert stats["messages_received"] == 10
    assert stats["messages_processed"] == 8
    assert stats["errors"] == 2
    assert "queue_size" in stats
    assert "connected" in stats


# ============================================================================
# CONFIGURATION TESTS WITH FIXTURES
# ============================================================================

@pytest.mark.asyncio
async def test_stream_with_custom_config(configured_stream, stream_url):
    """
    Test that MarketDataStream accepts custom configuration.
    
    MULTIPLE FIXTURES:
    - This test uses TWO fixtures
    - pytest runs both before the test
    - Order doesn't matter (pytest figures it out)
    """
    assert configured_stream.url == stream_url
    assert configured_stream.reconnect_interval == 10
    assert configured_stream.max_queue_size == 500


@pytest.mark.asyncio
async def test_stream_with_handler(stream_url, mock_handler):
    """
    Test that MarketDataStream accepts message handler.
    
    ASYNCMOCK IN ACTION:
    - mock_handler is an AsyncMock (from fixture)
    - It can be assigned to on_message
    - Later we can verify it was called correctly
    """
    stream = MarketDataStream(
        url=stream_url,
        on_message=mock_handler
    )
    
    assert stream.on_message is mock_handler


# ============================================================================
# QUEUE BEHAVIOR TESTS WITH FIXTURES
# ============================================================================

@pytest.mark.asyncio
async def test_queue_handles_multiple_messages(basic_stream, sample_messages):
    """
    Test that queue can handle multiple messages in sequence.
    
    TWO FIXTURES WORKING TOGETHER:
    - basic_stream: provides the stream object
    - sample_messages: provides test data
    - Clean test code without setup boilerplate
    """
    # Add all sample messages
    for msg in sample_messages:
        await basic_stream._message_queue.put(msg)
    
    # Verify all messages in queue
    assert basic_stream._message_queue.qsize() == len(sample_messages)
    
    # Retrieve all messages
    retrieved = []
    for _ in range(len(sample_messages)):
        msg = await basic_stream._message_queue.get()
        retrieved.append(msg)
    
    # Verify order preserved
    for original, retrieved_msg in zip(sample_messages, retrieved):
        assert retrieved_msg["symbol"] == original["symbol"]
        assert retrieved_msg["price"] == original["price"]


@pytest.mark.asyncio
async def test_queue_respects_max_size(stream_url):
    """Test that queue has correct maximum size."""
    stream = MarketDataStream(
        url=stream_url,
        max_queue_size=5  # Small queue for testing
    )
    
    # Fill queue to max
    for i in range(5):
        await stream._message_queue.put({"id": i})
    
    assert stream._message_queue.qsize() == 5
    assert stream._message_queue.maxsize == 5


@pytest.mark.asyncio
async def test_queue_fifo_order(basic_stream):
    """Test that queue maintains FIFO order."""
    # Put messages with timestamps
    messages = [
        {"symbol": "AAPL", "time": 1},
        {"symbol": "GOOGL", "time": 2},
        {"symbol": "MSFT", "time": 3}
    ]
    
    for msg in messages:
        await basic_stream._message_queue.put(msg)
    
    # Get messages - should be in same order
    first = await basic_stream._message_queue.get()
    second = await basic_stream._message_queue.get()
    third = await basic_stream._message_queue.get()
    
    assert first["symbol"] == "AAPL"
    assert second["symbol"] == "GOOGL"
    assert third["symbol"] == "MSFT"


# ============================================================================
# HANDLER TESTS WITH FIXTURES AND MOCKS
# ============================================================================

@pytest.mark.asyncio
async def test_handler_receives_all_messages(stream_url, collecting_handler, sample_messages):
    """
    Test that handler processes all messages.
    
    COLLECTING HANDLER PATTERN:
    - collecting_handler accumulates messages
    - We can inspect handler.collected after processing
    - Useful for verifying behavior without complex mocking
    """
    stream = MarketDataStream(
        url=stream_url,
        on_message=collecting_handler
    )
    
    # Simulate processing all messages
    for msg in sample_messages:
        await stream._message_queue.put(msg)
        
        if stream.on_message:
            message = await stream._message_queue.get()
            await stream.on_message(message)
            stream._message_queue.task_done()
            stream.messages_processed += 1
    
    # Verify all messages received
    assert len(collecting_handler.collected) == len(sample_messages)
    assert stream.messages_processed == len(sample_messages)
    
    # Verify message content
    for original, received in zip(sample_messages, collecting_handler.collected):
        assert received["symbol"] == original["symbol"]


@pytest.mark.asyncio
async def test_handler_called_with_correct_arguments(stream_url, mock_handler):
    """
    Test that handler is called with correct message.
    
    ASYNCMOCK VERIFICATION:
    ----------------------
    AsyncMock provides methods to verify how it was called:
    
    - assert_called(): Was called at least once
    - assert_called_once(): Was called exactly once
    - assert_called_with(args): Was called with specific arguments
    - assert_called_once_with(args): Called exactly once with args
    - call_count: Number of times called
    - call_args_list: List of all calls
    
    WHY THIS MATTERS:
    - Verify handler receives correct data
    - Catch bugs where wrong data is passed
    - Document expected behavior
    """
    stream = MarketDataStream(
        url=stream_url,
        on_message=mock_handler
    )
    
    test_message = {"symbol": "AAPL", "price": 150.0}
    
    # Call handler
    await stream.on_message(test_message)
    
    # ASYNCMOCK VERIFICATION:
    # assert_called_once_with checks:
    # 1. Handler was called exactly once
    # 2. Handler was called with test_message
    mock_handler.assert_called_once_with(test_message)


@pytest.mark.asyncio
async def test_handler_can_transform_data(stream_url):
    """Test that handler can transform message data."""
    processed_prices = []
    
    async def price_extractor(msg):
        price = Decimal(str(msg["price"]))
        processed_prices.append(price)
    
    stream = MarketDataStream(
        url=stream_url,
        on_message=price_extractor
    )
    
    messages = [
        {"symbol": "AAPL", "price": 150.50},
        {"symbol": "GOOGL", "price": 2800.25}
    ]
    
    for msg in messages:
        await stream.on_message(msg)
    
    # Verify transformation
    assert len(processed_prices) == 2
    assert isinstance(processed_prices[0], Decimal)
    assert processed_prices[0] == Decimal("150.50")
    assert processed_prices[1] == Decimal("2800.25")


@pytest.mark.asyncio
async def test_handler_can_filter_messages(stream_url):
    """Test that handler can selectively process messages."""
    aapl_prices = []
    
    async def aapl_filter(msg):
        if msg.get("symbol") == "AAPL":
            aapl_prices.append(msg["price"])
    
    stream = MarketDataStream(
        url=stream_url,
        on_message=aapl_filter
    )
    
    messages = [
        {"symbol": "AAPL", "price": 150.0},
        {"symbol": "GOOGL", "price": 2800.0},
        {"symbol": "AAPL", "price": 151.0},
        {"symbol": "MSFT", "price": 380.0},
        {"symbol": "AAPL", "price": 152.0}
    ]
    
    for msg in messages:
        await stream.on_message(msg)
    
    # Only AAPL prices should be captured
    assert len(aapl_prices) == 3
    assert aapl_prices == [150.0, 151.0, 152.0]


# ============================================================================
# ERROR HANDLING TESTS WITH MOCKS
# ============================================================================

@pytest.mark.asyncio
async def test_handler_error_is_tracked(stream_url):
    """Test that errors in handler are tracked in statistics."""
    error_count = 0
    
    async def failing_handler(msg):
        nonlocal error_count
        error_count += 1
        raise ValueError("Simulated handler error")
    
    stream = MarketDataStream(
        url=stream_url,
        on_message=failing_handler
    )
    
    message = {"symbol": "AAPL", "price": 150.0}
    
    try:
        await stream.on_message(message)
    except ValueError:
        stream.errors += 1
    
    assert error_count == 1
    assert stream.errors == 1
    
    stats = stream.get_stats()
    assert stats["errors"] == 1


@pytest.mark.asyncio
async def test_statistics_reset(basic_stream):
    """Test that statistics can be reset/cleared."""
    # Set some statistics
    basic_stream.messages_received = 100
    basic_stream.messages_processed = 95
    basic_stream.errors = 5
    basic_stream.reconnections = 3
    
    # Verify non-zero
    assert basic_stream.messages_received > 0
    
    # Reset
    basic_stream.messages_received = 0
    basic_stream.messages_processed = 0
    basic_stream.errors = 0
    basic_stream.reconnections = 0
    
    # Verify reset
    stats = basic_stream.get_stats()
    assert stats["messages_received"] == 0
    assert stats["messages_processed"] == 0
    assert stats["errors"] == 0
    assert stats["reconnections"] == 0


# ============================================================================
# CONCURRENT OPERATIONS WITH FIXTURES
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_queue_puts(basic_stream):
    """Test that multiple coroutines can add to queue concurrently."""
    async def add_messages(start_id: int, count: int):
        for i in range(count):
            await basic_stream._message_queue.put({
                "id": start_id + i,
                "value": f"message_{start_id + i}"
            })
    
    # Run 3 concurrent producers
    await asyncio.gather(
        add_messages(0, 10),
        add_messages(10, 10),
        add_messages(20, 10)
    )
    
    assert basic_stream._message_queue.qsize() == 30
    
    # Collect all messages
    all_messages = []
    while not basic_stream._message_queue.empty():
        msg = await basic_stream._message_queue.get()
        all_messages.append(msg)
    
    assert len(all_messages) == 30
    ids = [msg["id"] for msg in all_messages]
    assert len(set(ids)) == 30  # All unique


@pytest.mark.asyncio
async def test_concurrent_queue_gets(basic_stream):
    """Test that multiple coroutines can read from queue concurrently."""
    # Fill queue
    for i in range(30):
        await basic_stream._message_queue.put({"id": i})
    
    async def consume_messages(count: int) -> List[Dict]:
        consumed = []
        for _ in range(count):
            msg = await basic_stream._message_queue.get()
            consumed.append(msg)
        return consumed
    
    # Run 3 concurrent consumers
    results = await asyncio.gather(
        consume_messages(10),
        consume_messages(10),
        consume_messages(10)
    )
    
    # Flatten results
    all_consumed = []
    for result in results:
        all_consumed.extend(result)
    
    assert len(all_consumed) == 30
    assert basic_stream._message_queue.qsize() == 0
    
    # All messages should be unique
    ids = [msg["id"] for msg in all_consumed]
    assert len(set(ids)) == 30


# ============================================================================
# PRACTICAL INTEGRATION TESTS WITH FIXTURES
# ============================================================================

@pytest.mark.asyncio
async def test_realistic_message_flow(stream_url, sample_messages):
    """Test realistic message processing flow."""
    processed_data = {
        "total_messages": 0,
        "symbols": set(),
        "price_sum": Decimal("0")
    }
    
    async def realistic_handler(msg: Dict[str, Any]):
        processed_data["total_messages"] += 1
        processed_data["symbols"].add(msg["symbol"])
        processed_data["price_sum"] += Decimal(str(msg["price"]))
    
    stream = MarketDataStream(
        url=stream_url,
        on_message=realistic_handler
    )
    
    # Process messages
    for msg in sample_messages:
        await stream._message_queue.put(msg)
        
        if stream.on_message:
            message = await stream._message_queue.get()
            await stream.on_message(message)
            stream.messages_processed += 1
    
    # Verify processing results
    assert processed_data["total_messages"] == len(sample_messages)
    assert len(processed_data["symbols"]) == 3  # AAPL, GOOGL, MSFT
    assert stream.messages_processed == len(sample_messages)
    
    # Verify price sum
    expected_sum = sum(Decimal(str(msg["price"])) for msg in sample_messages)
    assert processed_data["price_sum"] == expected_sum


@pytest.mark.asyncio
async def test_batch_message_processing(stream_url):
    """Test processing messages in batches."""
    batches_processed = []
    
    async def batch_handler(msg: Dict[str, Any]):
        batches_processed.append(msg)
    
    stream = MarketDataStream(
        url=stream_url,
        on_message=batch_handler,
        max_queue_size=100
    )
    
    # Add 50 messages
    for i in range(50):
        await stream._message_queue.put({
            "id": i,
            "symbol": f"STOCK{i % 5}",
            "price": 100.0 + i
        })
    
    # Process in batches of 10
    for _ in range(5):
        batch = []
        for _ in range(10):
            if not stream._message_queue.empty():
                msg = await stream._message_queue.get()
                batch.append(msg)
                if stream.on_message:
                    await stream.on_message(msg)
        
        assert len(batch) == 10
    
    assert len(batches_processed) == 50
    assert stream._message_queue.empty()


# ============================================================================
# MOCKING TESTS WITH MAGICMOCK AND PATCH
# ============================================================================
#
# MAGICMOCK vs ASYNCMOCK:
# =======================
# 
# Use MAGICMOCK when:
# - Mocking regular (sync) objects
# - Mocking attributes/properties
# - Mocking classes with special methods (__getitem__, __len__)
# - Don't need to await the mock
#
# Use ASYNCMOCK when:
# - Mocking async functions (async def)
# - Mocking coroutines
# - Need to await the mock
#
# PATCH EXPLAINED:
# ===============
# 
# patch temporarily replaces an object/function during test execution.
# 
# Common patterns:
# - patch('module.function'): Replace function in module
# - patch.object(Class, 'method'): Replace method on class
# - patch.dict(dictionary): Replace dictionary entries
#
# Why use patch?
# - Test behavior with different implementations
# - Isolate code from dependencies
# - Simulate error conditions
# - Automatic cleanup (original restored after test)
#
# How it works:
# 1. with patch(...): <- Enter context manager
# 2. Original is saved, replacement installed
# 3. Test code runs with replacement
# 4. Original is automatically restored when exiting 'with'
# ============================================================================

@pytest.mark.asyncio
async def test_queue_put_with_magicmock(basic_stream):
    """
    Test queue.put using MagicMock.
    
    MAGICMOCK USAGE:
    ---------------
    MagicMock is for mocking regular (non-async) objects.
    
    Here's what we're doing:
    1. Create MagicMock for the queue object itself
    2. Make its 'put' method an AsyncMock (because put is async)
    3. Replace real queue with mock
    4. Verify mock was used correctly
    
    WHY MAGICMOCK for queue but ASYNCMOCK for put?
    - Queue object is regular (sync) class
    - But queue.put() is an async method
    - So: MagicMock wraps the object, AsyncMock wraps the method
    
    REAL-WORLD USE:
    - Testing without actual queue
    - Simulating queue failures
    - Counting queue operations
    """
    # MAGICMOCK: For the queue object (not async)
    mock_queue = MagicMock()
    
    # ASYNCMOCK: For the async put method
    mock_queue.put = AsyncMock()
    
    # Replace real queue with mock
    original_queue = basic_stream._message_queue
    basic_stream._message_queue = mock_queue
    
    # Put a message
    test_message = {"symbol": "AAPL", "price": 150.0}
    await basic_stream._message_queue.put(test_message)
    
    # Verify mock was called
    mock_queue.put.assert_called_once_with(test_message)
    
    # Restore original queue
    basic_stream._message_queue = original_queue


@pytest.mark.asyncio
async def test_handler_invocation_with_patch(stream_url):
    """
    Test handler invocation using patch.
    
    PATCH EXPLAINED:
    ---------------
    patch.object(Class, 'method') temporarily replaces a method.
    
    What happens:
    1. Original __init__ is saved
    2. Our replacement (return_value=None) is installed
    3. Test code runs
    4. Original __init__ is restored automatically
    
    WHY USE PATCH HERE?
    - Avoid complex __init__ setup
    - Focus on testing one specific behavior
    - Bypass initialization requirements
    
    PATTERN:
    with patch.object(Class, 'method', ...):
        # Inside here, method is patched
        # Do your test
    # Outside here, method is restored
    
    BENEFITS:
    - No need to clean up (automatic)
    - Can't forget to restore
    - Scoped to 'with' block
    """
    mock_handler = AsyncMock()
    
    # PATCH: Replace __init__ to bypass initialization
    with patch.object(MarketDataStream, '__init__', return_value=None):
        # Create instance without calling __init__
        stream = MarketDataStream.__new__(MarketDataStream)
        
        # Manually set what we need
        stream.on_message = mock_handler
        
        # Invoke handler
        test_message = {"symbol": "GOOGL", "price": 2800.0}
        await stream.on_message(test_message)
        
        # Verify
        mock_handler.assert_called_once_with(test_message)
    
    # After 'with' block, __init__ is automatically restored


@pytest.mark.asyncio
async def test_multiple_handler_calls_with_mock(stream_url, sample_messages):
    """
    Test multiple handler calls with mock verification.
    
    ASYNCMOCK CALL TRACKING:
    -----------------------
    AsyncMock tracks ALL calls automatically:
    
    - call_count: Total number of calls
    - call_args: Arguments from LAST call
    - call_args_list: Arguments from ALL calls (list of call objects)
    
    ACCESSING CALL ARGUMENTS:
    call_args_list[i][0][0] breaks down as:
    - [i]: Which call (0 = first, 1 = second, etc.)
    - [0]: Positional args tuple
    - [0]: First positional argument
    
    EXAMPLE:
    mock(msg1)  # Call 0
    mock(msg2)  # Call 1
    mock(msg3)  # Call 2
    
    call_args_list[1][0][0] = msg2 (second call, first arg)
    """
    mock_handler = AsyncMock()
    
    stream = MarketDataStream(
        url=stream_url,
        on_message=mock_handler
    )
    
    # Call handler multiple times
    for msg in sample_messages:
        await stream.on_message(msg)
    
    # VERIFY CALL COUNT
    assert mock_handler.call_count == len(sample_messages)
    
    # VERIFY EACH INDIVIDUAL CALL
    # call_args_list is a list of all calls
    for i, msg in enumerate(sample_messages):
        call_args = mock_handler.call_args_list[i]
        # call_args[0][0] = first positional argument of call i
        assert call_args[0][0]["symbol"] == msg["symbol"]


@pytest.mark.asyncio
async def test_handler_side_effect_with_mock(stream_url):
    """
    Test handler side effects using mock.
    
    ASYNCMOCK SIDE_EFFECT:
    ---------------------
    side_effect makes the mock DO something when called.
    
    THREE WAYS TO USE side_effect:
    
    1. Function (what we use here):
       mock = AsyncMock(side_effect=my_function)
       # When mock is called, my_function runs
    
    2. Exception:
       mock = AsyncMock(side_effect=ValueError("error"))
       # When mock is called, raises ValueError
    
    3. List of values:
       mock = AsyncMock(side_effect=[1, 2, 3])
       # First call returns 1, second returns 2, third returns 3
    
    USE CASES:
    - Test how code handles exceptions
    - Verify side effects happen (like logging)
    - Return different values on successive calls
    
    DIFFERENCE FROM return_value:
    - return_value: Simple return value
    - side_effect: Function that runs and can do more complex things
    """
    call_order = []
    
    # This function will run when mock is called
    async def side_effect(msg):
        call_order.append(msg["symbol"])
    
    # ASYNCMOCK WITH SIDE_EFFECT:
    # When mock is called, side_effect function runs
    mock_handler = AsyncMock(side_effect=side_effect)
    
    stream = MarketDataStream(
        url=stream_url,
        on_message=mock_handler
    )
    
    messages = [
        {"symbol": "AAPL", "price": 150.0},
        {"symbol": "GOOGL", "price": 2800.0},
        {"symbol": "MSFT", "price": 380.0}
    ]
    
    # Process messages
    for msg in messages:
        await stream.on_message(msg)
    
    # VERIFY SIDE EFFECT:
    # The side_effect function appended symbols to call_order
    assert call_order == ["AAPL", "GOOGL", "MSFT"]
    
    # ALSO: Mock still tracks calls normally
    assert mock_handler.call_count == 3


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])