import os
import random
import hashlib



proxy_path = os.environ['proxy_file_path']



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


# example address: '1099 Admiral Ct. • San Bruno, CA 94066'
def split_address(address):
    if type(address) != str:
        return None
    
    address = address.strip()
    
    number_and_street = address.split('•',1)[0].strip()
    number = number_and_street.split(' ',1)[0].strip()
    street = number_and_street.split(' ',1)[1].strip()

    city_state_zip = address.split('•',1)[1].strip()
    city = city_state_zip.split(',',1)[0].strip()
    state = city_state_zip.split(',',1)[1].strip().split(' ',1)[0].strip()
    zip_code = city_state_zip.split(',',1)[1].strip().split(' ',1)[1].strip()

    # Manipulation.
    if number == 'One':
        number = '1'

    return number, street, city, state, zip_code