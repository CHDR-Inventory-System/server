from flask import jsonify
from datetime import datetime


def create_error_response(message: str, status_code: int):
    """
    Takes a message and a status code and returns that error message
    in JSON format as well as sets the status code.
    """
    return jsonify({"error": message}), status_code


def convert_javascript_date(js_date: int):
    """
    Takes a JavaScript date timestamp and converts it to a string date
    that can be inserted into the database
    """
    date = datetime.fromtimestamp(js_date / 1_000)
    return date.strftime("%Y-%m-%d %H:%M:%S")
