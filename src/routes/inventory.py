import mysql.connector
import os
from flask import Blueprint, jsonify, current_app, request
from util.database import Database
from util.response import create_error_response, convert_javascript_date

inventory_blueprint = Blueprint("inventory", __name__)
VALID_IMAGE_EXTENSIONS = {"jpg", "png", "jpeg"}


@inventory_blueprint.route("/", methods=["GET"])
@Database.with_connection
def get_all(**kwargs):
    cursor = kwargs["cursor"]

    try:
        cursor.execute("SELECT * FROM itemImage")
        images = cursor.fetchall()

        cursor.execute(
            """
            SELECT * from item
            LEFT JOIN itemChild on itemChild.item = item.ID
            UNION
            SELECT * from item
            RIGHT JOIN itemChild on itemChild.item = item.ID
            """
        )
        items = []

        for row in cursor.fetchall():
            row["images"] = [
                image for image in images if image["itemChild"] == row["ID"]
            ]

            # These booleans are stored as bits in the database so we
            # need to convert them to boleans before sending the response
            row["available"] = bool(row["available"])
            row["moveable"] = bool(row["moveable"])
            row["main"] = bool(row["main"])

            items.append(row)

        return jsonify(items)

    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/<int:item_id>", methods=["DELETE"])
@Database.with_connection
def delete_item(item_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    # Before we delete the item, we first need to delete the
    # image files from the server. If this fails, we can still
    # delete from the database
    try:
        cursor.execute(
            "SELECT imagePath FROM itemImage WHERE itemChild = %s" % (item_id,)
        )

        for image in cursor.fetchall():
            image_path = image["imagePath"]

            if os.path.exists(image_path):
                os.remove(image_path)
            else:
                current_app.logger.warn(
                    f"{image_path} does not exist, skipping deletion..."
                )

    except Exception as err:
        current_app.logger.exception(str(err))

    try:
        cursor.execute("DELETE FROM itemImage WHERE itemChild = %s" % (item_id,))
        cursor.execute("DELETE FROM itemChild WHERE item = %s" % (item_id,))
        cursor.execute("DELETE FROM item WHERE ID = %s" % (item_id,))

        connection.commit()
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@inventory_blueprint.route("/<int:item_id>", methods=["GET"])
@Database.with_connection
def get_item_by_id(item_id, **kwargs):
    cursor = kwargs["cursor"]

    try:
        cursor.execute("SELECT * from itemImage WHERE itemChild = %s" % (item_id,))
        images = cursor.fetchall()

        query = """
            SELECT * FROM item
            LEFT JOIN itemChild on itemChild.item = item.ID
            WHERE item.ID = %(item_id)s
            UNION
            SELECT * FROM item
            RIGHT JOIN itemChild on itemChild.item = item.ID
            WHERE item.ID = %(item_id)s
        """

        cursor.execute(query, {"item_id": item_id})
        result = cursor.fetchone()

        if not result:
            return create_error_response(f"No item found with id {item_id}", 404)

        result["moveable"] = bool(result["moveable"])
        result["available"] = bool(result["available"])
        result["main"] = bool(result["main"])
        result["images"] = images

        return jsonify(result)
    except mysql.connector.Error as err:
        current_app.log_exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/search", methods=["GET"])
@Database.with_connection
def get_item_by_name(**kwargs):
    cursor = kwargs["cursor"]
    query = """
        SELECT * FROM itemChild
        LEFT JOIN item on itemChild.item = item.ID
        WHERE name LIKE %(item_name)s
        UNION
        SELECT * FROM itemChild
        RIGHT JOIN item on itemChild.item = item.ID
        WHERE name LIKE %(item_name)s
    """
    item_name = request.args.get("name", default="", type=str)

    try:
        cursor.execute(query, {"item_name": f"%{item_name}%"})
        items = []

        for row in cursor.fetchall():
            row["available"] = bool(row["available"])
            row["moveable"] = bool(row["moveable"])

            items.append(row)

        return jsonify(items)
    except mysql.connector.Error as err:
        current_app.log_exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/barcode/<barcode>", methods=["GET"])
@Database.with_connection
def get_item_by_barcode(barcode, **kwargs):
    cursor = kwargs["cursor"]
    query = """
        SELECT * FROM item
        LEFT JOIN itemChild on itemChild.item = item.ID
        WHERE barcode = %(barcode)s
        UNION
        SELECT * FROM item
        RIGHT JOIN itemChild on itemChild.item = item.ID
        WHERE barcode = %(barcode)s
    """

    try:
        cursor.execute(query, {"barcode": barcode})
        items = []

        for row in cursor.fetchall():
            row["available"] = bool(row["available"])
            row["moveable"] = bool(row["moveable"])
            row["main"] = bool(row["main"])

            items.append(row)

        return jsonify(items)
    except mysql.connector.Error as err:
        current_app.log_exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/<int:item_id>/uploadImage", methods=["POST"])
@Database.with_connection
def upload_images(item_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    images = request.files.getlist("image")

    for image in images:
        if image.filename.split(".")[-1] not in VALID_IMAGE_EXTENSIONS:
            extensions = ", ".join(VALID_IMAGE_EXTENSIONS)
            return create_error_response(f"Extension must be one of {extensions}", 400)

    try:
        os.makedirs("images", exist_ok=True)

        for image in images:
            image_path = os.path.join(
                current_app.config["IMAGE_FOLDER"], image.filename
            )
            image.save(image_path)

            query = """
                INSERT INTO itemImage (itemChild, imagePath)
                VALUES ("%s", "%s")
            """

            cursor.execute(query % (item_id, image_path))

        connection.commit()
    except Exception as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response(
            "An unexpected error occurred uploading image", 500
        )

    return jsonify({"status": "Success"})


@inventory_blueprint.route("/add", methods=["POST"])
@Database.with_connection
def add_item(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    post_data = request.get_json()
    item_values = {}

    try:
        # These values are required so we need to check for any key errors
        item_values["barcode"] = post_data["barcode"]
        item_values["available"] = int(post_data["available"])
        item_values["moveable"] = int(post_data["moveable"])
        item_values["location"] = post_data["location"]
    except KeyError as err:
        current_app.log_exception(str(err))
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    item_child_values = {}

    try:
        item_child_values["name"] = post_data["name"]
        item_child_values["type"] = post_data["type"]
        item_child_values["serial"] = post_data["serial"]

        # Using 'get' for these parameters so that they can default
        # to None (NULL in mysql's case) when inserted without a value
        item_child_values["description"] = post_data.get("description")
        item_child_values["vendor_name"] = post_data.get("vendorName")
        item_child_values["purchase_date"] = post_data.get("purchaseDate")
        item_child_values["vendor_price"] = post_data.get("vendorPrice")
        item_child_values["main"] = int(post_data.get("main", False))

        # Only convert these values if they exists. Otherwise, we'll want them
        # to be null in the database
        if item_child_values["vendor_price"]:
            item_child_values["vendor_price"] = float(item_child_values["vendor_price"])

        if item_child_values["purchase_date"]:
            # This date will come as a timestamp from the frontend so it needs to be
            # converted to play nicely with MySQL's date format
            item_child_values["purchase_date"] = convert_javascript_date(
                item_child_values["purchase_date"]
            )

    except KeyError as err:
        current_app.log_exception(str(err))
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    try:
        query = """
            INSERT INTO item (barcode, available, moveable, location)
            VALUES (%(barcode)s, %(available)s, %(moveable)s, %(location)s)
        """

        cursor.execute(query, item_values)

        # Get the ID of the item we just inserted since it's used as a foreign key
        # for the 'item' row in the 'itemChild' table
        item_child_values["item_id"] = cursor.lastrowid

        query = """
            INSERT INTO itemChild (
                item,
                name,
                description,
                type,
                serial,
                vendorName,
                vendorPrice,
                purchaseDate,
                main
            )
            VALUES (
                %(item_id)s,
                %(name)s,
                %(description)s,
                %(type)s,
                %(serial)s,
                %(vendor_name)s,
                %(vendor_price)s,
                %(purchase_date)s,
                %(main)s
            )
        """

        cursor.execute(query, item_child_values)
        connection.commit()
    except mysql.connector.errors.Error as err:
        current_app.log_exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)

    # The item id is returned here so that the client can easily grab
    # it and use it to upload images immediately afterwards
    return jsonify({"itemId": item_child_values["item_id"]})


@inventory_blueprint.route("/<int:item_id>", methods=["PUT"])
@Database.with_connection
def update_item(item_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    put_data = request.get_json()

    if not put_data:
        return create_error_response("A body is required", 400)

    # Values relating to the
    name = put_data.get("name")
    description = put_data.get("description")
    item_type = put_data.get("type")
    serial = put_data.get("serial")
    vendor_name = put_data.get("vendorName")
    vendor_price = put_data.get("vendorPrice")
    purchase_date = put_data.get("purchaseDate")

    # Values relating to the 'item' table
    barcode = put_data.get("barcode")
    available = put_data.get("available")
    moveable = put_data.get("moveable")
    location = put_data.get("location")
    quantity = put_data.get("quantity")

    try:
        item_child_query = "UPDATE itemChild SET %s = %s WHERE ID = %s"

        # Because some of these values are strings while some are numbers, the string
        # values will need to be surrounded with quotes
        if name is not None:
            cursor.execute(item_child_query % ("name", f"'{name}'", item_id))

        if description is not None:
            cursor.execute(
                item_child_query % ("description", f"'{description}'", item_id)
            )

        if item_type is not None:
            cursor.execute(item_child_query % ("type", f"'{item_type}'", item_id))

        if serial is not None:
            cursor.execute(item_child_query % ("serial", f"'{serial}'", item_id))

        if vendor_name is not None:
            cursor.execute(
                item_child_query % ("vendorName", f"'{vendor_name}'", item_id)
            )

        if vendor_price is not None:
            cursor.execute(item_child_query % ("vendorPrice", vendor_price, item_id))

        if purchase_date is not None:
            purchase_date = convert_javascript_date(purchase_date)
            cursor.execute(
                item_child_query % ("purchaseDate", f"'{purchase_date}'", item_id)
            )

        item_query = """
            UPDATE item SET %s = %s
            WHERE ID = (
                SELECT item from itemChild WHERE ID = %s
            )
        """

        if barcode is not None:
            cursor.execute(item_query % ("barcode", f"'{barcode}'", item_id))

        if available is not None:
            cursor.execute(item_query % ("available", int(available), item_id))

        if moveable is not None:
            cursor.execute(item_query % ("moveable", int(moveable), item_id))

        if location is not None:
            cursor.execute(item_query % ("location", f"'{location}'", item_id))

        if quantity is not None:
            cursor.execute(item_query % ("quantity", quantity, item_id))

        connection.commit()
    except mysql.connector.errors.Error as err:
        connection.rollback()
        current_app.log_exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})
