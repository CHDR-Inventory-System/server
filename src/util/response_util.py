from flask import jsonify


def create_error_response(message, status_code):
    """
    Takes a message and a status code and returns that error message
    in JSON format as well as sets the status code.
    """
    return jsonify({'error': message}), status_code
