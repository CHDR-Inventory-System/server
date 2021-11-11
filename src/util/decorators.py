from util.database import Database


def auto_close_db_connetion(func):
    """
    A decorator that ensures a connection to the MySQL database
    is always closed once a function returns
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, *kwargs)
        finally:
            Database.close_connection()

    return wrapper
