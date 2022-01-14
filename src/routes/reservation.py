import mysql.connector
from util.database import Database
from flask import Blueprint, current_app, jsonify, request
from util.response import create_error_response, convert_javascript_date

reservation_blueprint = Blueprint("reservation", __name__)


@reservation_blueprint.route("/user/<int:user_id>", methods=["GET"])
@Database.with_connection
def get_user_reservations(user_id, **kwargs):
    cursor = kwargs["cursor"]

    try:
        cursor.execute("SELECT * FROM reservation WHERE user = %s" % (user_id,))
        reservations = cursor.fetchall()

        for row in reservations:
            cursor.execute("SELECT * FROM item WHERE ID = %s", (row["item"],))
            row["item"] = cursor.fetchone()
            row["item"]["moveable"] = bool(row["item"]["moveable"])
            row["item"]["available"] = bool(row["item"]["available"])

            if row["userAdminID"] is not None:
                cursor.execute(
                    """
                    SELECT email, ID, role FROM users
                    WHERE ID = %s AND (role = 'Admin' OR role = 'Super')
                    """,
                    (row["userAdminID"],),
                )
                row["admin"] = cursor.fetchone()
            else:
                row["admin"] = None

        return jsonify(reservations)
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
    return create_error_response("An unexpected error occurred", 500)


@reservation_blueprint.route("/", methods=["POST"])
@Database.with_connection
def create_reservation(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json()
    reservation = {}

    try:
        reservation["item"] = post_data["item"]
        reservation["user"] = post_data["user"]
        reservation["start_date_time"] = convert_javascript_date(
            post_data["startDateTime"]
        )
        reservation["end_date_time"] = convert_javascript_date(post_data["endDateTime"])
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    try:
        cursor.execute("SELECT ID from item WHERE ID = %s", (reservation["item"],))
        result = cursor.fetchone()

        if result is None:
            return create_error_response("Invalid item ID", 400)

        cursor.execute("SELECT ID from users WHERE ID = %s", (reservation["user"],))
        result = cursor.fetchone()

        if result is None:
            return create_error_response("Invalid user ID", 400)

        query = """
            INSERT INTO reservation (item, user, startDateTime, endDateTime)
            VALUES (
                %(item)s,
                %(user)s,
                %(start_date_time)s,
                %(end_date_time)s
            )
        """

        cursor.execute(query, reservation)
        connection.commit()
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@reservation_blueprint.route("/<int:reservation_id>", methods=["DELETE"])
@Database.with_connection
def delete_reservation(reservation_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    try:
        cursor.execute("DELETE FROM reservation WHERE ID = %s" % (reservation_id,))
        connection.commit()
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})
