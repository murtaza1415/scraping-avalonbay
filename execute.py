import os
import sys
import csv
import json
import logging
import asyncio
import aiohttp
from PIL import Image
from io import BytesIO
from time import sleep
from pathlib import Path
from urllib import parse
from parsel import Selector
from datetime import datetime
from logging.handlers import RotatingFileHandler
from playwright.async_api import async_playwright
from python_files.helper_functions import get_image_filename, get_proxy, split_address



this_directory = Path(__file__).parent
scraped_communities = []
community_csv_headers = ['community_id', 'name', 'community_url', 'street_number', 'street_name', 'city', 'state', 'zip_code']



async def get_locations(browser):
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

            logging.info(f'Number of cities: {len(city_a_list)}')
            
            city_urls = []
            for element in city_a_list:
                city_name = element.xpath('text()').get().strip()
                city_url = element.xpath('@href').get().strip('/#? ')
                if city_url.startswith('www'):
                    city_url = 'https://' + city_url
                city_state = city_url.split('/')[3].replace('-', ' ').title()
                city_urls.append(city_url)
                logging.info('\n')
                logging.info('-------------------------------------------')
                logging.info(f'City: {city_name} ({city_state})')
                await get_city(browser, city_url)
                logging.info('-------------------------------------------')

            break
        except:
            logging.info(f'Exception in get_locations')
            logging.info(f'Exception in attempt {attempt_number}')
            logging.exception('exception: ')
        


async def get_city(browser, city_url):
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

            logging.info(f'Number of communities: {num_communities}')

            communities = []
            for i in range(num_communities):
                community_card = community_cards.nth(i)
                community_a_element = community_card.locator('xpath=.//a[@class="community-card-link"]')
                community_name = await community_a_element.inner_text()
                community_url = await community_a_element.get_attribute('href')
                community_url = parse.urljoin(city_url, community_url)
                community_address = await community_card.locator('xpath=.//div[contains(@class,"community-card-name")]/following-sibling::div').inner_text()
                address_number, address_street, address_city, address_state, address_zip = split_address(community_address)
                communities.append({'community_name':community_name, 'community_url':community_url, 'address_city':address_city, 'address_state':address_state, 'address_street':address_street, 'address_number':address_number, 'address_zip':address_zip})
                logging.info(community_name)

            logging.info('\n\n')

            # Create communities file if it doesn't exist.
            if not Path.exists(this_directory / 'output/avalonbay_communities.csv'):
                with open(Path('output/avalonbay_communities.csv'), 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(community_csv_headers)

            # Read content from communities file.
            with open(Path(this_directory / 'output/avalonbay_communities.csv'), 'r', encoding='utf-8') as f:
                file_content = f.read()

            # Write all communties to csv file.
            with open(Path(this_directory / 'output/avalonbay_communities.csv'), 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                for community in communities:
                    community_url = community['community_url']
                    if community_url not in file_content:    # Do not add duplicates. Using community_url as unique identifier.
                        csv_row = ['', community['community_name'], community['community_url'], community['address_number'], community['address_street'], community['address_city'], community['address_state'], community['address_zip']]
                        writer.writerow(csv_row)
                    else:
                        logging.info(f'-- community is duplicate. not writing to file: {community_url}')

            for community in communities:
                if community['community_url'] not in scraped_communities:    # Do not scrape the same community more than once.
                    await get_community(page, community)
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
    


async def get_community(page, community):
    max_attempts = 2
    for attempt_number in range(1,max_attempts+1):
        try:
            community_url = community['community_url']
            community_name = community['community_name']
            community_state = community['address_state']
            community_city = community['address_city']

            community_data = [
                {
                    "additional_data": {
                        "original_url": community_url,
                        "apartment_name": community_name,
                        "apartment_id": "pending"
                    },
                    "apartment_address_data": {
                        "city": community['address_city'],
                        "state": community['address_state'],
                        "street_name": community['address_street'],
                        "street_number": community['address_number'],
                        "zip_code": community['address_zip']
                    },
                    "contact_information": {
                        "Office Hours": "pending",
                        "name": "pending",
                        "phone": "pending"
                    },
                    "listings": [],
                    "error": None
                }
            ]
            
            apartments_button = page.locator('xpath=//button[@id="apartment-toggle"]')

            await apartments_button.click()

            embedded_script = await page.locator('xpath=//script[@id="fusion-metadata"]').inner_html()
            json_start_index = embedded_script.index('{"itemsCount":')
            json_end_index = embedded_script.index(',"communityFilters"')
            embedded_json = embedded_script[json_start_index:json_end_index]
            embedded_json = json.loads(embedded_json)

            
            # TODO: Make sure that the matching of unit with community is reliable.
            unit_cards = page.locator(f'xpath=//div[@class="ant-card-body"][.//a[contains(@href,"{community_url}")]]')

            num_units = await unit_cards.count()

            logging.info(f'Num of units: {num_units}')

            for i in range(num_units):
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

                '''
                unit_adate = None
                url_split = unit_url.split('&')
                for s in url_split:
                    if 'moveInDate' in s:
                        s = s.replace('%2F','/')
                        unit_adate = s.split('=')[1]
                        break
                '''

                for unit_json in embedded_json['items']:
                    if unit_json['unitName'] == unit_number:
                        unit_beds = unit_json['bedroomNumber']
                        if unit_beds:    # Convert from integer to string.
                            unit_beds = str(unit_beds)
                        unit_baths = unit_json['bathroomNumber']
                        if unit_baths:    # Convert from integer to string.
                            unit_baths = str(unit_baths)
                        unit_sqft = unit_json['squareFeet']
                        if unit_sqft:    # Convert from integer to string.
                            unit_sqft = str(unit_sqft)
                        unit_floorplan_name = unit_json['floorPlan']['name']
                        unit_floorplan_name = unit_floorplan_name.split('-')[0]
                        unit_adate = None
                        if unit_json['furnishStatus'] == 'Designated':        # Furnished only apartments do not have unfurnished adate.
                            unit_adate = unit_json['availableDateFurnished']
                            unit_adate = unit_adate.split('T')[0]    # Remove time.
                        else:
                            unit_adate = unit_json['availableDateUnfurnished']
                            unit_adate = unit_adate.split('T')[0]    # Remove time.
                        unit_specials = []
                        if 'promotions' in unit_json:
                            for promo in unit_json['promotions']:
                                promo_title = promo['promotionTitle']
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
                logging.info(f'Unit no: {unit_number}')
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

                with open(Path(this_directory, f'output/{community_state}_{community_city}_{community_name}.json'), 'w', encoding='utf-8') as f:
                    json.dump(community_data, f)

                await download_image(unit_img_url)

            scraped_communities.append(community_url)
            
            break
        except:
            community_url = community['community_url']
            logging.info(f'Exception in get_community: {community_url}')
            logging.info(f'Exception in attempt {attempt_number}')
            logging.exception('exception: ')



async def download_image(url):
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
            proxy = get_proxy()
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


    # Start a browser session with playwright.
    playwright = await async_playwright().start()
    firefox = playwright.firefox
    browser = await firefox.launch(headless=True)

    start_time = datetime.now()

    await get_locations(browser)

    scraping_end_time = datetime.now()

    logging.info('\nScraping started: ' + str(start_time))
    logging.info('Scraping ended:   ' + str(scraping_end_time))
    #logging.info('Script ended:     ' + str(datetime.now()))

    # Close playwright properly.    
    await browser.close()
    await playwright.stop()



if __name__ == '__main__':
    asyncio.run(main())  # Start the asyncio event loop and run the main coroutine.