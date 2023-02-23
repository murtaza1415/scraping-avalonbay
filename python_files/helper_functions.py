import os
import re
import random
import hashlib
import unicodedata
from pathlib import Path



# Absolut path to main BZP directory.
rb_directory = Path(__file__).parent.parent.parent.parent

# Absolute path to proxy file.
proxy_path = rb_directory / 'global_config/proxies.txt'



def get_image_filename(image_url):
    image_guid = hashlib.sha1(image_url.encode('utf-8')).hexdigest()
    return f'{image_guid}.jpg'



def get_proxy():
    # This function will return a random proxy from the proxies.txt file.
    with open(proxy_path, 'r') as f:
        lines = f.readlines()
        proxy = random.choice(lines)
        proxy = proxy.strip()
        ip_and_port = proxy.split('@')[1]
        server = 'http://' + ip_and_port
        username = proxy.split('@')[0].split(':')[0]
        password = proxy.split('@')[0].split(':')[1]
        url = f'http://{username}:{password}@{ip_and_port}'
    return [server, username, password, url]



def slugify(value, allow_unicode=False):
        """
        This function converts string to a valid filename.
        Taken from https://github.com/django/django/blob/master/django/utils/text.py
        Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
        dashes to single dashes. Remove characters that aren't alphanumerics,
        underscores, or hyphens. Convert to lowercase. Also strip leading and
        trailing whitespace, dashes, and underscores.
        """
        value = str(value)
        if allow_unicode:
            value = unicodedata.normalize('NFKC', value)
        else:
            value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
        value = re.sub(r'[^\w\s-]', '', value.lower())
        return re.sub(r'[-\s]+', '-', value).strip('-_')