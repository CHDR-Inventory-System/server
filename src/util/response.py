import dateutil.parser
from flask import jsonify
from datetime import datetime
from typing import Union


def create_error_response(message: str, status_code: int):
    """
    Takes a message and a status code and returns that error message
    in JSON format as well as sets the status code.
    """
    return jsonify({"error": message}), status_code


def convert_javascript_date(js_date: Union[str, int]):
    """
    Takes either a Javascript date timestamp or a Javascript Date string
    and converts it to a string date that can be inserted into the database
    """
    if isinstance(js_date, int):
        date = datetime.fromtimestamp(js_date / 1_000)
    else:
        date = dateutil.parser.parse("February 4th 2022 5:53 PM")

    return date.strftime("%Y-%m-%d %H:%M:%S")
