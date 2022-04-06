from util.database import Database
from ics import Calendar, Event
from dateutil import tz


@Database.with_connection()
def create_calendar_for_reservation(reservation, **kwargs):
    """
    Takes details from a given reservation and returns a
    Calendar object containing the reservation details.
    """

    cursor = kwargs["cursor"]
    date_format = "%Y-%m-%d %H:%M:%S"
    iid = reservation["item"]["item"]
    start = reservation["startDateTime"]
    end = reservation["endDateTime"]

    start = start.replace(tzinfo=tz.gettz())
    end = end.replace(tzinfo=tz.gettz())

    start = start.astimezone(tz.tzutc())
    end = end.astimezone(tz.tzutc())

    query = f"SELECT name FROM itemChild WHERE item = {iid} AND main = 1"
    cursor.execute(query)
    itemName = cursor.fetchone()
    itemName = itemName["name"]

    event = Event()
    calendar = Calendar()

    event.name = "CHDR Reservation"
    event.begin = start.strftime(date_format)
    event.end = end.strftime(date_format)
    event.description = f"UCF CHDR Reservation: {itemName}"

    calendar.events.add(event)

    return calendar
