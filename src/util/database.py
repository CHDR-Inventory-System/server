import mysql.connector
import functools
from util.config import secrets
from flask import current_app

POOL_NAME = "database_pool"


class Database:
    """
    A wrapper class that manages the MySQL connection pool.
    """

    connection_pool = mysql.connector.connect(
        pool_name=POOL_NAME,
        pool_size=5,
        connection_timeout=5,
        host=secrets["DB_HOST"],
        user=secrets["DB_USERNAME"],
        password=secrets["DB_PASSWORD"],
        database=secrets["DB_DATABASE"],
    )

    @staticmethod
    def with_connection(func):
        """
        A decorator that passess a connection and cursor from the connection pool
        to the function in its kwargs. Functions that use this don't need to worry
        about closing the cursor or connection since it's done automatically in
        this decorator.
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                connection = mysql.connector.connect(pool_name=POOL_NAME)
                cursor = connection.cursor(dictionary=True)
                return func(*args, cursor=cursor, connection=connection, **kwargs)
            except mysql.connector.Error as err:
                current_app.logger.exception(str(err))
                connection.rollback()
            finally:
                cursor.close()
                connection.close()

        return wrapper
