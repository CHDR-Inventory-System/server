import mysql.connector
import mysql.connector.pooling
import functools
from util.config import secrets
from flask import current_app


_connection_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="database_pool",
    pool_size=5,
    # Timeout is given in seconds
    connection_timeout=30,
    host=secrets["DB_HOST"],
    user=secrets["DB_USERNAME"],
    password=secrets["DB_PASSWORD"],
    database=secrets["DB_DATABASE"],
)


class Database:
    """
    A wrapper class that manages the MySQL connection pool.
    """

    @staticmethod
    def with_connection(buffered=False, dictionary=True):
        """
        A decorator that passess a connection and cursor from the connection pool
        to the function in its kwargs. Functions that use this don't need to worry
        about closing the cursor or connection since it's done automatically in
        this decorator.
        """

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    connection = _connection_pool.get_connection()
                    cursor = connection.cursor(dictionary=dictionary, buffered=buffered)
                    return func(*args, cursor=cursor, connection=connection, **kwargs)
                except mysql.connector.Error as err:
                    current_app.logger.exception(str(err))
                    connection.rollback()
                finally:
                    cursor.close()
                    connection.close()

            return wrapper

        return decorator
