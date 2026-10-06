import os
import traceback
from agent import run_agent

try:
    print("Testing agent directly...")
    result = run_agent("test", "2026-10-01", ["Kal subah ka appointment mil jayega Dr. Rao ke saath?"])
    print("SUCCESS! Result:")
    print(result)
except Exception as e:
    print("FAILED with Exception:")
    traceback.print_exc()
