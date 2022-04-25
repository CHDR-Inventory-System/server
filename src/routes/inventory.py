import mysql.connector
import os
from io import BytesIO
from flask import Blueprint, jsonify, current_app, request
from flask_jwt_extended import jwt_required
from util.database import Database
from util.response import create_error_response, convert_javascript_date
from util.request import require_roles
from util.config import secrets
from util.imaging import compress_image
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
import base64

inventory_blueprint = Blueprint("inventory", __name__)
VALID_IMAGE_EXTENSIONS = {"jpg", "png", "jpeg"}


@Database.with_connection()
def query_by_id(item_id, **kwargs):
    cursor = kwargs["cursor"]

    cursor.execute("SELECT * from itemImage WHERE itemChild = %s", (item_id,))
    images = cursor.fetchall()

    query = """
        SELECT
            A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
        FROM itemChild AS A
        LEFT JOIN item AS B on A.item = B.ID
        WHERE A.ID = %(item_id)s
        UNION
        SELECT
            A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
        FROM itemChild AS A
        LEFT JOIN item AS B on A.item = B.ID
        WHERE A.ID = %(item_id)s
    """

    cursor.execute(query, {"item_id": item_id})
    result = cursor.fetchone()

    if not result:
        return None

    result["moveable"] = bool(result["moveable"])
    result["available"] = bool(result["available"])
    result["main"] = bool(result["main"])
    result["images"] = images
    result["children"] = []

    if result["main"]:
        query = """
            SELECT
                A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
            FROM itemChild AS A
            LEFT JOIN item AS B on A.item = B.ID
            WHERE A.item = %(item)s AND A.main = 0
            UNION
            SELECT
                A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
            FROM itemChild AS A
            LEFT JOIN item AS B on A.item = B.ID
            WHERE A.item = %(item)s AND A.main = 0
        """

        cursor.reset()
        cursor.execute(query, {"item": result["item"]})
        children = cursor.fetchall()

        for child in children:
            cursor.execute(
                "SELECT * FROM itemImage WHERE itemChild = %s" % (child["ID"],)
            )

            child["images"] = cursor.fetchall()
            child["moveable"] = bool(child["moveable"])
            child["available"] = bool(child["available"])
            child["main"] = bool(child["main"])

        result["children"] = children

    return result


@inventory_blueprint.route("/", methods=["GET"])
@jwt_required()
@Database.with_connection()
def get_all(**kwargs):
    cursor = kwargs["cursor"]

    try:
        cursor.execute("SELECT * FROM itemImage")
        images = cursor.fetchall()

        # Since MySQL doesn't have full join, we'll have to do a left join
        # unioned with a right join. Because that returns everything from
        # both tables, we need to make sure columns with the same name
        # aren't included twice.
        cursor.execute(
            """
            SELECT
                A.barcode, A.available, A.moveable, A.location, A.quantity,
                A.retiredDateTime, B.*
            FROM item AS A
            LEFT JOIN itemChild AS B on B.item = A.ID
            UNION
            SELECT
                A.barcode, A.available, A.moveable, A.location, A.quantity,
                A.retiredDateTime, B.*
            FROM item AS A
            RIGHT JOIN itemChild B on B.item = A.ID
            """
        )
        all_items = cursor.fetchall()
        main_items = [item for item in all_items if bool(item["main"])]
        child_items = [item for item in all_items if not bool(item["main"])]
        response = []

        # Add all images to each item
        for row in main_items + child_items:
            row["images"] = [
                image for image in images if image["itemChild"] == row["ID"]
            ]

            # These booleans are stored as bits in the database so we
            # need to convert them to boleans before sending the response
            row["available"] = bool(row["available"])
            row["moveable"] = bool(row["moveable"])
            row["main"] = bool(row["main"])

        # Add the child to the main items if the main item has children
        for row in main_items:
            row["children"] = [
                child for child in child_items if child["item"] == row["item"]
            ]
            response.append(row)

        return jsonify(response)

    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/<int:item_id>", methods=["DELETE"])
