from flask_mail import Mail, Message
from util.config import secrets


class Emailer:
    _mail = Mail()

    @staticmethod
    def init(app):
        Emailer._mail.init_app(app)

    @staticmethod
    def send_email(recipient: str, subject: str, body: str):
        """
        Sends an email to the specified recipient.
        Throws SMTPException on failure
        """
        message = Message(
            recipients=[recipient],
            subject=subject,
            body=body,
            sender=secrets["EMAIL_USERNAME"],
        )
        Emailer._mail.send(message)
