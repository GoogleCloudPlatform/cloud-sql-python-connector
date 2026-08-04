# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import os
import time

try:
    import psutil
except ImportError:
    psutil = None

import pytest

from google.cloud.sql.connector import Connector

# These will be set from environment variables or default to our test instance
INSTANCE_CONNECTION_NAME = os.getenv(
    "DB_CONNECTION_NAME", "galakp-playground:us-east7:pg-us-east7-psycopg"
)
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "SuperPass123!")
DB_NAME = os.getenv("DB_NAME", "postgres")


@pytest.mark.skipif(psutil is None, reason="psutil package is not installed")
def test_system_psycopg_resource_leak() -> None:
    """Benchmark test to verify no resource leaks (threads, FDs, memory) between iteration 20 and 100."""
    print("\nStarting resource leak benchmark...")
    
    process = psutil.Process(os.getpid())
    
    def get_metrics():
        return {
            "threads": process.num_threads(),
            "fds": process.num_fds(),
            "rss_mb": process.memory_info().rss / (1024 * 1024),
        }

    warmup_iterations = 20
    total_iterations = 100
    
    baseline_metrics = None
    active_final_metrics = None
    
    with Connector() as connector:
        for i in range(1, total_iterations + 1):
            conn = connector.connect(
                INSTANCE_CONNECTION_NAME,
                "psycopg",
                user=DB_USER,
                password=DB_PASSWORD,
                db=DB_NAME,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            cursor.fetchone()
            cursor.close()
            conn.close()
            
            if i == warmup_iterations:
                time.sleep(0.5)
                baseline_metrics = get_metrics()
                print(f"Baseline Metrics (Iteration {i}): {baseline_metrics}")
                
            if i == total_iterations:
                time.sleep(0.5)
                active_final_metrics = get_metrics()
                print(f"Active Final Metrics (Iteration {i}): {active_final_metrics}")
                
            if i % 10 == 0 and warmup_iterations < i < total_iterations:
                current_metrics = get_metrics()
                print(f"Iteration {i:3d}/{total_iterations}: {current_metrics}")
                
    # Post-close metrics
    time.sleep(1)
    post_close_metrics = get_metrics()
    print(f"Post-Close Metrics: {post_close_metrics}")
    
    assert baseline_metrics is not None
    assert active_final_metrics is not None
    
    # Assertions: compare Active Final (100) vs Baseline (20)
    # Threads should not grow
    assert active_final_metrics["threads"] <= baseline_metrics["threads"] + 1, f"Thread leak: {baseline_metrics} -> {active_final_metrics}"
    # FDs should not grow
    assert active_final_metrics["fds"] <= baseline_metrics["fds"] + 1, f"FD leak: {baseline_metrics} -> {active_final_metrics}"
    # Memory growth should be minimal (allow < 5MB growth for minor fragmentation)
    assert active_final_metrics["rss_mb"] <= baseline_metrics["rss_mb"] + 5, f"Memory leak: {baseline_metrics} -> {active_final_metrics}"
    
    print("Resource leak benchmark passed successfully.")


def test_system_psycopg_basic() -> None:
    """Basic system test to verify connection and query."""
    print(f"\nConnecting to {INSTANCE_CONNECTION_NAME}...")
    with Connector() as connector:
        conn = connector.connect(
            INSTANCE_CONNECTION_NAME,
            "psycopg",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        result = cursor.fetchone()
        print(f"Database version: {result[0]}")
        assert result is not None
        cursor.close()
        conn.close()
    print("Connection closed successfully.")





def test_system_psycopg_to_thread() -> None:
    """Verify that running sync connect in asyncio.to_thread works."""
    print(f"\nConnecting via asyncio.to_thread to {INSTANCE_CONNECTION_NAME}...")

    async def run_connect():
        with Connector() as connector:
            # Run the blocking connector.connect in a thread
            conn = await asyncio.to_thread(
                connector.connect,
                INSTANCE_CONNECTION_NAME,
                "psycopg",
                user=DB_USER,
                password=DB_PASSWORD,
                db=DB_NAME,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            result = cursor.fetchone()
            print(f"Database version (to_thread): {result[0]}")
            assert result is not None
            cursor.close()
            conn.close()

    asyncio.run(run_connect())
    print("to_thread connection closed successfully.")
