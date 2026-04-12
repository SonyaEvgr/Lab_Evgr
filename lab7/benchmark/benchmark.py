import os
import csv
import time
import uuid
import random
import threading
import requests
import numpy as np

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
REQUESTS_PER_THREAD = 20
THREAD_COUNTS = [1, 5, 10, 50]
RESULTS_DIR = "/app/results"


def wait_for_service():
    for _ in range(60):
        try:
            r = requests.get(f"{BASE_URL}/cars", timeout=5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("Service not available")


def seed_data():
    """Create some initial cars for read/write tests."""
    created_ids = []
    for i in range(20):
        plate = f"BENCH{i:04d}"
        vin = f"BENCH{uuid.uuid4().hex[:12].upper()}"
        r = requests.post(f"{BASE_URL}/cars", json={
            "brand": "TestBrand",
            "model": "TestModel",
            "year": 2023,
            "license_plate": plate,
            "vin": vin[:17],
        }, timeout=10)
        if r.status_code == 201:
            created_ids.append(r.json()["id"])
    return created_ids


def scenario_read(thread_id, results, n):
    times = []
    for _ in range(n):
        start = time.perf_counter()
        try:
            requests.get(f"{BASE_URL}/cars", timeout=30)
        except Exception:
            pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    results[thread_id] = times


def scenario_write(thread_id, results, n):
    times = []
    for i in range(n):
        plate = f"W{thread_id}_{i}_{uuid.uuid4().hex[:6]}"
        vin = f"W{uuid.uuid4().hex[:15].upper()}"
        start = time.perf_counter()
        try:
            if i % 2 == 0:
                requests.post(f"{BASE_URL}/cars", json={
                    "brand": "BenchWrite",
                    "model": "Model",
                    "year": 2024,
                    "license_plate": plate,
                    "vin": vin[:17],
                }, timeout=30)
            else:
                # Try to update a random car from the list
                r = requests.get(f"{BASE_URL}/cars", timeout=30)
                if r.status_code == 200:
                    cars = r.json()
                    if cars:
                        car = random.choice(cars)
                        requests.put(f"{BASE_URL}/cars/{car['id']}", json={
                            "brand": "Updated",
                        }, timeout=30)
        except Exception:
            pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    results[thread_id] = times


def scenario_mixed(thread_id, results, n):
    times = []
    for i in range(n):
        start = time.perf_counter()
        try:
            if i % 2 == 0:
                requests.get(f"{BASE_URL}/cars", timeout=30)
            else:
                plate = f"M{thread_id}_{i}_{uuid.uuid4().hex[:6]}"
                vin = f"M{uuid.uuid4().hex[:15].upper()}"
                requests.post(f"{BASE_URL}/cars", json={
                    "brand": "BenchMixed",
                    "model": "Model",
                    "year": 2024,
                    "license_plate": plate,
                    "vin": vin[:17],
                }, timeout=30)
        except Exception:
            pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    results[thread_id] = times


def scenario_write_report(thread_id, results, n):
    times = []
    for i in range(n):
        start = time.perf_counter()
        try:
            if i % 2 == 0:
                plate = f"R{thread_id}_{i}_{uuid.uuid4().hex[:6]}"
                vin = f"R{uuid.uuid4().hex[:15].upper()}"
                requests.post(f"{BASE_URL}/cars", json={
                    "brand": "BenchReport",
                    "model": "Model",
                    "year": 2024,
                    "license_plate": plate,
                    "vin": vin[:17],
                }, timeout=60)
            else:
                requests.get(f"{BASE_URL}/report", timeout=60)
        except Exception:
            pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    results[thread_id] = times


SCENARIOS = {
    "read_only": scenario_read,
    "write_only": scenario_write,
    "mixed_read_write": scenario_mixed,
    "write_and_report": scenario_write_report,
}


def run_scenario(name, func, num_threads, requests_per_thread):
    results = {}
    threads = []
    total_start = time.perf_counter()
    for t in range(num_threads):
        th = threading.Thread(target=func, args=(t, results, requests_per_thread))
        threads.append(th)
        th.start()
    for th in threads:
        th.join()
    total_time = time.perf_counter() - total_start

    all_times = []
    for times in results.values():
        all_times.extend(times)

    all_times_ms = [t * 1000 for t in all_times]
    total_requests = len(all_times)
    avg_ms = np.mean(all_times_ms) if all_times_ms else 0
    std_ms = np.std(all_times_ms) if all_times_ms else 0
    p95_ms = np.percentile(all_times_ms, 95) if all_times_ms else 0

    return {
        "scenario": name,
        "threads": num_threads,
        "total_requests": total_requests,
        "total_time_sec": round(total_time, 3),
        "avg_response_ms": round(avg_ms, 2),
        "std_response_ms": round(std_ms, 2),
        "p95_response_ms": round(p95_ms, 2),
    }


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Waiting for service to be ready...")
    wait_for_service()
    print("Service is ready. Seeding data...")
    seed_data()
    print("Seeding done. Starting benchmark...\n")

    all_results = []

    for scenario_name, scenario_func in SCENARIOS.items():
        for num_threads in THREAD_COUNTS:
            print(f"Running {scenario_name} with {num_threads} threads...")
            result = run_scenario(scenario_name, scenario_func, num_threads, REQUESTS_PER_THREAD)
            all_results.append(result)
            print(f"  -> {result['total_requests']} reqs in {result['total_time_sec']}s, "
                  f"avg={result['avg_response_ms']}ms, p95={result['p95_response_ms']}ms")

    csv_path = os.path.join(RESULTS_DIR, "benchmark_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "scenario", "threads", "total_requests", "total_time_sec",
            "avg_response_ms", "std_response_ms", "p95_response_ms",
        ])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"\nBenchmark complete. Results saved to {csv_path}")


if __name__ == "__main__":
    main()
