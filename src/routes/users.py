from flask import Blueprint, jsonify, request, current_app
from util.database import Database
from util.response import create_error_response
from flask_jwt_extended import create_access_token
from ldap3 import Server, Connection, ALL
from ldap3.core.exceptions import LDAPBindError
from util.config import secrets
import re
import json
import mysql.connector

users_blueprint = Blueprint("users", __name__)


def ldap_auth(nid, password):
    """
    Takes an NID and password and checks it against UCF's system.
    If the user inputs invalid credentials, this function will throw
    an LDAPBindError
    """
    ldap_server = secrets["LDAP_SERVER"]
    base_dn = secrets["BASE_DN"]
    domain = secrets["DOMAIN"]
    user = f"{nid}@{domain}"

    server = Server(ldap_server, get_info=ALL)
    connection = Connection(server, user=user, password=password, auto_bind=True)

    if connection.bind():
        res = connection.search(
            search_base=base_dn,
            search_filter=f"(samaccountname={nid})",
            attributes=["givenname", "sn", "employeeid", "cn"],
        )

        if res:
            return json.loads(connection.response_to_json())

        raise LookupError("Error searching directory")

    else:
        raise ConnectionError("Couldn't bind connection")


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
        nid = incoming_data["nid"]
        password = incoming_data["password"]
        email = incoming_data["email"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return create_error_response("Invalid email address!", 400)

    try:
        ucf_creds = ldap_auth(nid, password)

        first_name = ucf_creds["entries"][0]["attributes"]["givenName"]
        last_name = ucf_creds["entries"][0]["attributes"]["sn"]
        full_name = f"{first_name} {last_name}"

        # Check to see if account exist already or not
        cursor.execute(
            "SELECT ID FROM users WHERE email = %s OR nid = %s LIMIT 1", (email, nid)
        )
        exist_acc = cursor.fetchone()

        if exist_acc:
            return create_error_response(
                "An account with this email or nid already exists", 409
            )

        # Set role and verified automatically to user and unverified
        verified = 0
        role = "User"

        query = """
        INSERT INTO users(nid, email, verified, role, fullName)
        VALUES(%s, %s, %s, %s, %s)
        """
        data = (
            nid,
            email,
            verified,
            role,
            full_name,
        )

        cursor.execute(query, data)
        connection.commit()

        return jsonify({"status": "New account created"})

    except LDAPBindError:
        return create_error_response("Invalid credentials", 401)
    except ConnectionError as err:
        current_app.logger.exception(str(err))
        return create_error_response(str(err), 503)
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
        nid = incoming_data["nid"]
        password = incoming_data["password"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    # If variables were inserted then proceed
    try:
        ucf_creds = ldap_auth(nid, password)
        ucf_creds_nid = ucf_creds["entries"][0]["attributes"]["cn"]

        if ucf_creds_nid != nid:
            return create_error_response("Invalid credentials", 401)

        # sql query to check if nid exists already
        cursor.execute("SELECT * FROM users WHERE nid = %s", (ucf_creds_nid,))
        user = cursor.fetchone()

        if not user:
            return create_error_response("Invalid credentials", 401)

        token = create_access_token(identity={"ID": user["ID"], "role": user["role"]})

        return jsonify(
            {
                "ID": user["ID"],
                "created": user["created"],
                "email": user["email"],
                "role": user["role"],
                "nid": user["nid"],
                "verified": bool(user["verified"]),
                "fullName": user["fullName"],
                "token": token,
            }
        )

    except LDAPBindError:
        return create_error_response("Invalid credentials", 401)
    except ConnectionError as err:
        current_app.logger.exception(str(err))
        return create_error_response(str(err), 503)
    except (Exception, LookupError) as err:
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
        nid = incoming_data["nid"]
        password = incoming_data["password"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    try:
        # Fetch this user from the ldap server to verify their credentials
        ldap_auth(nid, password)
    except LDAPBindError:
        return create_error_response("Invalid credentials", 401)
    except ConnectionError as err:
        current_app.logger.exception(str(err))
        return create_error_response(str(err), 503)
    except (Exception, LookupError) as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    try:
        # checks to see if user exist or not
        query = "SELECT nid FROM users WHERE nid = %s"
        cursor.execute(query, (nid,))
        exist_acc = cursor.fetchone()

        if not exist_acc:
            return create_error_response("Invalid credentials", 401)

        # sql query to delete user if it exists already
        query = "DELETE FROM users WHERE nid = %s"

        cursor.execute("DELETE FROM reservation WHERE user = %s" % (nid,))
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
            SELECT ID, nid, email, verified, role, created, fullName
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
    query = "SELECT ID, nid, email, verified, role, created, fullName FROM users"

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
    except (KeyError, TypeError):
        return create_error_response("An email is required", 400)

    query = """
            UPDATE users
            SET email = '%s', verified = 0
            WHERE ID = %s
            """ % (
        email,
        user_id,
    )

    try:
        cursor.execute(query)
        connection.commit()
    except mysql.connection.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})
