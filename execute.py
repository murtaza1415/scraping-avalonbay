import os
import sys
import csv
import json
import logging
import asyncio
import aiohttp
import configparser
from PIL import Image
from io import BytesIO
from time import sleep
from pathlib import Path
from urllib import parse
from parsel import Selector
from datetime import datetime
from logging.handlers import RotatingFileHandler
from playwright.async_api import async_playwright
from python_files import data_manipulation
from python_files.helper_functions import get_image_filename, get_proxy, slugify



this_directory = Path(__file__).parent

# Absolute path of configuration files.
config_file_local = this_directory / 'local_config/local_config.ini'
#config_file_global = rb_directory / 'global_config/global_config.ini'

scraped_communities = []
community_csv_headers = ['apartment_id', 'apartment_name', 'apartment_url', 'street_number', 'street_name', 'city', 'state', 'zip_code']



async def get_website(browser):
    max_attempts = 3
    for attempt_number in range(1,max_attempts+1):
        try:
            proxy = get_proxy()
            async with aiohttp.ClientSession() as session:
                async with session.get('https://www2.avaloncommunities.com/apartment-locations', timeout=60, proxy=proxy[3]) as response:
                    response_html = await response.text()
                    response_status = response.status

            selector = Selector(text=response_html)
            city_a_list = selector.xpath('//div[@class="col-sm"]/a')
            
            cities = []
            for element in city_a_list:
                city_name = element.xpath('text()').get().strip()
                city_url = element.xpath('@href').get().strip('/#? ')
                if city_url.startswith('www'):
                    city_url = 'https://' + city_url
                city_state = city_url.split('/')[3].replace('-', ' ').title().strip()
                cities.append({'url': city_url, 'name': city_name, 'state': city_state})

            logging.info(f'Cities found: {len(cities)}')

            tasks = set()
            for city in cities:
                task = asyncio.create_task(get_city(browser, city['url'], city['name'], city['state']))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            await asyncio.gather(*tasks)

            break
        except:
            logging.info(f'Exception in get_website')
            logging.info(f'Exception in attempt {attempt_number}')
            logging.exception('exception: ')
        


async def get_state(browser, input_state):
    logging.info(f'\nFetching state: {input_state}')
    max_attempts = 3
    for attempt_number in range(1,max_attempts+1):
        try:
            proxy = get_proxy()
            async with aiohttp.ClientSession() as session:
                async with session.get('https://www2.avaloncommunities.com/apartment-locations', timeout=60, proxy=proxy[3]) as response:
                    response_html = await response.text()
                    response_status = response.status

            selector = Selector(text=response_html)
            city_a_list = selector.xpath('//div[@class="col-sm"]/a')
            
            cities = []
            for element in city_a_list:
                city_name = element.xpath('text()').get().strip()
                city_url = element.xpath('@href').get().strip('/#? ')
                if city_url.startswith('www'):
                    city_url = 'https://' + city_url
                city_state = city_url.split('/')[3].replace('-', ' ').title().strip()
                if city_state.lower() == input_state.lower():
                    cities.append({'url': city_url, 'name': city_name, 'state': city_state})
            
            logging.info(f'Cities found: {len(cities)}')

            tasks = set()
            for city in cities:
                task = asyncio.create_task(get_city(browser, city['url'], city['name'], city['state']))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            await asyncio.gather(*tasks)

            break
        except:
            logging.info(f'Exception in get_state')
            logging.info(f'Exception in attempt {attempt_number}')
            logging.exception('exception: ')



