"""
start.py
--------
One-Click Launcher for the complete Text-to-SQL Assistant Application.
Connects Priyanshi's Frontend, Kunal's FastAPI Backend, and Khushi's Model Layer.

Run: python3 start.py
"""

import os
import sys
import webbrowser
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

def main():
    print("==========================================================================")
    print("      LAUNCHING LLM TEXT-TO-SQL ASSISTANT UNIFIED SYSTEM                 ")
    print("==========================================================================")
    print(f"Project Location : {ROOT_DIR}")

    # Check dependencies
    try:
        import uvicorn
        import fastapi
        import sqlglot
    except ImportError:
        print("\nInstalling required backend dependencies (uvicorn, fastapi, sqlglot)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "uvicorn", "fastapi", "sqlglot", "google-genai"])

    # Locate setup_db.py
    setup_script = ROOT_DIR / "backend" / "setup_db.py"
    if not setup_script.exists():
        setup_script = ROOT_DIR / "setup_db.py"

    db_file = ROOT_DIR / "backend" / "demo.db"
    if not db_file.exists() and setup_script.exists():
        print("Initializing demo SQLite database...")
        subprocess.check_call([sys.executable, str(setup_script)])

    print("\n[+] Starting FastAPI Unified Backend Server at http://localhost:8000")
    print("[+] Opening Web UI in your default browser...\n")

    # Automatically open browser after 1.5 seconds
    import threading, time
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")
    
    threading.Thread(target=open_browser, daemon=True).start()

    # Launch main.py
    main_script = ROOT_DIR / "backend" / "main.py"
    subprocess.call([sys.executable, str(main_script)])

if __name__ == "__main__":
    main()
