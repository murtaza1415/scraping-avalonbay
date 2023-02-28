from time import sleep
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
    
    email_recipient_list = config_global['email']['email_recipient']
    email_recipient_list = email_recipient_list.split(',')
    email_recipient_list = ', '.join(email_recipient_list)

    logging.info(f'Email will be sent to: {email_recipient_list}')

    yandex_user = 'scraper.apartment@yandex.com'
    yandex_password = 'fiawskomspgtkcpd'

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = yandex_user
    msg['To'] = email_recipient_list

    try:
        smtp_server = smtplib.SMTP_SSL('smtp.yandex.com', 465)
        #smtp_server = smtplib.SMTP_SSL('smtp.mailgun.org', 465)
        #smtp_server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp_server.ehlo()
        smtp_server.login(yandex_user, yandex_password)
        smtp_server.send_message(msg)
        smtp_server.quit()

        logging.info("Email sent.")
    except:
        logging.info("Unable to send email. ")
        logging.exception('exception: ')
