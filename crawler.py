#!/usr/bin/env python3

import re
import json
import requests
import lxml.html
import argparse

from time import sleep
from requests.exceptions import ConnectionError
from fake_useragent import UserAgent

EMAIL_REGEX = re.compile(r'[^@]+@[^@]+\.[^@]+')


def german_postalcodes():
    postal_codes = []

    with open('data/german_postalcodes.geojson', 'r') as f:
        d = json.load(f)

        for feature in d['features']:
            postal_codes.append(feature['properties']['postcode'])

    return postal_codes


def parse_details(content):
    doc = lxml.html.fromstring(content)
    contact = doc.xpath('//div[@class="lnks"]')

    mail = contact[0].xpath('./a[@class="mail"]')
    web = contact[0].xpath('./a[@class="www"]')

    contact_data = {}

    for m in mail:
        if len(m.xpath('./@title')) > 0:
            mail_address = m.xpath('./@title')[0].lower()

            if not EMAIL_REGEX.fullmatch(mail_address):
                continue

            contact_data['mailAddress'] = mail_address

            break

    for w in web:
        if len(w.xpath('./@title')) > 0:
            contact_data['website'] = w.xpath('./@title')[0].lower()

            break

    if 'mailAddress' not in contact_data:
        contact_data['mailAddress'] = ''

    if 'website' not in contact_data:
        contact_data['website'] = ''

    return contact_data


def parse_listings(content):
    doc = lxml.html.fromstring(content)
    d = doc.xpath('//script[@type="application/ld+json"]/text()')
    j = json.loads(d[0])

    return j['@graph']


def parse_hits(content):
    doc = lxml.html.fromstring(content)
    h = doc.xpath('//span[@class="sttrefferanz"]/text()')

    if len(h) > 0:
        l = int(h[0])
    else:
        l = 0

    return l


def parse_iteration(content):
    doc = lxml.html.fromstring(content)
    n = doc.xpath('//a[@title="zur nächsten Seite"]/@href')

    if len(n) > 0:
        url = n[0]
    else:
        url = None

    return url


def download_site(url, headers):
    try:
        r = requests.get(url, headers=headers, cookies={'CONSENT': 'YES+'})

        return r.content
    except ConnectionError as e:
        sleep(15)
        download_site(url, headers)
    except Exception as e:
        print(e)
        return None


def aggregate(query, postal_code):
    ua = UserAgent()
    headers = { 'User-Agent': ua.random }

    param = 'kw={}&ci={}&form_name=search_nat'.format(query, postal_code)
    url = 'https://www.dasoertliche.de?{}'.format(param)
    print('start parsing {}\n'.format(url))

    results = []

    site_listings = download_site(url, headers)
    total_hists = parse_hits(site_listings)

    while total_hists > 0:
        listings = parse_listings(site_listings)

        for item in listings:
            site_details = download_site(item['url'], headers)
            details = parse_details(site_details)

            keys = ['url', 'geo', 'address']

            if all(i not in item for i in keys):
                print('abort parsing listings for {}\n\n'.format(postal_code))

                break

            item.pop('aggregateRating') if 'aggregateRating' in item else item

            item['coordinates'] = []
            item['coordinates'].append(float(item['geo']['latitude']))
            item['coordinates'].append(float(item['geo']['longitude']))

            try:
                listing_postal_code = f'{item["address"]["postalCode"]:05d}'
                item['address']['postalCode'] = listing_postal_code
            except:
                pass

            try:
                item['telephone'] = item['telephone'].replace(' ', '')
            except:
                pass

            item.pop('url')
            item.pop('geo')
            item.pop('@type')
            item['address'].pop('@type')

            entry = {**item, **details}
            results.append(entry)

            print('{}\n'.format(entry))

            sleep(1)

        if postal_code.isnumeric():
            file_name = '{}_{}'.format(query.lower(), postal_code)
        else:
            file_name = '{}'.format(query.lower())

        output = 'data/{}.json'.format(file_name)

        with open(output, 'a', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False)

        url = parse_iteration(site_listings)

        if len(results) <= total_hists and url is not None:
            print('Next url {}\n'.format(url))
            site_listings = download_site(url, headers)
        else:
            print('Reached end of end of scraping process')

            break


def main():
    parser = argparse.ArgumentParser(description='Simple scraper')
    parser.add_argument('--query', dest='query', required=True)
    parser.add_argument('--use-postal-codes', dest='use_postal_codes', action='store_true')

    args = parser.parse_args()

    postal_codes = german_postalcodes()

    if args.use_postal_codes:
        for postal_code in postal_codes:
            aggregate(args.query, postal_code)
    else:
        aggregate(args.query, '')


if __name__ == '__main__':
    main()
