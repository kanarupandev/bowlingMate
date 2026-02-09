import urllib.request
import time
import sys
import argparse

def wait_for_server(url, timeout=10):
    print(f"⏳ Connecting to {url}...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url) as response:
                if response.status == 200:
                    print(f"✅ Server is UP at {url} (Status: 200)")
                    return True
                else:
                    print(f"⚠️ Server returned status: {response.status}")
        except Exception as e:
            # print(f"Connection failed: {e}") # Optional verbose
            time.sleep(1)
    print(f"❌ Timeout waiting for {url}")
    return False

def smoke_test():
    parser = argparse.ArgumentParser(description="Run smoke test against API")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the server")
    args = parser.parse_args()
    
    base_url = args.url.rstrip("/")
    # Check docs endpoint as it usually loads without params
    target_url = f"{base_url}/docs"
    
    if not wait_for_server(target_url):
        print("Failed to connect to server.")
        sys.exit(1)

    print(f"🚀 Smoke Test PASSED against {base_url}")
    sys.exit(0)

if __name__ == "__main__":
    smoke_test()
