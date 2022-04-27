from util.config import secrets
import mysql.connector
from util.database import Database
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from util.ics import create_calendar_for_reservation
from util.response import create_error_response, convert_javascript_date
from util.request import require_roles

from util.email import Emailer
from smtplib import SMTPException
import os


reservation_blueprint = Blueprint("reservation", __name__)

VALID_RESERVATION_STATUSES = {
    "approved",
    "cancelled",
    "checked out",
    "denied",
    "late",
    "missed",
    "pending",
    "returned",
}


@Database.with_connection()
def query_reservations(
    base_query: str, variables: dict = {}, use_jsonify=True, **kwargs
):
    """
    A helper function that uses "base_query" to select reservations from
    the reservation table and build a JSON structure that includes the
    item, user, and admin who approves it. Any variables should be
    passed as a dict to "variables"

    If use_jsonify is true, this will cause this function to return a jsonified
    response. Otherwise, it'll return an array of reservations.
    """
    cursor = kwargs["cursor"]

    try:
        cursor.execute(base_query, variables)
        reservations = cursor.fetchall()

        # For every reservation, we'll need to replace the item id,
        # user id, and admin id with the actual values in the database
        for reservation in reservations:
            query = """
                SELECT
                    A.*, B.barcode, B.available, B.moveable, B.location,
                    B.quantity, B.retiredDateTime
                FROM itemChild AS A
                LEFT JOIN item AS B on A.item = B.ID
                WHERE A.item = %(item_id)s
                UNION
                SELECT
                    A.*, B.barcode, B.available, B.moveable, B.location,
                    B.quantity, B.retiredDateTime
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

            # Using next here to find the first reservation that matches this condition
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

            if user:
                user["verified"] = bool(user["verified"])
                reservation["user"] = user

            # Replace the reservation's admin field with the actual user data from the
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

                if admin:
                    admin["verified"] = bool(admin["verified"])
                    reservation["admin"] = admin
                else:
                    reservation["admin"] = None
            else:
                reservation["admin"] = None

            # Since this filed can be accesse through the nested admin object,
            # we no longer need this property
            del reservation["userAdminID"]

        return jsonify(reservations) if use_jsonify else reservations
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
    return create_error_response("An unexpected error occurred", 500)


@reservation_blueprint.route("/", methods=["GET"])
@require_roles(["admin", "super"])
def get_all_reservations():
    status = request.args.get("status", default="", type=str)

    if status:
        return query_reservations(
            "SELECT * FROM reservation WHERE status = %(status)s",
            variables={"status": status},
        )

    return query_reservations("SELECT * FROM reservation")


@reservation_blueprint.route("/user/<int:user_id>", methods=["GET"])
@jwt_required()
def get_reservations_by_user(user_id):
    user = get_jwt_identity()

    # Prevent users from looking at reservations that aren't their own
    if user["role"].lower() == "user" and user["ID"] != user_id:
        return create_error_response(
            "You don't have permission to view this resource", 403
        )

    return query_reservations(
        "SELECT * FROM reservation WHERE user = %(user_id)s",
        variables={"user_id": user_id},
    )


@reservation_blueprint.route("/item/<int:item_id>", methods=["GET"])
@jwt_required()
def get_reservations_by_item(item_id):
    jwt_user = get_jwt_identity()

    reservations = query_reservations(
        "SELECT * FROM reservation WHERE item = %(item_id)s",
        variables={"item_id": item_id},
        use_jsonify=False,
    )

    # Prevent normal users from viewing the user and admin associated
    # with a reservation. That information should only be available to admins
    if jwt_user["role"].lower() == "user":
        for reservation in reservations:
            del reservation["user"]
            del reservation["admin"]

    return jsonify(reservations)


@reservation_blueprint.route("/<int:reservation_id>", methods=["GET"])
@require_roles(["admin", "super"])
def get_reservations_by_id(reservation_id):
    return query_reservations(
        "SELECT * FROM reservation WHERE ID = %(reservation_id)s",
        variables={"reservation_id": reservation_id},
    )


@reservation_blueprint.route("/", methods=["POST"])
@jwt_required()
@Database.with_connection()
def create_reservation(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json()
    reservation = {}

    try:
        cursor.execute("SELECT ID FROM users WHERE email = %s", (post_data["email"],))

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
        reservation["admin_id"] = post_data.get("adminId", None)

        if reservation["status"].lower() not in VALID_RESERVATION_STATUSES:
            return create_error_response("Invalid reservation status", 400)

        # If the ID of the admin was given, we need to make sure that ID
        # refers to a valid user and that the user is an admin or super user
        if reservation["admin_id"]:
            cursor.execute(
                "SELECT role FROM users WHERE ID = %s", (int(reservation["admin_id"]),)
            )
            admin = cursor.fetchone()

            if not admin:
                return create_error_response("No admin with this ID", 404)

            if admin["role"].lower() not in {"admin", "super"}:
                return create_error_response("Insufficient permissions", 401)

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

        cursor.execute(
            """
            SELECT status FROM reservation WHERE user = %(user)s
            AND item = %(item)s
            """,
            reservation,
        )

        reservations = cursor.fetchall()

        for res in reservations:
            if res["status"].lower() in {"approved", "checked out", "late", "pending"}:
                return create_error_response(
                    "You already have a reservation for this item", 409
                )

        query = """
            INSERT INTO reservation (
                item,
                user,
                startDateTime,
                endDateTime,
                status,
                userAdminID
            )
            VALUES (
                %(item)s,
                %(user)s,
                %(start_date_time)s,
                %(end_date_time)s,
                %(status)s,
                %(admin_id)s
            )
        """

        cursor.execute(query, reservation)
        connection.commit()

        reservations = query_reservations(
            "SELECT * FROM reservation WHERE ID = %(row_id)s",
            variables={"row_id": cursor.lastrowid},
            use_jsonify=False,
        )

        # Makes sure to update the quantity when an item is checked out
        if reservation["status"].lower() == "checked out":
            cursor.execute("SELECT quantity FROM item WHERE ID = %(item)s", reservation)
            item = cursor.fetchone()

            # Here, we need to check if the quantity is 1 because we're gonna decrement
            # it right away. We need to check before we update the quantity because the
            # change may not be reflected immediately
            if item["quantity"] == 1:
                cursor.execute(
                    "UPDATE item SET available = 0 WHERE ID = %(item)s", reservation
                )

            cursor.execute(
                "UPDATE item SET quantity = quantity - 1 WHERE ID = %(item)s",
                reservation,
            )

            connection.commit()

        # BEGIN ICS

        if reservation["status"].lower() in {"approved", "checked out"}:
            res = reservations[0]
            res_id = res["ID"]
            calendar = create_calendar_for_reservation(res)
            ics_path = f"{res_id}.ics"
            email_body = """
                Your reservation has been created.
                Use the attached file to add the reservation to your calendar.
                """

            user_email = post_data["email"]
            with open(ics_path, "w") as f:
                f.write(str(calendar))

            try:
                Emailer.send_email(
                    user_email,
                    "CHDR Item Reservation Confirmation",
                    email_body,
                    ics_path,
                    cc=secrets["EMAIL_USERNAME"],
                )
            except SMTPException as e:
                current_app.logger.error(e.message)

            try:
                os.remove(ics_path)
            except OSError as e:
                current_app.logger.error(e.message)

        # END ICS

        return reservations[0]
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@reservation_blueprint.route("/<int:reservation_id>", methods=["DELETE"])
@require_roles(["admin", "super"])
@Database.with_connection()
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


@reservation_blueprint.route("/<int:reservation_id>/status", methods=["PATCH"])
@jwt_required()
@Database.with_connection()
def update_status(reservation_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    jwt_user = get_jwt_identity()
    post_data = request.get_json()
    fullSend = False

    if not post_data:
        return create_error_response("A body is required", 400)

    admin_id = post_data.get("adminId")
    start_date_time = post_data.get("startDateTime")
    end_date_time = post_data.get("endDateTime")

    try:
        cursor.execute("SELECT user FROM reservation WHERE ID = %s", (reservation_id,))
        uid = cursor.fetchone()

        if jwt_user["role"].lower() == "user" and jwt_user["ID"] != uid["user"]:
            return create_error_response(
                "You don't have permission to view this resource", 403
            )

    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    try:
        status = post_data["status"]
    except KeyError:
        return create_error_response("A status is required", 400)

    if status.lower() not in VALID_RESERVATION_STATUSES:
        return create_error_response("Invalid reservation status", 400)

    if (
        jwt_user["role"].lower() == "user"
        and jwt_user["ID"] == uid["user"]
        and status.lower() != "cancelled"
    ):
        return create_error_response("Invalid reservation status", 400)

    if jwt_user["role"].lower() in {"admin", "super"} and status.lower() in {
        "approved",
        "checked out",
    }:
        fullSend = True

    # If the item is checked out, we need to decrement the quantity
    if status.lower() == "checked out":
        cursor.execute(
            """
            UPDATE item SET quantity = quantity - 1 WHERE ID = (
                SELECT item FROM reservation WHERE ID = %s
            )
            """,
            (reservation_id,),
        )
        connection.commit()

        cursor.execute(
            """
            SELECT quantity FROM item WHERE ID = (
                SELECT item FROM reservation WHERE ID = %s
            )
            """,
            (reservation_id,),
        )

        updated_item = cursor.fetchone()

        # Makes sure to mark the item as unavailable if the the item is no longer in stock
        if updated_item["quantity"] == 0:
            cursor.execute(
                """
                UPDATE item SET available = 0 WHERE ID = (
                    SELECT item FROM reservation WHERE ID = %s
                )
                """,
                (reservation_id,),
            )

    # Once the item has been returned, we need to increment the quantity again
    if status.lower() == "returned":
        cursor.execute(
            """
            UPDATE item
            SET quantity = quantity + 1, available = 1
            WHERE ID = (SELECT item FROM reservation WHERE ID = %s)
            """,
            (reservation_id,),
        )
        connection.commit()

    try:
        cursor.execute(
            "UPDATE reservation SET status = %s WHERE ID = %s",
            (status, reservation_id),
        )

        if admin_id is not None:
            cursor.execute(
                "UPDATE reservation SET userAdminID = %s WHERE ID = %s",
                (int(admin_id), reservation_id),
            )

        if start_date_time is not None:
            cursor.execute(
                "UPDATE reservation SET startDateTime = %s WHERE ID = %s",
                (convert_javascript_date(start_date_time), reservation_id),
            )

        if end_date_time is not None:
            cursor.execute(
                "UPDATE reservation SET endDateTime = %s WHERE ID = %s",
                (convert_javascript_date(end_date_time), reservation_id),
            )

        connection.commit()
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    updated_reservations = query_reservations(
        "SELECT * FROM reservation WHERE ID = %(row_id)s",
        variables={"row_id": reservation_id},
        use_jsonify=False,
    )

    # Safety check: this length of "updated_reservations" should always be 1
    if len(updated_reservations) == 0:
        return create_error_response("An unexpected error occurred", 500)

    # BEGIN ICS

    if fullSend:
        reservation = updated_reservations[0]
        calendar = create_calendar_for_reservation(reservation)
        ics_path = f"{reservation_id}.ics"
        email_body = "Use the attached file to add the Reservation to your calendar."

        uid = reservation["user"]["ID"]
        query = f"SELECT email FROM users WHERE ID = {uid}"
        cursor.execute(query)
        user_email = cursor.fetchone()
        user_email = user_email["email"]

        with open(ics_path, "w") as f:
            f.write(str(calendar))

        try:
            Emailer.send_email(
                user_email,
                "CHDR Item Reservation Confirmation",
                email_body,
                ics_path,
                cc=secrets["EMAIL_USERNAME"],
            )
        except SMTPException as e:
            current_app.logger.error(e.message)

        try:
            os.remove(ics_path)
        except OSError as e:
            current_app.logger.error(e.message)

    # END ICS

    return jsonify(updated_reservations[0])
