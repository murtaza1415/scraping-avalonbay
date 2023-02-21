import smtplib
import logging
import configparser
from pathlib import Path
from email.message import EmailMessage



# Absolut path to RebtalBeast main directory.
rb_directory = Path(__file__).parent.parent.parent.parent

# Absolute path of configuration file.
config_file_global = rb_directory / 'global_config/global_config.ini'



def send_email(subject, body):
    # Load variables from config files. The purpose of having config files is so that the user can easily change the variables if needed.
    config_global = configparser.ConfigParser(interpolation=None)
    config_global.read(config_file_global)
    
    email_recipient = config_global['email']['email_recipient']

    yandex_user = 'scraper.rb@yandex.com'
    yandex_password = 'zqP7H#r8Ytrf&A8'

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = yandex_user
    msg['To'] = email_recipient

    try:
        smtp_server = smtplib.SMTP_SSL('smtp.yandex.com', 465)
        smtp_server.ehlo()
        smtp_server.login(yandex_user, yandex_password)
        smtp_server.send_message(msg)
        smtp_server.quit()
        logging.info("Email sent.")
    except Exception as ex:
        logging.info("Unable to send email. ",ex)
