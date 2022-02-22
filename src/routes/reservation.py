import mysql.connector
from util.database import Database
from flask import Blueprint, current_app, jsonify, request
from util.response import create_error_response, convert_javascript_date

reservation_blueprint = Blueprint("reservation", __name__)

VALID_RESERVATION_STATUSES = {
    "pending",
    "denied",
    "approved",
    "missed",
    "checked out",
    "late",
    "returned",
}


@Database.with_connection
def query_reservations(base_query: str, **kwargs):
    """
    A helper function that uses "base_query" to select reservations from
    the reservation table and build a JSON structure that includes the
    item, user, and admin who approves it
    """
    cursor = kwargs["cursor"]

    try:
        cursor.execute(base_query)
        reservations = cursor.fetchall()

        # For every reservation, we'll need to replace the item id,
        # user id, and admin id with the actual values in the database
        for reservation in reservations:
            query = """
                SELECT
                    A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
                FROM itemChild AS A
                LEFT JOIN item AS B on A.item = B.ID
                WHERE A.item = %(item_id)s
                UNION
                SELECT
                    A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
                FROM itemChild AS A
                LEFT JOIN item AS B on A.item = B.ID
                WHERE A.item = %(item_id)s
            """
            cursor.execute(query, {"item_id": reservation["item"]})

            # Replace the reservation's item field with the actual item data
            # from the database
            items = cursor.fetchall()

            for item in items:
                item["moveable"] = bool(item["moveable"])
                item["available"] = bool(item["available"])
                item["main"] = bool(item["main"])

                cursor.execute(
                    "SELECT * from itemImage WHERE itemChild = %s", (item["ID"],)
                )

                item["images"] = cursor.fetchall()

            main_item = next((item for item in items if bool(item["main"])), None)
            main_item["children"] = [item for item in items if not bool(item["main"])]

            reservation["item"] = main_item

            # Replace the reservation's user field with the actual user data
            # from the database
            cursor.execute(
                """
                SELECT ID, email, verified, role, created, fullName
                FROM users
                WHERE ID = %s
                LIMIT 1
                """,
                (reservation["user"],),
            )

            user = cursor.fetchone()
            user["verified"] = bool(user["verified"])

            reservation["user"] = user

            # Replace the reservation's user field with the actual user data from the
            # database (if there is an admin who has updated this reservation's status)
            if reservation["userAdminID"] is not None:
                cursor.execute(
                    """
                    SELECT ID, email, verified, role, created, fullName
                    FROM users
                    WHERE ID = %s AND (role = 'Admin' OR role = 'Super')
                    LIMIT 1
                    """,
                    (reservation["userAdminID"],),
                )
                admin = cursor.fetchone()
                admin["verified"] = bool(admin["verified"])

                reservation["admin"] = admin
            else:
                reservation["admin"] = None

            # Since this filed can be accesse through the nested admin object,
            # we no longer need this property
            del reservation["userAdminID"]

        return jsonify(reservations)
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
    return create_error_response("An unexpected error occurred", 500)


@reservation_blueprint.route("/", methods=["GET"])
@Database.with_connection
def get_all_reservations(**kwargs):
    status = request.args.get("status", default="", type=str)

    if status:
        return query_reservations(
            'SELECT * FROM reservation WHERE status = "%s"' % (status,)
        )

    return query_reservations("SELECT * FROM reservation")


@reservation_blueprint.route("/user/<int:user_id>", methods=["GET"])
@Database.with_connection
def get_reservations_by_user(user_id, **kwargs):
    return query_reservations("SELECT * FROM reservation WHERE user = %s" % (user_id,))


@reservation_blueprint.route("/item/<int:item_id>", methods=["GET"])
@Database.with_connection
def get_reservations_by_item(item_id, **kwargs):
    return query_reservations("SELECT * FROM reservation WHERE item = %s" % (item_id,))


@reservation_blueprint.route("/<int:reservation_id>", methods=["GET"])
@Database.with_connection
def get_reservations_by_id(reservation_id, **kwargs):
    return query_reservations(
        "SELECT * FROM reservation WHERE ID = %s" % (reservation_id,)
    )


@reservation_blueprint.route("/", methods=["POST"])
@Database.with_connection
def create_reservation(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json()
    reservation = {}

    try:
        cursor.execute("SELECT ID FROM users WHERE email = '%s'", (post_data["email"],))

        user = cursor.fetchone()

        if not user:
            return create_error_response("Email not found", 404)

        reservation["user"] = user["ID"]

        # item refers to the ID of the item in the "item" table
        reservation["item"] = post_data["item"]
        reservation["start_date_time"] = convert_javascript_date(
            post_data["startDateTime"]
        )
        reservation["end_date_time"] = convert_javascript_date(post_data["endDateTime"])

        reservation["status"] = post_data.get("status", "Pending")

        if reservation["status"].lower() not in VALID_RESERVATION_STATUSES:
            return create_error_response("Invalid reservation status", 400)
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    try:
        cursor.execute("SELECT ID from item WHERE ID = %s", (reservation["item"],))
        result = cursor.fetchone()

        if result is None:
            return create_error_response("Invalid item ID", 400)

        query = """
            INSERT INTO reservation (item, user, startDateTime, endDateTime, status)
            VALUES (
                %(item)s,
                %(user)s,
                %(start_date_time)s,
                %(end_date_time)s,
                %(status)s
            )
        """

        cursor.execute(query, reservation)
        connection.commit()
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    # Return the newly created reservation
    return query_reservations(
        "SELECT * FROM reservation WHERE ID = %s" % (cursor.lastrowid,)
    )


@reservation_blueprint.route("/<int:reservation_id>", methods=["DELETE"])
@Database.with_connection
def delete_reservation(reservation_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    try:
        cursor.execute("DELETE FROM reservation WHERE ID = %s", (reservation_id,))
        connection.commit()
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@reservation_blueprint.route("/<int:reservation_id>/status", methods=["PUT"])
@Database.with_connection
def update_status(reservation_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    post_data = request.get_json()

    try:
        status = post_data["status"]
    except KeyError:
        return create_error_response("A status is required", 400)

    if status.lower() not in VALID_RESERVATION_STATUSES:
        return create_error_response("Invalid reservation status", 400)

    try:
        cursor.execute(
            "UPDATE reservation SET status = '%s' WHERE ID = %s",
            (status, reservation_id),
        )
        connection.commit()
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})
