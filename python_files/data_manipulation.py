import logging



def manipulate_date(date):
    # Remove time.
    date = date.split(' ')[0]
    
    month,day,year = date.split('/')
    
    # Prefix zero to month and day to make them two digit.
    if len(month) == 1:
        month = '0' + month
    if len(day) == 1:
        day = '0' + day
    
    # yyyy-mm-dd    
    date = year + '-' + month + '-' + day

    return date



def split_address(address):
    # example address: '1099 Admiral Ct. • San Bruno, CA 94066'
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



def format_phone(phone_number):
    phone_number = ''.join(char for char in phone_number if char.isdecimal())

    if len(phone_number) != 10:
        logging.info(f'--unexpected phone numbr: {phone_number}')
        return None
    
    # ddd-ddd-dddd
    phone_number = phone_number[0:3] + '-' + phone_number[3:6] + '-' + phone_number[6:]

    return phone_number

    
