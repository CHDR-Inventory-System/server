"""
This is a debug file that contains tasks to test the APScheduler
"""
from datetime import datetime
from flask import Flask


def tick(app: Flask):
    print(f"Tick => {datetime.now().strftime('%I:%M:%S')}")
