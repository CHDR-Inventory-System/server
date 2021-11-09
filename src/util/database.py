import mysql.connector
from util.config import secrets
from flask import current_app


def _get_sql_connection():
    try:
        return mysql.connector.connect(
            host=secrets['DB_HOST'],
            user=secrets['DB_USERNAME'],
            password=secrets['DB_PASSWORD'],
            database=secrets['DB_DATABASE'],
            connection_timeout=secrets['DB_CONNECTION_TIMEOUT'],
        )
    except Exception as err:
        current_app.logger.exception(str(err))
        return None


class Database:
    """
    A wrapper class that manages the MySQL server connection. Note that
    after Database.execute_query() is called, you MUST call
    Database.close_connection() after you've closed the cursor that execute_query
    returns. This is so that there
    """

    connection = None

    @staticmethod
    def execute_query(sql_query, *variables):
        """
        Takes an sql query string and the variables that follow. Note the
        number of "%s" characters needs to match the number of variables
        passed to this function.
        """
        try:
            if Database.connection is None:
                Database.connection = _get_sql_connection()
            elif Database.connection.is_closed():
                Database.connection.reconnect(attempts=3, delay=5)

            cursor = Database.connection.cursor()
        except mysql.connector.OperationalError:
            # If the connection isn't available, try to reconnect
            Database.connection = _get_sql_connection()
            cursor = Database.connection.cursor()
        except Exception as err:
            current_app.logger.exception(str(err))
            return None

        cursor.execute(sql_query % variables)

        return cursor

    @staticmethod
    def close_connection():
        if Database.connection:
            Database.connection.close()
