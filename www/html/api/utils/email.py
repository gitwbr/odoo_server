from flask_mail import Message
from config import logger

def send_email(mail, subject, recipient, body):
    try:
        msg = Message(subject,
                     sender=mail.app.config['MAIL_USERNAME'],
                     recipients=[recipient])
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        logger.error(f'發送郵件失敗: {str(e)}')
        return False 