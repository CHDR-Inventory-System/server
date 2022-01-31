import mysql.connector
from flask import Blueprint, jsonify, request, current_app
from util.database import Database
from util.response import create_error_response
import re
import bcrypt
from flask_jwt_extended import create_access_token


users_blueprint = Blueprint("users", __name__)


@users_blueprint.route("/register", methods=["POST"])
@Database.with_connection
def do_register(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    try:
        # Takes incoming data as json
        incoming_data = request.get_json()
        nid_ = incoming_data["nid"]
        password_ = incoming_data["password"]
        email_ = incoming_data["email"]
        # comfirm_Pwrd = incoming_data['Comfirm_pass']
        # set role and verified automatically to user and Admin and Super admnin or 0 to verified
        verified_ = 0
        role_ = "User"

        # If variables were inserted then proceed
        if nid_ and password_ and email_ and request.method == "POST":
            # if password != comfirm_Pwrd:
            # return create_error_response('Passwords do not match!', 404)

            hashed_Password = bcrypt.hashpw(password_.encode("utf-8"), bcrypt.gensalt())
            # sql query to check if Email exists already

            cursor.execute("SELECT * FROM users WHERE email = %s", (email_,))
            exist_acc = cursor.fetchone()
            # Check to see if account exist already or not
            if exist_acc:
                return create_error_response("Account already exists!", 404)
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email_):
                return create_error_response("Invalid email address!", 404)
            else:
                sql_Query2 = """
                  INSERT INTO users(nid, password, email, verified, role)
                  VALUES(%s, %s, %s, %s, %s)
                """
                data = (
                    nid_,
                    hashed_Password,
                    email_,
                    verified_,
                    role_,
                )
                cursor.execute(sql_Query2, data)
                connection.commit()

                return jsonify({"message": "New account created"})

        else:
            return create_error_response("Please enter the required fields!", 404)

    except Exception as err:
        print(err)
        return create_error_response("Error", 404)


@users_blueprint.route("/login", methods=["POST"])
@Database.with_connection
def do_login(**kwargs):
    try:
        cursor = kwargs["cursor"]

        # Takes incoming data as json
        incoming_data = request.get_json()
        email_ = incoming_data["Email"]
        password_ = incoming_data["Password"]

        if email_ and password_ and request.method == "POST":
            # sql query to check if Email exists already
            sqlQuery_1 = "SELECT * FROM users WHERE Email = %s"
            cursor.execute(sqlQuery_1, (email_,))
            exist_acc = cursor.fetchone()

            hash_pwrd = exist_acc["password"]
            userid = exist_acc["ID"]

            if exist_acc:
                if bcrypt.checkpw(password_.encode("utf-8"), hash_pwrd.encode("utf-8")):
                    my_token = create_access_token(identity=userid)
                    return jsonify({"token": my_token})

                else:
                    return create_error_response("Password do not match!", 404)
            else:
                return create_error_response("Account does not exist!", 404)
        else:
            return create_error_response("Please enter all required fields!", 404)
    except Exception as err:
        print(err)
        return create_error_response("Error", 404)


@users_blueprint.route("/<int:id>", methods=["DELETE"])
@Database.with_connection
def do_delete(id, **kwargs):
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
            return create_error_response("Error", 404)

        return jsonify({"status": "Success"})
    except Exception as err:
        print(err)
        connection.rollback()
        return create_error_response("Error", 404)


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

    if exist_acc:
        return jsonify({"created": created_, "nid": nid_, "email": email_})
    else:
        return create_error_response("User does not exist", 404)


@users_blueprint.route("/", methods=["GET"])
@Database.with_connection
def get_all_users(**kwargs):
    cursor = kwargs["cursor"]

    # sql query to return all users in database with id, nid, email, created, and role
    query = "SELECT ID, nid, email, role, created, verified FROM users"
    try:
        cursor.execute(query)
        # ? fetchall() returns a list of dictionaries where
        # ? the keys are the column-names in the database
        users = cursor.fetchall()

        return jsonify(users)

    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@users_blueprint.route("/<int:user_id>/email", methods=["PATCH"])
@Database.with_connection
def update_user_email(user_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    request_data = request.get_json()

    try:
        email = request_data["email"]
    except KeyError:
        return create_error_response("An email is required", 400)
    except TypeError:
        return create_error_response("An email is requried", 400)

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