async def get_city(browser, city_url, city_name, city_state):
    global semaphore_cities
    async with semaphore_cities:    # The semaphore controls how many cities can be scraped simultaneously.
        logging.info(f'\nFetching city: {city_name} ({city_state})\n')
        page = None
        context = None
        max_attempts = 3
        for attempt_number in range(1,max_attempts+1):
            try:
                proxy = get_proxy()
                context = await browser.new_context(
                    viewport = {'height': 757, 'width': 1368},
                    proxy = {
                        'server': proxy[0],
                        'username': proxy[1],
                        'password': proxy[2]
                    }
                )
                page = await context.new_page()

                # Abort image requests to reduce network usage.
                await page.route("**/*.{png,jpg,jpeg}", lambda route: route.abort())
                await page.route("**/*", lambda route: route.abort() if route.request.resource_type == "image"  else route.continue_())

                await page.goto(city_url, timeout=60000)

                community_button = page.locator('xpath=//button[@id="community-toggle"]')

                try:
                    await community_button.click()
                except:
                    has_404 = await page.locator('xpath=//h1[text()="404 Page Not Found"]').is_visible()
                    if has_404:
                        logging.info(f'-- Skipping city. Page not found: {city_url}')
                        await page.close()
                        await context.close()
                        return
                    else:
                        raise Exception('Community button not found.')

                community_cards = page.locator('xpath=//div[contains(@class,"community-card-wrapper")]')

                num_communities = await community_cards.count()

                logging.info(f'Number of communities: {num_communities}\n')

                communities = []
                for i in range(num_communities):
                    community_card = community_cards.nth(i)
                    community_a_element = community_card.locator('xpath=.//a[@class="community-card-link"]')
                    community_name = await community_a_element.inner_text()
                    community_url = await community_a_element.get_attribute('href')
                    community_url = parse.urljoin(city_url, community_url)
                    community_address = await community_card.locator('xpath=.//div[contains(@class,"community-card-name")]/following-sibling::div').inner_text()
                    address_number, address_street, address_city, address_state, address_zip = data_manipulation.split_address(community_address)
                    communities.append({'community_name':community_name, 'community_url':community_url, 'address_city':address_city, 'address_state':address_state, 'address_street':address_street, 'address_number':address_number, 'address_zip':address_zip})
                    #logging.info(community_name)

                for community in communities:
                    if community['community_url'] not in scraped_communities:    # Do not scrape the same community more than once.
                        scraped_communities.append(community['community_url'])
                        await get_community_from_url(browser, community['community_url'])
                    else:
                        logging.info(logging.info(f'-- community is duplicate. not scraping again: {community_url}'))

                await page.close()
                await context.close()

                break
            except:
                logging.info(f'Exception in get_city: {city_url}')
                logging.info(f'Exception in attempt {attempt_number}')
                logging.exception('exception: ')
                if page:
                    await page.close()
                if context:
                    await context.close()
    


