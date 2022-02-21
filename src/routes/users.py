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

users_blueprint = Blueprint("users", __name__)


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
        firstname = incoming_data["firstname"]
        lastname = incoming_data["lastname"]
        email = incoming_data["email"]
        password = incoming_data["password"]

    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return create_error_response("Invalid email address!", 400)

    try:

        full_name = f"{firstname} {lastname}"

        hashed_Password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        # Check to see if account exist already or not
        cursor.execute("SELECT ID FROM users WHERE email = %s", (email,))
        exist_acc = cursor.fetchone()

        if exist_acc:

            return create_error_response(
                "An account with this email already exists", 409
            )

        # Set role and verified automatically to user and unverified
        verified = 0
        role = "User"
        verifiCode = uuid.uuid4()
        verifiCode = str(verifiCode)

        query = """
        INSERT INTO users(fullName,email, verified, role, password, verificationCode)
        VALUES(%s, %s, %s, %s, %s,%s)
        """
        data = (
            full_name,
            email,
            verified,
            role,
            hashed_Password,
            verifiCode,
        )

        cursor.execute(query, data)
        connection.commit()

        # excecute for the user to get their ID to pass along with the link
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return create_error_response("An unexpected error occurred", 500)

        ID = user["ID"]
        num = str(ID)
        verification_link = (
            f"http://127.0.0.1:4565/verify/?id={num}&verificationCode={verifiCode}"
        )
        subj = "Verify Account"
        body = (
            "Hello"
            + " "
            + full_name
            + ","
            + "to verify your account, please click the following link:"
            + verification_link
        )

        try:
            Emailer.send_email(email, subj, body)
        except SMTPException as e:
            current_app.logger.error(e.message)

        return jsonify({"status": "New account created"})

    except Exception as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/verify", methods=["PATCH"])
@Database.with_connection
def update_Verification(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    # Takes incoming data as json
    incoming_data = request.get_json()

    if not incoming_data:
        return create_error_response("A body is required", 400)

    try:
        user_Id = incoming_data["userId"]
        verification_Code = incoming_data["verificationCode"]

    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    cursor.execute("SELECT * FROM users WHERE ID = %s", (user_Id,))
    user = cursor.fetchone()

    if not user:
        return create_error_response("User does not exist", 404)
    database_code = user["verificationCode"]
    verifyValue = 1

    print(database_code)
    print(verification_Code)

    if verification_Code != database_code:
        return create_error_response("Invalid email credentials!", 400)

    if verification_Code == database_code:

        query = "UPDATE users SET verified = %s WHERE ID = %s " % (verifyValue, user_Id)

        try:
            cursor.execute(query)
            connection.commit()

            return jsonify({"status": "Success"})
        except (Exception, LookupError) as err:
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

        hash_pwrd = user["password"]

        if bcrypt.checkpw(password.encode("utf-8"), hash_pwrd.encode("utf-8")):
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
        else:
            return create_error_response("Invalid credentials", 401)
    except Exception as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/<int:user_id>", methods=["DELETE"])
@Database.with_connection
def delete(user_id, **kwargs):
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
        exist_acc = cursor.fetchone()

        if not exist_acc:
            return create_error_response("Invalid credentials", 401)

        hash_pwrd = exist_acc["password"]

        if not bcrypt.checkpw(password.encode("utf-8"), hash_pwrd.encode("utf-8")):
            return create_error_response("Invalid credentials", 401)

        bcrypt.checkpw(password.encode("utf-8"), hash_pwrd.encode("utf-8"))
        # sql query to delete user if it exists already
        query = "DELETE FROM users WHERE ID = %s"

        cursor.execute("DELETE FROM reservation WHERE user = %s" % (user_id,))
        cursor.execute(query % (user_id,))

        connection.commit()

        return jsonify({"status": "Success"})
    except Exception as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/<int:user_id>", methods=["GET"])
@Database.with_connection
def get_user_by_ID(user_id, **kwargs):
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

    try:
        user_role = request_data["role"]
    except KeyError:
        return create_error_response("A role is required", 400)
    except TypeError:
        return create_error_response("A role is required", 400)

    if (
        user_role.lower() != "user"
        and user_role.lower() != "admin"
        and user_role.lower() != "super"
    ):
        return create_error_response("Role is invalid", 406)

    query = "UPDATE users SET role = '%s' WHERE ID = '%s'" % (user_role, user_id)

    try:
        cursor.execute(query)
        connection.commit()
    except mysql.connection.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


# CHECK TO SEE IF IT WORK
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
    except (KeyError, TypeError):
        return create_error_response("Please enter the required credentials", 400)

    try:

        # sql query to check if nid exists already
        cursor.execute("SELECT * FROM users WHERE ID = %s", (user_id,))
        user = cursor.fetchone()
        hash_pwrd = user["password"]
        verifiCode = uuid.uuid4()
        verifiCode = str(verifiCode)

        if not user:
            return create_error_response("Invalid credentials", 401)

        if bcrypt.checkpw(password.encode("utf-8"), hash_pwrd.encode("utf-8")):
            query = """
                    UPDATE users
                    SET email = '%s', verificationCode = '%s', verified = 0
                    WHERE ID = %s
            """ % (
                email,
                verifiCode,
                user_id,
            )

            cursor.execute(query)
            connection.commit()

            num = str(user_id)
            verification_link = (
                f"http://127.0.0.1:4565/verify/?id={num}&verificationCode={verifiCode}"
            )
            subj = "Verify Account"
            body = (
                "Hello"
                + " "
                + user["fullName"]
                + ","
                + "To verify your account, please click the following link:"
                + verification_link
            )

            try:
                Emailer.send_email(email, subj, body)
            except SMTPException as e:
                current_app.logger.error(e.message)

    except mysql.connection.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})
