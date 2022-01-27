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

    try:
        # Takes incoming data as json
        incoming_data = request.get_json()

        nid_ = incoming_data["nid"]
        password_ = incoming_data["password"]
        email_ = incoming_data["email"]
        # set role and verified automatically to user and Admin and Super admnin or 0 to verified
        verified_ = 0
        role_ = "User"

        # If variables were inserted then proceed
        if nid_ and password_ and email_:

            try:
                ucf_creds = ldap_auth(nid_, password_)

                first_name = ucf_creds["entries"][0]["attributes"]["givenName"]
                last_name = ucf_creds["entries"][0]["attributes"]["sn"]
                full_name = f"{first_name} {last_name}"

                # sql query to check if Email exists already
                cursor.execute("SELECT * FROM users WHERE email = %s", (email_,))
                exist_acc = cursor.fetchone()

                # Check to see if account exist already or not
                if exist_acc:
                    return create_error_response("Account already exists!", 208)
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email_):
                    return create_error_response("Invalid email address!", 409)
                else:
                    sql_Query2 = """
                  INSERT INTO users(nid, email, verified, role, fullName)
                  VALUES(%s, %s, %s, %s, %s)
                """
                    data = (
                        nid_,
                        email_,
                        verified_,
                        role_,
                        full_name,
                    )
                cursor.execute(sql_Query2, data)
                connection.commit()

                return jsonify({"message": "New account created"})

            except LDAPBindError:
                return create_error_response("Invalid credentials", 401)
            except LookupError as err:
                print(err)
                current_app.logger.exception(str(err))
                return create_error_response(str(err), 500)
            except ConnectionError as err:
                current_app.logger.exception(str(err))
                return create_error_response(str(err), 503)
        else:
            return create_error_response("Please enter the required fields!", 204)

    except Exception as err:
        current_app.logger.exception(str(err))
        return create_error_response("Error", 500)


@users_blueprint.route("/login", methods=["POST"])
@Database.with_connection
def login(**kwargs):
    try:
        cursor = kwargs["cursor"]

        # Takes incoming data as json
        incoming_data = request.get_json()

        nid_ = incoming_data["nid"]
        password_ = incoming_data["password"]

        # If variables were inserted then proceed
        if nid_ and password_:
            try:
                ucf_creds = ldap_auth(nid_, password_)
                ucf_creds_nid = ucf_creds["entries"][0]["attributes"]["cn"]

                if ucf_creds_nid != nid_:
                    return create_error_response("Invalid credentials", 401)
                # sql query to check if nid exists already
                cursor.execute("SELECT * FROM users WHERE nid = %s", (ucf_creds_nid,))
                exist_acc = cursor.fetchone()

                if exist_acc:
                    my_token = create_access_token(
                        identity={"id": exist_acc["ID"], "role": exist_acc["role"]}
                    )
                    return jsonify({"token": my_token})

            except LDAPBindError:
                return create_error_response("Invalid credentials", 401)
            except LookupError as err:
                print(err)
                current_app.logger.exception(str(err))
                return create_error_response(str(err), 500)
            except ConnectionError as err:
                current_app.logger.exception(str(err))
                return create_error_response(str(err), 503)

        else:
            return create_error_response("Please enter all required fields!", 204)
    except Exception as err:
        current_app.logger.exception(str(err))
        return create_error_response("Error", 500)


@users_blueprint.route("/<int:id>", methods=["DELETE"])
@Database.with_connection
def delete(id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    try:
        id_ = id
        # checks to see if user exist or not
        sqlQuery_1 = "SELECT * FROM users WHERE ID = %s"
        cursor.execute(sqlQuery_1, (id_,))
        exist_acc = cursor.fetchone()

        if not exist_acc:
            return create_error_response("User does not exist", 404)

        # sql query to delete user if it exists already
        sqlQuery_2 = "DELETE FROM users WHERE ID=%s"

        try:
            cursor.execute("DELETE FROM reservation WHERE user = %s" % (id_,))
            cursor.execute(sqlQuery_2 % (id_,))

            connection.commit()
        except Exception as err:
            print(err)
            connection.rollback()
            return create_error_response("Error", 400)

        return jsonify({"status": "Success"})
    except Exception as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response("Error", 500)


@users_blueprint.route("/<int:id>", methods=["GET"])
@Database.with_connection
def get_user_byID(id, **kwargs):
    cursor = kwargs["cursor"]

    id_ = id

    # sql query to check if user exists already
    sqlQuery_1 = "SELECT * FROM users WHERE ID=%s"
    cursor.execute(sqlQuery_1, (id_,))
    exist_acc = cursor.fetchone()
    created_ = exist_acc["created"]
    nid_ = exist_acc["nid"]
    email_ = exist_acc["email"]
    full_name = exist_acc["fullName"]

    if exist_acc:
        return jsonify(
            {"Full Name": full_name, "nid": nid_, "email": email_, "created": created_}
        )
    else:
        return create_error_response("User does not exist", 404)


@users_blueprint.route("/", methods=["GET"])
@Database.with_connection
def get_all_users(**kwargs):
    cursor = kwargs["cursor"]

    # sql query to return all users in database with id, nid, email, created, and role
    query = "SELECT ID, fullName, nid, email, role, created FROM users"
    try:
        cursor.execute(query)
        # ? fetchall() returns a list of dictionaries where
        # ? the keys are the column-names in the database
        users = cursor.fetchall()

        return jsonify(users)

    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)
