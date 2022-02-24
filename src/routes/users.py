from smtplib import SMTPException
from flask import Blueprint, jsonify, request, current_app
from util.database import Database
from util.response import create_error_response
from flask_jwt_extended import create_access_token
from util.email import Emailer
import re
import mysql.connector
import uuid
import bcrypt
import textwrap

users_blueprint = Blueprint("users", __name__)


def create_verification_link(user_id: str, verification_code: str):
    base_url = (
        "http://127.0.0.1:9000" if current_app.debug else "https://chdr.cs.ucf.edu/csi"
    )

    return f"{base_url}/#/verify/?id={user_id}&verificationCode={verification_code}"


def create_verification_email_body(user_id: str, name: str, verification_code: str):
    return textwrap.dedent(
        f"""
        Hello {name}, to verify your account, please click the following link:
        {create_verification_link(user_id, verification_code)}
        """
    )


@users_blueprint.route("/register", methods=["POST"])
@Database.with_connection
def register(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    # Takes incoming data as json
    incoming_data = request.get_json()

    if not incoming_data:
        return create_error_response("A body is required", 400)

    try:
        firstname = incoming_data["firstName"]
        lastname = incoming_data["lastName"]
        email = incoming_data["email"]
        password = incoming_data["password"]

    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return create_error_response("Invalid email address!", 400)

    try:

        full_name = f"{firstname} {lastname}"
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        # Check to see if account exist already or not
        cursor.execute("SELECT ID FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user:
            return create_error_response(
                "An account with this email already exists", 409
            )

        # Set role and verified automatically to user and unverified
        verified = 0
        role = "User"
        verification_code = str(uuid.uuid4())

        query = """
            INSERT INTO users
            (fullName, email, verified, role, password, verificationCode)
            VALUES(%s, %s, %s, %s, %s, %s)
        """
        data = (
            full_name,
            email,
            verified,
            role,
            hashed_password,
            verification_code,
        )

        cursor.execute(query, data)
        connection.commit()

        # execute for the user to get their ID to pass along with the link
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return create_error_response("An unexpected error occurred", 500)

        body = create_verification_email_body(
            user_id=user["ID"],
            name=user["fullName"],
            verification_code=verification_code,
        )

        try:
            Emailer.send_email(email, "Verify Your Account", body)
        except SMTPException as err:
            current_app.logger.exception(str(err))

        return jsonify({"status": "New account created"})

    except Exception as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/verify", methods=["PATCH"])
@Database.with_connection
def update_verification(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    # Takes incoming data as json
    incoming_data = request.get_json()

    if not incoming_data:
        return create_error_response("A body is required", 400)

    try:
        user_id = incoming_data["userId"]
        verification_code = incoming_data["verificationCode"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    cursor.execute("SELECT verificationCode FROM users WHERE ID = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        return create_error_response("Invalid credentials", 400)

    database_verification_code = user["verificationCode"]

    if verification_code != database_verification_code:
        return create_error_response("Invalid credentials", 400)

    verification_code = str(uuid.uuid4())
    query = "UPDATE users SET verified = %s, verificationCode = %s WHERE ID = %s"

    try:
        cursor.execute(
            query,
            (
                1,
                verification_code,
                user_id,
            ),
        )
        connection.commit()

        return jsonify({"status": "Success"})
    except Exception as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/login", methods=["POST"])
@Database.with_connection
def login(**kwargs):
    cursor = kwargs["cursor"]

    # Takes incoming data as json
    incoming_data = request.get_json()

    if not incoming_data:
        return create_error_response("A body is required", 400)

    try:
        email = incoming_data["email"]
        password = incoming_data["password"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    # If variables were inserted then proceed
    try:

        # sql query to check if nid exists already
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return create_error_response("Invalid credentials", 401)

        hashed_password = user["password"]

        if bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8")):
            token = create_access_token(
                identity={
                    "ID": user["ID"],
                    "role": user["role"],
                    "verified": user["verified"],
                }
            )

            return jsonify(
                {
                    "ID": user["ID"],
                    "created": user["created"],
                    "email": user["email"],
                    "role": user["role"],
                    "verified": bool(user["verified"]),
                    "fullName": user["fullName"],
                    "token": token,
                }
            )

        return create_error_response("Invalid credentials", 401)
    except Exception as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/<int:user_id>", methods=["DELETE"])
@Database.with_connection
def delete_user(user_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    incoming_data = request.get_json()

    if not incoming_data:
        return create_error_response("A body is required", 400)

    try:
        email = incoming_data["email"]
        password = incoming_data["password"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    try:
        # checks to see if user exist or not
        query = "SELECT * FROM users WHERE email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()

        if not user:
            return create_error_response("Invalid credentials", 401)

        if not bcrypt.checkpw(
            password.encode("utf-8"), user["password"].encode("utf-8")
        ):
            return create_error_response("Invalid credentials", 401)

        # sql query to delete user if it exists already
        query = "DELETE FROM users WHERE ID = %s"

        cursor.execute(query, (user_id,))

        connection.commit()

        return jsonify({"status": "Success"})
    except Exception as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/<int:user_id>", methods=["GET"])
@Database.with_connection
def get_user_by_id(user_id, **kwargs):
    cursor = kwargs["cursor"]

    try:
        # sql query to check if user exists already
        query = """
            SELECT ID, email, verified, role, created, fullName
            FROM users WHERE ID = %s
        """

        cursor.execute(query, (user_id,))
        user = cursor.fetchone()

        if not user:
            return create_error_response("User does not exist", 404)

        user["verified"] = bool(user["verified"])

        return jsonify(user)
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/", methods=["GET"])
@Database.with_connection
def get_all_users(**kwargs):
    cursor = kwargs["cursor"]

    # sql query to return all users in database with id, nid, email, created, and role
    query = "SELECT ID, email, verified, role, created, fullName FROM users"

    try:
        cursor.execute(query)
        # ? fetchall() returns a list of dictionaries where
        # ? the keys are the column-names in the database
        users = cursor.fetchall()

        for user in users:
            user["verified"] = bool(user["verified"])

        return jsonify(users)

    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/<int:user_id>/role", methods=["PATCH"])
@Database.with_connection
def update_user_role(user_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    request_data = request.get_json()

    if not request_data:
        return create_error_response("A body is required", 400)

    try:
        user_role = request_data["role"]
    except KeyError:
        return create_error_response("A role is required", 400)

    if user_role.lower() not in {"user", "super", "admin"}:
        return create_error_response("Role is invalid", 406)

    query = "UPDATE users SET role = '%s' WHERE ID = '%s'"

    try:
        cursor.execute(query, (user_role, user_id))
        connection.commit()
    except mysql.connection.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@users_blueprint.route("/<int:user_id>/email", methods=["PATCH"])
@Database.with_connection
def update_user_email(user_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    request_data = request.get_json()

    if not request_data:
        return create_error_response("A body is required", 400)

    try:
        email = request_data["email"]
        password = request_data["password"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    try:
        cursor.execute("SELECT * FROM users WHERE ID = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return create_error_response("Invalid credentials", 401)

        if not bcrypt.checkpw(
            password.encode("utf-8"), user["password"].encode("utf-8")
        ):
            return create_error_response("Invalid credentials", 401)

        verification_code = str(uuid.uuid4())

        query = """
            UPDATE users
            SET email = %s, verificationCode = %s, verified = 0
            WHERE ID = %s
        """

        cursor.execute(
            query,
            (
                email,
                verification_code,
                user_id,
            ),
        )
        connection.commit()

        body = create_verification_email_body(
            user_id=user["ID"],
            name=user["fullName"],
            verification_code=verification_code,
        )

        try:
            Emailer.send_email(email, "Verify Your Email", body)
        except SMTPException as e:
            current_app.logger.error(e.message)

    except mysql.connection.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})