async def get_community_from_url(browser, community_url):
    logging.info(f'\nFetching apartment: {community_url}')
    page = None
    context = None
    max_attempts = 3
    for attempt_number in range(1,max_attempts+1):
        try:
            proxy = get_proxy()
            context = await browser.new_context(
                viewport = {'height': 757, 'width': 1368},
                proxy = {
                    'server': proxy[0],
                    'username': proxy[1],
                    'password': proxy[2]
                }
            )
            page = await context.new_page()

            # Abort image requests to reduce network usage.
            await page.route("**/*.{png,jpg,jpeg}", lambda route: route.abort())
            await page.route("**/*", lambda route: route.abort() if route.request.resource_type == "image"  else route.continue_())

            await page.goto(community_url, timeout=60000)

            community_name = await page.locator('xpath=//h1[@id="cdph-title-id"]').inner_text()
            community_name = community_name.strip()
            
            community_address = await page.locator('xpath=//div[@id="cdph-address-id"]').inner_text()
            address_number, address_street, address_city, address_state, address_zip = data_manipulation.split_address(community_address)

            community_phone = await page.locator('xpath=//a[contains(@href,"tel:")]').first.inner_text()
            community_phone = data_manipulation.format_phone(community_phone)

            embedded_script = await page.locator('xpath=//script[@id="fusion-metadata"]').inner_html()
            
            json_start_index = embedded_script.index('[{"unitId":')
            json_end_index = embedded_script.index('}}],"promotions":')
            embedded_json_units = embedded_script[json_start_index:json_end_index] + '}}]'
            embedded_json_units = json.loads(embedded_json_units)

            json_start_index = embedded_script.index('}}],"promotions":')
            json_end_index = embedded_script.index(',"fees"')
            embedded_json_promos = embedded_script[json_start_index:json_end_index].replace('}}],"promotions":','',1)
            embedded_json_promos = json.loads(embedded_json_promos)

            time_start_index = embedded_script.index('"officeHours":[')
            time_end_index = embedded_script.index('],"policies":')
            times_string = embedded_script[time_start_index:time_end_index].replace('"officeHours":[','',1)
            times_string = times_string.replace('"','').replace(',',', ')

            community_data = [
                {
                    "additional_data": {
                        "original_url": community_url,
                        "apartment_name": community_name,
                        "apartment_id": "pending"
                    },
                    "apartment_address_data": {
                        "city": address_city,
                        "state": address_state,
                        "street_name": address_street,
                        "street_number": address_number,
                        "zip_code": address_zip
                    },
                    "contact_information": {
                        "Office Hours": times_string,
                        "name": community_name.replace(' ', '_'),
                        "phone": community_phone
                    },
                    "listings": [],
                    "error": None
                }
            ]

            # Create communities file if it doesn't exist.
            if not Path.exists(this_directory / 'output/_avalonbay_apartments.csv'):
                with open(Path('output/_avalonbay_apartments.csv'), 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(community_csv_headers)

            # Read all content from _avalonbay_apartments.csv
            with open(Path(this_directory / 'output/_avalonbay_apartments.csv'), 'r', encoding='utf-8') as f:
                file_content = f.read()

            # Write community data to _avalonbay_apartments.csv
            with open(Path(this_directory / 'output/_avalonbay_apartments.csv'), 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                if community_url not in file_content:    # Do not add duplicates. Using community_url as unique identifier.
                    csv_row = ['pending', community_name, community_url, address_number, address_street, address_city, address_state, address_zip]
                    writer.writerow(csv_row)
                else:
                    logging.info(f'-- community already in file: {community_url}')

            logging.info(f'Community: {community_name}')
            logging.info(f'Phone: {community_phone}')
            logging.info(f'Times: {times_string}\n')

            logging.debug('--- waiting for popup button')
            close_specials_button = page.locator('xpath=//span[@aria-label="close"]')
            if await close_specials_button.is_visible():
                await close_specials_button.click()
                logging.debug('--- closed popup')
            else:
                logging.debug('--- popup not found')

            logging.debug('--- waiting for load button')
            load_all_button = page.locator('xpath=//button[@id="load-all-units"]')
            if await load_all_button.is_visible():
                await load_all_button.click()
                logging.debug('--- clicked load button')
            else:
                logging.debug('--- load button not found')
            
            unit_cards = page.locator(f'xpath=//div[@class="ant-card-body"]')

            num_units = await unit_cards.count()

            logging.info(f'Num of units: {num_units}')
            
            for i in range(num_units):
                # Extract unit data from cards.
                unit_card = unit_cards.nth(i)
                title = await unit_card.locator('xpath=.//div[@class="ant-card-meta-title"]').inner_text()
                unit_number = title.split('\n')[0].replace('Apt.', '',1).strip()
                
                unit_specs = await unit_card.locator('xpath=.//div[@class="description"]').inner_text()
                unit_specs = unit_specs.split('•')
                
                unit_price = await unit_card.locator('xpath=.//span[contains(@class,"unit-price")]').inner_text()
                unit_url = await unit_card.locator('xpath=.//a[contains(@class,"unit-item-details-title")]').get_attribute('href')
                unit_url = unit_url.split('?')[0]
                
                unit_furnish_price = None
                furnish_div = unit_card.locator('xpath=.//div[contains(text(),"Furnished starting at")]')
                if await furnish_div.is_visible():
                    unit_furnish_price = await furnish_div.inner_text()
                    unit_furnish_price = unit_furnish_price.replace('Furnished starting at','').strip()

                unit_img_url = await unit_card.locator('xpath=.//div[contains(@class,"unit-image")]//img').first.get_attribute('src')
                unit_img_url = parse.urljoin(community_url, unit_img_url)  # Some image urls like '/pf/resources/img/notfound-borderless.png?d=80' need joining.
                unit_img_filename = get_image_filename(unit_img_url)

                # Extract remaining unit data from embedded_json_units
                for unit_json in embedded_json_units:
                    if '-' in unit_number:
                        unit_number_half = unit_number.split('-')[1]    # Remove number before dash. (remove the building number) 
                    else:
                        unit_number_half = unit_number
                    
                    if unit_json['name'] == unit_number_half:          # Look for relevant object in json that contains unit's data. Matching based on unit_number_half (without the building number).
                        unit_beds = unit_json['bedroom']
                        if unit_beds:    # Convert from integer to string.
                            unit_beds = str(unit_beds)
                        unit_baths = unit_json['bathroom']
                        if unit_baths:    # Convert from integer to string.
                            unit_baths = str(unit_baths)
                        unit_sqft = unit_json['squareFeet']
                        if unit_sqft:    # Convert from integer to string.
                            unit_sqft = str(unit_sqft)
                        
                        unit_floorplan_name = None
                        if 'floorplan' in unit_json:
                            unit_floorplan_name = unit_json['floorPlan']['name']
                            unit_floorplan_name = unit_floorplan_name.split('-')[0]
                        
                        unit_adate = None
                        if 'availableDate' in unit_json:
                            unit_adate = unit_json['availableDate']
                        else:
                            unit_adate = unit_json['furnishedAvailableDate']
                        unit_adate = data_manipulation.manipulate_date(unit_adate)
                        
                        unit_specials = []
                        if 'promotions' in unit_json:
                            for promo in unit_json['promotions']:
                                promo_id = promo['promotionId']
                                for promo2 in embedded_json_promos:   # Match promo id from embedded_json_units with promo id in embedded_json_promos to get promo title.
                                    if promo_id == promo2['promotionId']:
                                        promo_title = promo2['promotionTitle']
                                        unit_specials.append(promo_title)
                        unit_specials = '\n'.join(s for s in unit_specials)
                        
                        unit_package = None
                        if 'finishPackage' in unit_json:
                            package_name = unit_json['finishPackage']['name']
                            package_disc = unit_json['finishPackage']['description']
                            unit_package = package_name + ': ' + package_disc
                        
                        unit_virtual = None
                        if 'virtualTour' in unit_json:
                            unit_virtual = unit_json['virtualTour']['space']
                        
                        break

                logging.info('\n')
                logging.info(f'Full Unit no: {unit_number}')
                logging.info(f'Half unit no: {unit_number_half}')
                logging.info(f'Floorplan: {unit_floorplan_name}')
                logging.info(f'Spec list: {unit_specs}')
                logging.info(f'Beds: {unit_beds}')
                logging.info(f'Baths: {unit_baths}')
                logging.info(f'Sqft: {unit_sqft}')
                logging.info(f'Price: {unit_price}')
                logging.info(f'Fur price: {unit_furnish_price}')
                logging.info(f'Url: {unit_url}')
                logging.info(f'Image url: {unit_img_url}')
                logging.info(f'Virtual tour: {unit_virtual}')
                logging.info(f'Move in: {unit_adate}')
                logging.info(f'Specials: {unit_specials}')
                logging.info(f'Packages: {unit_package}')

                community_data[0]['listings'].append(
                    {
                        "available": unit_adate,
                        "bathrooms": unit_baths,
                        "bedrooms": unit_beds,
                        "floor_plan_name": unit_floorplan_name,
                        "rent": unit_price,
                        "furnishedRent": unit_furnish_price,
                        "sqft": unit_sqft,
                        "unitId": unit_number,
                        "unit_url": unit_url,
                        "image_url": unit_img_url,
                        "image_filename": unit_img_filename,
                        "virtual_tour": unit_virtual,
                        "specials": unit_specials,
                        "unit_details": unit_package
                    }
                )

                output_file_name = slugify(f'{address_state}_{address_city}_{community_name}').replace('-', '_') + '.json'
                with open(Path(this_directory, f'output/{output_file_name}'), 'w', encoding='utf-8') as f:
                    json.dump(community_data, f)

                await download_image(unit_img_url, proxy)

            await page.close()
            await context.close()
            
            break
        except:
            logging.info(f'Exception in get_community: {community_url}')
            logging.info(f'Exception in attempt {attempt_number}')
            logging.exception('exception: ')
            if page:
                await page.close()
            if context:
                await context.close()



async def download_image(url, proxy):
    # The purpose of this function is self evident from its name.
    if url == None:
        logging.info('Missing image.')
        return
    
    # Use image url to generate a unique file name.
    filename = get_image_filename(url)

    # Check if image is already saved in images folder. If not, download it to images folder.
    file_exists = os.path.exists(Path(this_directory, f'output/images/{filename}'))
    if not file_exists:
        logging.info('Downloading image...')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=70, proxy=proxy[3]) as response:
                    #response = requests.get(url, stream=True, timeout=40, proxies={'http': proxy[3], 'https': proxy[3]})
                    if response.status == 200:
                        im = Image.open(BytesIO(await response.read()))
                        rgb_im = im.convert('RGB')    # Convert image to jpg format.
                        rgb_im.save(Path(this_directory, f'output/images/{filename}'))
                        #new_images_list.append(filename)    # Append image filename to new_images_list.
                        logging.info('Image successfully downloaded.')
                    #del response
        except Exception:
            logging.exception('exception: ')
    else:
        logging.info('Image already exists.')



async def main():

    ######################################################
    # Setup logging.
    # Create output directory if it doesn't exist.
    if not Path.exists(this_directory / 'output'):
        Path.mkdir(this_directory / 'output')
    # Create logs directory if it doesn't exist.
    if not Path.exists(this_directory / 'output/logs'):
        Path.mkdir(this_directory / 'output/logs')

    # Write logs to both stdout and file. 
    # Note: Playwright does not use Python's logger. Workaround: Catch playwright's exceptions and log them in the 'except' block.
    logging.basicConfig(
        level=logging.DEBUG,
        format = '',
        handlers=[
            RotatingFileHandler(Path(this_directory, 'output/logs/log_file.log'), encoding='utf-8', maxBytes=1024*1024*30, backupCount=1),
            logging.StreamHandler(sys.stdout)
        ]    
    )
    ######################################################


    # Change name of terminal window.
    os.system("title " + 'AvalonBay scraper')
    # Create images directory if it doesn't exist.
    if not Path.exists(this_directory / 'output/images'):
        Path.mkdir(this_directory / 'output/images')

    # Load variables from config files. The purpose of having config files is so that the user can easily change the variables if needed.
    config_local = configparser.ConfigParser(interpolation=None)
    config_local.read(config_file_local)
    #config_global = configparser.ConfigParser(interpolation=None)    # Setting interpolation to None means "%" won't be treated as a special character.
    #config_global.read(config_file_global)

    global semaphore_cities      # Number of cities to scrape concurrently.
    concurrency = config_local['settings']['number_of_concurrent_cities']
    concurrency = int(concurrency)
    semaphore_cities = asyncio.Semaphore(concurrency)


    # Start a browser session with playwright.
    playwright = await async_playwright().start()
    firefox = playwright.firefox
    browser = await firefox.launch(headless=True)

    logging.info('\nWelcome to the AvalonBay scraper.\n')
    logging.info(f'Concurrency: Scraping {concurrency} cities at a time.\n')

    start_time = datetime.now()

    # Ask user to input mode. The crawler has 5 modes.
    while True:
        logging.info('Modes:\n\t1:  Scrape entire website.\n\t2:  Enter a state.\n\t3:  Enter apartment url.\n\t4:  Scrape states listed in "states_to_scrape.txt".\n\t5:  Scrape apartments listed in "apartments_to_scrape.txt"')
        mode = input('\nEnter mode:\n').lower()
        if mode == '1':
            # Scrape all cities.
            start_time = datetime.now()
            logging.info('Start time: ' + str(start_time))
            await get_website(browser)
            break
        elif mode == '2':
            # Scrape all cities from a particular state.
            input_state = input('Enter state name:\n').strip()
            start_time = datetime.now()
            logging.info('Start time: ' + str(start_time))
            await get_state(browser, input_state)
            break
        elif mode == '3':
            # Scrape a particular community from url.
            community_url = input('\nExample: https://www.avaloncommunities.com/california/berkeley-apartments/avalon-berkeley\n\nEnter apartment url:\n').split('?')[0].strip().strip('/')
            if 'https://www.avaloncommunities.com/' not in community_url:
                logging.info('\n-----------------------------------------------------------------------')
                logging.info('Invalid url entered.\n')
                continue
            start_time = datetime.now()
            logging.info('Start time: ' + str(start_time))
            community_url = community_url.split('#')[0].split('?')[0]
            await get_community_from_url(browser, community_url)
            break
        elif mode == '4':
            # Scrape states listed in states_to_scrape.txt
            start_time = datetime.now()
            logging.info('Start time: ' + str(start_time))
            with open(Path(this_directory, 'input/states_to_scrape.txt'), 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if len(line) > 1:
                        input_state = line
                        await get_state(browser, input_state)
            break
        elif mode == '5':
            # Scrape apartments listed in apartments_to_scrape.txt
            start_time = datetime.now()
            logging.info('Start time: ' + str(start_time))
            with open(Path(this_directory, 'input/apartments_to_scrape.txt'), 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if len(line) > 1:
                        community_url = line
                        await get_community_from_url(browser, community_url)
            break
        else:
            logging.info('\n-----------------------------------------------------------------------')
            logging.info('Invalid mode entered.\n')


    scraping_end_time = datetime.now()

    logging.info('\nScraping started: ' + str(start_time))
    logging.info('Scraping ended:   ' + str(scraping_end_time))
    #logging.info('Script ended:     ' + str(datetime.now()))

    # Close playwright properly.    
    await browser.close()
    await playwright.stop()


if __name__ == '__main__':
    asyncio.run(main())  # Start the asyncio event loop and run the main coroutine.