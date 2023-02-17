import csv
import json
from time import sleep
from pathlib import Path
from urllib import parse
import asyncio
import aiohttp
from python_files.helper_functions import get_proxy, split_address
from parsel import Selector
from playwright.async_api import async_playwright


this_directory = Path(__file__).parent
community_csv_headers = ['community_id', 'name', 'community_url', 'street_number', 'street_name', 'city', 'state', 'zip_code']


async def get_locations(browser):
    proxy = get_proxy()
    async with aiohttp.ClientSession() as session:
        async with session.get('https://www2.avaloncommunities.com/apartment-locations', timeout=60, proxy=proxy[3]) as response:
            response_html = await response.text()
            response_status = response.status

    selector = Selector(text=response_html)
    city_a_list = selector.xpath('//div[@class="col-sm"]/a')
    
    city_urls = []
    for element in city_a_list:
        city_name = element.xpath('text()').get().strip()
        city_url = element.xpath('@href').get().strip('/#? ')
        if city_url.startswith('www'):
            city_url = 'https://' + city_url
        city_state = city_url.split('/')[3].replace('-', ' ').title()
        city_urls.append(city_url)
        print('---------------------------------')
        print(city_state)
        print(city_name)
        await get_city(browser, city_url)
        print('---------------------------------')
        

    #print(response_status)
    #print(response_html)


async def get_city(browser, city_url):
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
            print(f'-- Skipping city. Page not found: {city_url}')
            await page.close()
            await context.close()
            return
        else:
            raise Exception('Community button not found.')

    community_cards = page.locator('xpath=//div[contains(@class,"community-card-wrapper")]')

    num_communities = await community_cards.count()

    print(f'Number of communities: {num_communities}')

    communities = []
    for i in range(num_communities):
        community_card = community_cards.nth(i)
        community_a_element = community_card.locator('xpath=.//a[@class="community-card-link"]')
        community_name = await community_a_element.inner_text()
        community_url = await community_a_element.get_attribute('href')
        community_url = parse.urljoin(city_url, community_url)
        community_address = await community_card.locator('xpath=.//div[contains(@class,"community-card-name")]/following-sibling::div').inner_text()
        address_city, address_state, address_street, address_number, address_zip = split_address(community_address)
        communities.append([community_name, community_url, address_city, address_state, address_street, address_number, address_zip])
        print(community_name)

    print('\n\n')

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
            community_url = community[1]
            if community_url not in file_content:    # Do not add duplicates. Using community_url as unique identifier.
                writer.writerow(['']+community)
            else:
                print(f'-- community is duplicate. not writing to file: {community_url}')

    for community in communities:
        await get_community(page, community[1], community[0])

    await page.close()
    await context.close()

    sleep(2)
    


async def get_community(page, community_url, community_name):
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

    print(f'Num of units: {num_units}')

    for i in range(num_units):
        unit_card = unit_cards.nth(i)
        title = await unit_card.locator('xpath=.//div[@class="ant-card-meta-title"]').inner_text()
        unit_number = title.split('\n')[0].replace('Apt.', '',1).strip()
        
        unit_specs = await unit_card.locator('xpath=.//div[@class="description"]').inner_text()
        unit_specs = unit_specs.split('•')
        
        unit_price = await unit_card.locator('xpath=.//span[contains(@class,"unit-price")]').inner_text()
        unit_url = await unit_card.locator('xpath=.//a[contains(@class,"unit-item-details-title")]').get_attribute('href')
        
        unit_furnish_price = None
        furnish_div = unit_card.locator('xpath=.//div[contains(text(),"Furnished starting at")]')
        if await furnish_div.is_visible():
            unit_furnish_price = await furnish_div.inner_text()
            unit_furnish_price = unit_furnish_price.replace('Furnished starting at','').strip()

        unit_image_url = await unit_card.locator('xpath=.//div[contains(@class,"unit-image")]//img').first.get_attribute('src')
        unit_image_url = parse.urljoin(community_url, unit_image_url)  # For image urls like '/pf/resources/img/notfound-borderless.png?d=80'

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
                unit_baths = unit_json['bathroomNumber']
                unit_sqft = unit_json['squareFeet']
                unit_adate = None
                if unit_json['furnishStatus'] == 'Designated':        # Furnished only apartments do not have unfurnished adate.
                    unit_adate = unit_json['availableDateFurnished']
                else:
                    unit_adate = unit_json['availableDateUnfurnished']
                unit_specials = []
                if 'promotions' in unit_json:
                    for promo in unit_json['promotions']:
                        promo_title = promo['promotionTitle']
                        unit_specials.append(promo_title)
                unit_packages = []
                if 'finishPackage' in unit_json:
                    package_name = unit_json['finishPackage']['name']
                    package_disc = unit_json['finishPackage']['description']
                    unit_packages.append(package_name + ': ' + package_disc)
                unit_virtual = None
                if 'virtualTour' in unit_json:
                    unit_virtual = unit_json['virtualTour']['space']
                break

        print(f'Unit no: {unit_number}')
        print(f'Spec list: {unit_specs}')
        print(f'Beds: {unit_beds}')
        print(f'Baths: {unit_baths}')
        print(f'Sqft: {unit_sqft}')
        print(f'Price: {unit_price}')
        print(f'Fur price: {unit_furnish_price}')
        print(f'Url: {unit_url}')
        print(f'Image url: {unit_image_url}')
        print(f'Virtual tour: {unit_virtual}')
        print(f'Move in: {unit_adate}')
        print(f'Specials: {unit_specials}')
        print(f'Packages: {unit_packages}')

        print('\n')







async def main():

    # Create output directory if it doesn't exist.
    if not Path.exists(this_directory / 'output'):
        Path.mkdir(this_directory / 'output')

    # Start a browser session with playwright.
    playwright = await async_playwright().start()
    firefox = playwright.firefox
    browser = await firefox.launch(headless=True)

    await get_locations(browser)

    # Close playwright properly.    
    await browser.close()
    await playwright.stop()




if __name__ == '__main__':
    asyncio.run(main())  # Start the asyncio event loop and run the main coroutine.