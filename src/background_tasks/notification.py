from flask import Flask
from util.email import Emailer
from smtplib import SMTPException
from flask import current_app
from util.database import Database
from datetime import datetime
import textwrap
from flask import jsonify


def create_alert_email_body(name: str, days: int, list):
    """
    This function is used to create the message that is set to be sent out to a
    user, in order to inform them of the items that are due.
    """
    days = abs(days)
    return textwrap.dedent(
        f"""
        Hello {name},

        We would like to advice you that your items: {list}. Will be due {days} days from today.

        Thank you.
        """
    )


@Database.with_connection()
def retrieve_user_credentials(user_id: int, item_id: int, **kwargs):
    """
    This function is used to search through the database for the credentials of the users
    and items that is checked out. Later then returned as a list
    """
    creds = []
    cursor = kwargs["cursor"]

    cursor.execute("SELECT * FROM users WHERE ID = %s", (user_id,))

    user = cursor.fetchone()
    email = user["email"]
    name = user["fullName"]

    cursor.execute("SELECT name FROM itemchild WHERE item = %s", (item_id,))

    item = cursor.fetchall()

    item_name = []
    for row in item:
        item_name.append(row["name"])

    creds = {"email": email, "name": name, "item_name": item_name}

    return creds


@Database.with_connection()
def due_date_iterator(app: Flask, **kwargs):
    cursor = kwargs["cursor"]
    # connection = kwargs["connection"]

    cursor.execute("SELECT ID, user, endDateTime, status, item from reservation")
    dates = cursor.fetchall()

    todays_date = datetime.now()

    # loops throught the due dates for all the reservations in the table
    # calculate the amount of days from the due date by using todays date
    for row in dates:
        days_to_duedate = row["endDateTime"] - todays_date

        # select item and the status of the of the reservation
        item_ID = row["item"]
        reservation_status = row["status"]
        # Select from items table the user the due date belongs to
        # check whether the items are moveable are not
        cursor.execute("SELECT * FROM item WHERE ID = %s", (item_ID,))
        item = cursor.fetchone()
        item_moveable = item["moveable"]

        user_id = row["user"]

        # If item is moveable then we check if the item is due in 1 day and send out an email
        if (item_moveable == 1) and (reservation_status == "Checked Out"):

            if days_to_duedate.days == 1:
                text = retrieve_user_credentials(user_id, item_ID)
                user_email = text["email"]
                user_name = text["name"]
                item_names = text["item_name"]

                body = create_alert_email_body(
                    user_name,
                    days_to_duedate.days,
                    item_names,
                )
                with app.app_context():
                    try:
                        Emailer.send_email(user_email, "Due date notification", body)

                        print(jsonify({"status": "Success"}))
                    except SMTPException as err:
                        current_app.logger.exception(str(err))
            elif days_to_duedate.days == 2:
                text = retrieve_user_credentials(user_id, item_ID)
                user_email = text["email"]
                user_name = text["name"]
                item_names = text["item_name"]

                body = create_alert_email_body(
                    user_name,
                    days_to_duedate.days,
                    item_names,
                )
                with app.app_context():
                    try:
                        Emailer.send_email(user_email, "Due date notification", body)

                        print(jsonify({"status": "Success"}))
                    except SMTPException as err:
                        current_app.logger.exception(str(err))
            elif days_to_duedate.days == 7:
                text = retrieve_user_credentials(user_id, item_ID)
                user_email = text["email"]
                user_name = text["name"]
                item_names = text["item_name"]

                body = create_alert_email_body(
                    user_name,
                    days_to_duedate.days,
                    item_names,
                )
                with app.app_context():
                    try:
                        Emailer.send_email(user_email, "Due date notification", body)

                        print(jsonify({"status": "Success"}))
                    except SMTPException as err:
                        current_app.logger.exception(str(err))