@require_roles(["admin", "super"])
@Database.with_connection()
def delete_item(item_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    # Before we delete the item, we first need to delete the image files from the
    # server (including child images if the item we're deleting is a parent item).
    # If this step fails for some reason, we can still try to delete the item
    # from the database
    try:
        cursor.execute("SELECT item, main FROM itemChild WHERE ID = %s" % (item_id,))

        item = cursor.fetchone()

        if item["main"]:
            cursor.execute(
                "SELECT imagePath from itemImage WHERE itemChild = %s", (item_id,)
            )
            image_paths = [row["imagePath"] for row in cursor.fetchall()]

            for image_path in image_paths:
                try:
                    os.remove(image_path)
                except (IsADirectoryError, FileNotFoundError) as err:
                    current_app.logger.exception(str(err))

            cursor.execute("DELETE FROM reservation WHERE item = %s", (item["item"],))

    except Exception as err:
        current_app.logger.exception(str(err))

    try:
        cursor.execute("SELECT item, main FROM itemChild WHERE ID = %s" % (item_id,))

        item = cursor.fetchone()

        # If this is the main item, we also need to delete its associated children
        if item["main"]:
            cursor.execute(
                "DELETE FROM itemChild WHERE item = %s AND main = 0" % (item["item"])
            )

        cursor.execute("DELETE FROM itemChild WHERE ID = %s" % (item_id,))

        connection.commit()
    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@inventory_blueprint.route("/<int:item_id>", methods=["GET"])
@jwt_required()
def get_item_by_id(item_id):
    try:
        item = query_by_id(item_id)

        if not item:
            return create_error_response("Item not found", 404)

        return jsonify(item)
    except mysql.connector.Error as err:
        current_app.log_exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/search", methods=["GET"])
@jwt_required()
@Database.with_connection()
def get_item_by_name(**kwargs):
    cursor = kwargs["cursor"]
    query = """
        SELECT
            A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
        FROM itemChild AS A
        LEFT JOIN item AS B on A.item = B.ID
        WHERE name LIKE %(item_name)s AND A.main = 1
        UNION
        SELECT
            A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
        FROM itemChild AS A
        RIGHT JOIN item AS B on A.item = B.ID
        WHERE name LIKE %(item_name)s AND A.main = 1
    """
    item_name = request.args.get("query", default="", type=str)

    try:
        cursor.execute(query, {"item_name": f"%{item_name}%"})
        items = cursor.fetchall()
        response = []

        for row in items:
            row["available"] = bool(row["available"])
            row["moveable"] = bool(row["moveable"])
            row["main"] = bool(row["main"])

            cursor.execute(
                "SELECT * FROM itemImage WHERE itemChild = %s" % (row["ID"],)
            )
            row["images"] = cursor.fetchall()

            query = """
                SELECT
                    A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
                FROM itemChild AS A
                LEFT JOIN item AS B on A.item = B.ID
                WHERE item = %(item)s AND A.main = 0
                UNION
                SELECT
                    A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
                FROM itemChild AS A
                RIGHT JOIN item AS B on A.item = B.ID
                WHERE item = %(item)s AND A.main = 0
            """
            cursor.execute(query, {"item": row["item"]})

            row["children"] = cursor.fetchall()

            for child in row["children"]:
                child["moveable"] = bool(child["moveable"])
                child["main"] = bool(child["main"])
                child["available"] = bool(child["available"])

                cursor.execute(
                    "SELECT * FROM itemImage WHERE itemChild = %s" % (child["ID"],)
                )
                child["images"] = cursor.fetchall()

            response.append(row)

        return jsonify(response)
    except mysql.connector.Error as err:
        current_app.log_exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/barcode/<barcode>", methods=["GET"])
@jwt_required()
@Database.with_connection()
def get_item_by_barcode(barcode, **kwargs):
    cursor = kwargs["cursor"]
    query = """
        SELECT
            A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
        FROM itemChild AS A
        LEFT JOIN item AS B on A.item = B.ID
        WHERE B.barcode = %(barcode)s
        UNION
        SELECT
            A.*, B.barcode, B.available, B.moveable, B.location, B.quantity
        FROM itemChild AS A
        RIGHT JOIN item AS B on A.item = B.ID
        WHERE B.barcode = %(barcode)s
    """

    try:
        cursor.execute(query, {"barcode": barcode})
        all_items = cursor.fetchall()

        if len(all_items) == 0:
            return create_error_response(f"No item found with barcode {barcode}", 404)

        # Find the first parent item that has this barcode and add children to
        # the main item if it has children. This assumes all barcodes are unique
        main_item = next(item for item in all_items if bool(item["main"]))
        child_items = [item for item in all_items if not bool(item["main"])]

        for row in child_items + [main_item]:
            cursor.execute(
                "SELECT * FROM itemImage WHERE itemChild = %s" % (row["ID"],)
            )
            row["images"] = cursor.fetchall()
            row["children"] = []
            row["available"] = bool(row["available"])
            row["moveable"] = bool(row["moveable"])
            row["main"] = bool(row["main"])

        main_item["children"] = [
            child for child in child_items if child["item"] == row["item"]
        ]

        return jsonify(main_item)
    except mysql.connector.Error as err:
        current_app.log_exception(str(err))
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/<int:item_id>/uploadImage", methods=["POST"])
@require_roles(["admin", "super"])
@Database.with_connection()
def upload_image(item_id, **kwargs):
    """
    This route can receive either a JavaScript FormData object with the key
    'image' or a JSON object with the name of the image and the image data
    encoded as a base64 string
    """
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json() or {}

    try:
        # Check to see if we received a FormData object
        image = request.files["image"]
    except KeyError:
        # No form data was passed so check the request body instead
        pass

    try:
        # We didn't get a FormData object so encode the base64 image as a
        # byte stream and save it
        filename = post_data["filename"]
        content_type = "image/png" if filename.endswith("png") else "image/jpeg"
        file_data = BytesIO(base64.b64decode(post_data["image"]))

        image = FileStorage(
            stream=file_data,
            filename=filename,
            content_type=content_type,
        )
    except KeyError:
        return create_error_response("An image is required", 400)
    except Exception:
        return create_error_response("An unexpected error occurred", 500)

    # Make sure we only received images with valid extensions
    if image.filename.split(".")[-1] not in VALID_IMAGE_EXTENSIONS:
        extensions = ", ".join(VALID_IMAGE_EXTENSIONS)
        return create_error_response(f"Extension must be one of {extensions}", 400)

    try:
        os.makedirs(current_app.config["IMAGE_FOLDER"], exist_ok=True)

        filename = secure_filename(image.filename)

        image_path = os.path.join(current_app.config["IMAGE_FOLDER"], filename)
        image_url = f"{secrets['BASE_URL']}/images/{filename}"

        query = """
            INSERT INTO itemImage (itemChild, imagePath, imageURL)
            VALUES (%s, %s, %s)
        """
        cursor.execute(query, (item_id, image_path, image_url))

        image.save(image_path)
        compress_image(image_path)

        connection.commit()

        return jsonify({"imageID": cursor.lastrowid})
    except Exception as err:
        current_app.logger.exception(str(err))
        connection.rollback()
        return create_error_response(
            "An unexpected error occurred uploading image", 500
        )


@inventory_blueprint.route("/image/<int:image_id>", methods=["DELETE"])
@require_roles(["admin", "super"])
@Database.with_connection()
def delete_image(image_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    try:
        cursor.execute("SELECT imagePath FROM itemImage WHERE ID = %s" % (image_id,))

        file = cursor.fetchone()

        if not file:
            return create_error_response("Image not found", 404)

        cursor.execute("DELETE FROM itemImage WHERE ID = %s" % (image_id,))
        connection.commit()
    except mysql.connector.errors.Error as err:
        connection.rollback()
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    try:
        os.remove(file["imagePath"])
    except (IsADirectoryError, FileNotFoundError) as err:
        current_app.logger.exception(str(err))

    return jsonify({"status": "Success"})


@inventory_blueprint.route("/add", methods=["POST"])
@require_roles(["admin", "super"])
@Database.with_connection()
def add_item(**kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    post_data = request.get_json()
    item_values = {}

    try:
        # These values are required so we need to check for any key errors.
        # This will be inserted into the item table
        item_values["barcode"] = post_data["barcode"]
        item_values["available"] = int(post_data["available"])
        item_values["moveable"] = int(post_data["moveable"])
        item_values["location"] = post_data["location"]
    except KeyError as err:
        current_app.log_exception(str(err))
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    item_child_values = {}

    try:
        # These values will be inserted into the item child table
        item_child_values["name"] = post_data["name"]
        item_child_values["type"] = post_data["type"]
        item_child_values["main"] = True

        # Using 'get' for these parameters so that they can default
        # to None (NULL in mysql's case) when inserted without a value
        item_child_values["description"] = post_data.get("description")
        item_child_values["vendor_name"] = post_data.get("vendorName")
        item_child_values["purchase_date"] = post_data.get("purchaseDate")
        item_child_values["vendor_price"] = post_data.get("vendorPrice")
        item_child_values["serial"] = post_data.get("serial")

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

        inserted_item = query_by_id(cursor.lastrowid)

        return jsonify(inserted_item)
    except mysql.connector.errors.Error as err:
        current_app.log_exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/<int:item_id>/addChild", methods=["POST"])
@require_roles(["admin", "super"])
@Database.with_connection()
def add_child_item(item_id, **kwargs):
    """
    NOTE: Here, 'item_id' refers to the ID of the item in the item table
    """
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json()
    values = {}

    try:
        values["name"] = post_data["name"]
        values["type"] = post_data["type"]
    except KeyError as err:
        return create_error_response(f"Parameter {err.args[0]} is required", 400)

    values["main"] = False
    values["item_id"] = item_id
    values["description"] = post_data.get("description")
    values["serial"] = post_data.get("serial")
    values["vendor_name"] = post_data.get("vendorName")
    values["vendor_price"] = post_data.get("vendorPrice")
    values["purchase_date"] = post_data.get("purchaseDate")

    if values["purchase_date"]:
        values["purchase_date"] = convert_javascript_date(values["purchase_date"])

    try:
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

        cursor.execute(query, values)
        connection.commit()

        inserted_item = query_by_id(cursor.lastrowid)

        return jsonify(inserted_item)
    except mysql.connector.errors.Error as err:
        current_app.log_exception(str(err))
        connection.rollback()
        return create_error_response("An unexpected error occurred", 500)


@inventory_blueprint.route("/<int:item_id>", methods=["PUT"])
@require_roles(["admin", "super"])
@Database.with_connection()
def update_item(item_id, **kwargs):
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]

    put_data = request.get_json()

    if not put_data:
        return create_error_response("A body is required", 400)

    # Values from the 'itemChild' table
    name = put_data.get("name")
    description = put_data.get("description")
    item_type = put_data.get("type")
    serial = put_data.get("serial")
    vendor_name = put_data.get("vendorName")
    vendor_price = put_data.get("vendorPrice")
    purchase_date = put_data.get("purchaseDate")

    # Values from the 'item' table
    barcode = put_data.get("barcode")
    available = put_data.get("available")
    moveable = put_data.get("moveable")
    location = put_data.get("location")
    quantity = put_data.get("quantity")

    try:
        if name is not None:
            cursor.execute(
                "UPDATE itemChild SET name = %s WHERE ID = %s", (name, item_id)
            )

        if description is not None:
            cursor.execute(
                "UPDATE itemChild SET description = %s WHERE ID = %s",
                (description, item_id),
            )

        if item_type is not None:
            cursor.execute(
                "UPDATE itemChild SET type = %s WHERE ID = %s", (item_type, item_id)
            )

        if serial is not None:
            cursor.execute(
                "UPDATE itemChild SET serial = %s WHERE ID = %s", (serial, item_id)
            )

        if vendor_name is not None:
            cursor.execute(
                "UPDATE itemChild SET vendorName = %s WHERE ID = %s",
                (vendor_name, item_id),
            )

        if vendor_price is not None and vendor_price != "":
            cursor.execute(
                "UPDATE itemChild SET vendorPrice = %s WHERE ID = %s",
                (vendor_price, item_id),
            )

        if purchase_date is not None:
            purchase_date = convert_javascript_date(purchase_date)
            cursor.execute(
                "UPDATE itemChild SET purchaseDate = %s WHERE ID = %s",
                (purchase_date, item_id),
            )

        if barcode is not None:
            cursor.execute(
                """
                UPDATE item SET barcode = %s
                WHERE ID = (SELECT item from itemChild WHERE ID = %s)
                """,
                (barcode, item_id),
            )

        if available is not None:
            cursor.execute(
                """
                UPDATE item SET available = %s
                WHERE ID = (SELECT item from itemChild WHERE ID = %s)
                """,
                (int(available), item_id),
            )

        if moveable is not None:
            cursor.execute(
                """
                UPDATE item SET moveable = %s
                WHERE ID = (SELECT item from itemChild WHERE ID = %s)
                """,
                (int(moveable), item_id),
            )

        if location is not None:
            cursor.execute(
                """
                UPDATE item SET location = %s
                WHERE ID = (SELECT item from itemChild WHERE ID = %s)
                """,
                (location, item_id),
            )

        # Quantity is a special case. If the quantity is 0, the item's status should
        # be marked as unavailable. If the quantity is > 0, the item's status should
        # be marked as available
        if quantity is not None:
            values = {
                "quantity": quantity,
                "item_id": item_id,
                "available": 0 if quantity == 0 else 1,
            }

            cursor.execute(
                """
                UPDATE item
                SET quantity = %(quantity)s, available = %(available)s
                WHERE ID = (SELECT item from itemChild WHERE ID = %(item_id)s)
                """,
                values,
            )

        connection.commit()
    except mysql.connector.errors.Error as err:
        connection.rollback()
        current_app.log_exception(str(err))
        return create_error_response("An unexpected error occurred", 500)

    return jsonify({"status": "Success"})


@inventory_blueprint.route("/<int:item_id>/retire", methods=["PUT"])
@require_roles(["admin", "super"])
@Database.with_connection()
def retire_item(item_id, **kwargs):
    """
    Handles retiring an item. This route takes "date" as a parameter. If
    "date" is null then the item's retired status will be removed.
    """
    cursor = kwargs["cursor"]
    connection = kwargs["connection"]
    post_data = request.get_json() or {}

    try:
        retired_date = post_data["date"]

        if retired_date is not None:
            retired_date = convert_javascript_date(retired_date)

    except KeyError:
        return create_error_response("Parameter date is required", 400)

    try:
        cursor.execute("SELECT item FROM itemChild WHERE ID = %s" % (item_id,))

        item = cursor.fetchone()

        if not item:
            return create_error_response("Item not found", 404)

        params = (retired_date, item["item"])

        cursor.execute("UPDATE item SET retiredDateTime = %s WHERE ID = %s", params)

        connection.commit()

        return jsonify({"status": "Success"})
    except mysql.connector.errors.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)
