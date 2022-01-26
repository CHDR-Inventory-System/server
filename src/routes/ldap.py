from flask import Blueprint, jsonify, request
from ldap3 import Server, Connection, ALL
from ldap3.core.exceptions import LDAPBindError
from util.response import create_error_response
from util.config import secrets
import json


def ldap_auth(nid, password):
    ldap_server = secrets["LDAP_SERVER"]
    base_dn = secrets["BASE_DN"]
    domain = secrets["DOMAIN"]
    user = f"{nid}@{domain}"

    try:
        server = Server(ldap_server, get_info=ALL)
        connection = Connection(server, user=user, password=password, auto_bind=True)
    except LDAPBindError:
        return create_error_response("Invalid credentials", 401)

    if connection.bind():
        res = connection.search(
            search_base=base_dn,
            search_filter=f"(samaccountname={nid})",
            attributes=["givenname", "sn", "employeeid"],
        )

        json_resp = json.loads(connection.response_to_json())

        if res:
            return jsonify(json_resp)

        return create_error_response("Error searching directory", 500)

    else:
        return create_error_response("Couldn't bind connection", 500)


ldap_blueprint = Blueprint("ldap", __name__)


@ldap_blueprint.route("/", methods=["POST"])
def authenticate():
    post_data = request.get_json()
    password = post_data["password"]
    nid = post_data["nid"]

    return ldap_auth(nid, password)
