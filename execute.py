import csv
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

    # Write all communties to csv file.
    with open(Path(this_directory / 'output/avalonbay_communities.csv'), 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for community in communities:
            writer.writerow(['']+community)

    for community in communities:
        community_url = community[1]
        await get_community(page, community_url)

    await page.close()
    await context.close()

    sleep(2)
    


async def get_community(page, community_url):
    apartments_button = page.locator('xpath=//button[@id="apartment-toggle"]')

    await apartments_button.click()

    # TODO: Make sure that the matching of unit with community is reliable.
    unit_cards = page.locator(f'xpath=//div[@class="ant-card-body"][.//a[contains(@href,"{community_url}")]]')

    num_units = await unit_cards.count()

    print(f'Num of units: {num_units}')




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