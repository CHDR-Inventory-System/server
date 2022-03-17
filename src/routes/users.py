from smtplib import SMTPException
from flask import Blueprint, jsonify, request, current_app
from util.database import Database
from util.response import create_error_response
from util.request import require_roles
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    create_access_token,
    set_access_cookies,
    decode_token,
    unset_jwt_cookies,
)
from util.email import Emailer
import re
import mysql.connector
import uuid
import bcrypt
import textwrap

users_blueprint = Blueprint("users", __name__)


def get_base_url():
    return (
        "http://localhost:9000" if current_app.debug else "https://chdr.cs.ucf.edu/csi"
    )


def create_verification_link(user_id: str, verification_code: str):
    return f"{get_base_url()}/#/verify/{user_id}/{verification_code}"


def create_verification_email_body(user_id: str, name: str, verification_code: str):
    first_name = name.split(" ")[0]

    return textwrap.dedent(
        f"""
        Welcome {first_name}! To verify your account, please click the following link:
        {create_verification_link(user_id, verification_code)}
        """
    )


@users_blueprint.route("/register", methods=["POST"])
@Database.with_connection()
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
@Database.with_connection()
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
@Database.with_connection()
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
                    "verified": bool(user["verified"]),
                }
            )

            response = jsonify(
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

            jwt = decode_token(token)

            set_access_cookies(response, token)
            response.set_cookie(
                "session_exp", value=str(jwt["exp"]), expires=jwt["exp"]
            )

            return response

        return create_error_response("Invalid credentials", 401)
    except Exception as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/logout", methods=["POST"])
def logout():
    response = jsonify({"status": "Success"})
    unset_jwt_cookies(response)
    return response


@users_blueprint.route("/<int:user_id>", methods=["DELETE"])
@jwt_required()
@Database.with_connection()
def delete_user(user_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    jwt_user = get_jwt_identity()
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

        if jwt_user["role"].lower() == "user" and jwt_user["ID"] != user_id:
            return create_error_response(
                "You don't have permission to view this resource", 403
            )

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
@require_roles(["admin", "super"])
@Database.with_connection()
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
@require_roles(["admin", "super"])
@Database.with_connection()
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
@require_roles(["super"])
@Database.with_connection()
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

    query = "UPDATE users SET role = %s WHERE ID = %s"

    try:
        cursor.execute(query, (user_role, user_id))
        connection.commit()
    except mysql.connection.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@users_blueprint.route("/<int:user_id>/email", methods=["PATCH"])
@jwt_required()
@Database.with_connection()
def send_update_email(user_id, **kwargs):
    """
    Handles sending the email that lets a user update their email
    """
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    jwt_user = get_jwt_identity()
    request_data = request.get_json()

    if not request_data:
        return create_error_response("A body is required", 400)

    if jwt_user["role"].lower() == "user" and jwt_user["ID"] != user_id:
        return create_error_response(
            "You don't have permission to view this resource", 403
        )

    try:
        email = request_data["email"]
    except KeyError:
        return create_error_response("Parameter email is required", 400)

    try:
        cursor.execute(
            "SELECT ID, password, fullName, email FROM users WHERE ID = %s", (user_id,)
        )
        user = cursor.fetchone()

        # Check to make sure the current email of the user making the request matches
        # the email in the DB. This is to make sure other users can't update a different
        # user's email address
        if not user or email != user["email"]:
            return create_error_response("Invalid credentials", 401)

        # Create a new verification code so that previous links to update
        # a user's email won't work
        verification_code = str(uuid.uuid4())

        cursor.execute(
            "UPDATE users SET verificationCode = %s WHERE ID = %s",
            (verification_code, user_id),
        )

        connection.commit()

    except mysql.connection.Error as err:
        connection.rollback()
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    first_name = user["fullName"].split(" ")[0]
    body = textwrap.dedent(
        f"""
        Hello {first_name}, please visit the following link to change your email.
        If you didn't request an update, you can ignore this email.

        {get_base_url()}/#/update-email/{user["ID"]}/{verification_code}
        """
    )

    try:
        Emailer.send_email(email, "Requested Email Change", body)
    except SMTPException as e:
        current_app.logger.error(e.message)

    return jsonify({"status": "Success"})


@users_blueprint.route("/resendVerificationEmail", methods=["POST"])
@Database.with_connection()
def resend_verification_email(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json()

    if not post_data:
        return create_error_response("A body is required", 400)

    try:
        email = post_data["email"]
    except KeyError:
        return create_error_response("Parameter email is required", 400)

    try:
        cursor.execute(
            "SELECT ID, verificationCode, fullName from users WHERE email = %s",
            (email,),
        )
        user = cursor.fetchone()

        if not user:
            return create_error_response("Couldn't find a user with this email", 404)

        # Create a new verification code so that previous links to verify
        # the user's account won't work
        verification_code = str(uuid.uuid4())

        cursor.execute(
            "UPDATE users SET verificationCode = %s WHERE ID = %s",
            (verification_code, user["ID"]),
        )
        connection.commit()

    except mysql.connector.errors.Error as err:
        connection.rollback()
        current_app.logger.error(str(err))
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
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@users_blueprint.route("/sendPasswordResetEmail", methods=["POST"])
@Database.with_connection()
def send_password_reset_email(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json()

    try:
        email = post_data["email"]
    except KeyError:
        return create_error_response("Parameter email is required", 500)

    try:
        cursor.execute(
            "SELECT ID, verificationCode, fullName FROM users WHERE email = %s",
            (email,),
        )
        user = cursor.fetchone()

        if not user:
            return create_error_response("Couldn't find a user with this email", 404)

        # Create a new verification code so that previous links won't work
        verification_code = str(uuid.uuid4())

        cursor.execute(
            "UPDATE users SET verificationCode = %s WHERE ID = %s",
            (verification_code, user["ID"]),
        )
        connection.commit()

    except mysql.connector.errors.Error as err:
        current_app.logger.error(str(err))
        return create_error_response("An unexpected error occurred", 500)

    first_name = user["fullName"].split(" ")[0]

    body = textwrap.dedent(
        f"""
        Hello {first_name}, please visit the following link to reset your password.
        If you didn't request to change your password, you can ignore this email.

        {get_base_url()}/#/reset-password/{user["ID"]}/{verification_code}
        """
    )

    try:
        Emailer.send_email(email, "Requested Password Reset", body)
    except SMTPException as err:
        current_app.logger.error(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@users_blueprint.route("/resetPassword", methods=["POST"])
@Database.with_connection()
def reset_password(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json()

    if not post_data:
        return create_error_response("A body is required", 400)

    try:
        user_id = post_data["userId"]
        verification_code = post_data["verificationCode"]
        password = post_data["password"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    try:
        cursor.execute(
            "SELECT ID, verificationCode from users WHERE ID = %s", (user_id,)
        )
        user = cursor.fetchone()

        if not user or user["verificationCode"] != verification_code:
            return create_error_response("Invalid credentials", 401)

        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        cursor.execute(
            "UPDATE users SET password = %s, verificationCode = %s WHERE ID = %s",
            (hashed_password, str(uuid.uuid4()), user_id),
        )

        connection.commit()

    except mysql.connector.errors.Error as err:
        current_app.logger.error(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@users_blueprint.route("/updateEmail", methods=["PATCH"])
@Database.with_connection()
def update_user_email(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    request_data = request.get_json()

    if not request_data:
        return create_error_response("A body is required", 400)

    try:
        email = request_data["email"]
        password = request_data["password"]
        verification_code = request_data["verificationCode"]
        user_id = request_data["userId"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    try:
        cursor.execute(
            "SELECT verificationCode, password FROM users WHERE ID = %s", (user_id,)
        )
        user = cursor.fetchone()

        if not user or not bcrypt.checkpw(
            password.encode("utf-8"), user["password"].encode("utf-8")
        ):
            return create_error_response("Invalid credentials", 401)

        if user["verificationCode"] != verification_code:
            return create_error_response("Invalid verification code", 406)

        cursor.execute(
            "UPDATE users SET verificationCode = %s, email = %s WHERE ID = %s",
            (str(uuid.uuid4()), email, user_id),
        )

        connection.commit()

    except mysql.connector.errors.IntegrityError:
        return create_error_response("This email is in use", 409)
    except mysql.connector.errors.Error as err:
        current_app.logger.error(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@users_blueprint.route("<int:user_id>/updateName", methods=["PATCH"])
@jwt_required()
@Database.with_connection()
def update_name(user_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    request_data = request.get_json()
    jwt_user = get_jwt_identity()

    if not request_data:
        return create_error_response("A body is required", 400)

    if jwt_user["role"].lower() == "user" and jwt_user["ID"] != user_id:
        return create_error_response(
            "You don't have permission to view this resource", 403
        )

    try:
        full_name = request_data["fullName"]
    except KeyError:
        return create_error_response("Parameter fullName is required", 400)

    try:
        cursor.execute("SELECT ID FROM users WHERE ID = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return create_error_response("Invalid credentials", 401)

        cursor.execute(
            "UPDATE users SET fullName = %s WHERE ID = %s",
            (full_name.strip(), user_id),
        )
        connection.commit()
    except mysql.connector.errors.Error as err:
        current_app.logger.error(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})
