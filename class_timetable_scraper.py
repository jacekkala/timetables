import requests
from bs4 import BeautifulSoup
import re
from collections import defaultdict
import os
from datetime import datetime
import json

class TimetableScraper:
    """
    A class to scrape timetable data from the MPK Łódź website.
    """
    def __init__(self, base_url="https://www.mpk.lodz.pl/rozklady/",
                 timetable_selector_pattern="html body.stopTable div#dBckgrnd div#dWrkspc div#dTable div#dTab div#day_type_{}.dayType",
                 stop_links_selector="td.version table:nth-child(2) a",
                 output_base_folder="Timetables"):
        """
        Initializes the scraper with base URLs, CSS selectors, and the output base folder.

        Args:
            base_url (str): The base URL of the MPK Łódź website.
            timetable_selector_pattern (str): The CSS selector pattern for timetable data.
            stop_links_selector (str): The CSS selector to target the <a> elements containing stop links.
            output_base_folder (str): The name of the main folder to store tram timetables.
        """
        self.base_url = base_url
        self.timetable_selector_pattern = timetable_selector_pattern
        self.stop_links_selector = stop_links_selector
        self.current_date = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
        self.output_base_folder = output_base_folder
        if not os.path.exists(self.output_base_folder):
            os.makedirs(self.output_base_folder)

    def _scrape_timetable_for_day(self, soup, day_type_id):
        """
        Scrapes timetable data for a specific day from a BeautifulSoup object.

        Args:
            soup (BeautifulSoup): The parsed HTML content of the timetable page.
            day_type_id (int): The ID representing the day type (e.g., 12 for weekday).

        Returns:
            defaultdict(list) or None: A dictionary of timetable data for the day,
                                       or None if the timetable element is not found.
        """
        selector = self.timetable_selector_pattern.format(day_type_id)
        element = soup.select_one(selector)
        if element:
            time_elements = element.find_all('a', class_=['minute', 'minute_sel'])
            day_timetable_dict = defaultdict(list)
            for time_element in time_elements:
                time_str = time_element.text.strip()
                cleaned_time_str = re.sub(r'[AB]$', '', time_str)
                if not re.search(r'[a-z]$', cleaned_time_str):
                    hour_element = time_element.parent.previous_sibling
                    if hour_element:
                        hour = hour_element.text.strip()
                        day_timetable_dict[int(hour)].append(cleaned_time_str)
            return day_timetable_dict
        return None

    def scrape_timetable(self, url, tram_number):
        """
        Scrapes timetable data from a given URL for weekday, Saturday, and Sunday.
        Skips minutes that end with a lowercase letter.

        Args:
            url (str): The URL of the website to scrape.
            tram_number (str): The number or identifier of the tram line.

        Returns:
            dict: A dictionary where keys are day types ('weekday', 'Saturday', 'Sunday')
                  and values are dictionaries of timetable data for that day.
                  If a day's timetable is not found, its value will be None.
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            timetable_data = {}
            day_types = {
                'weekday': 12,
                'Saturday': 13,
                'Sunday': 14,
            }
            for day, day_type_id in day_types.items():
                timetable_data[day] = self._scrape_timetable_for_day(soup, day_type_id)
                if day_type_id == 13 and timetable_data[day] is None:
                    print(f"Tram {tram_number} does not run on Saturdays.")
                elif day_type_id == 14 and timetable_data[day] is None:
                    print(f"Tram {tram_number} does not run on Sundays.")
            return timetable_data
        except requests.exceptions.RequestException as e:
            print(f"Error fetching the website: {e}")
            return None
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def scrape_stop_links_and_timetables(self, url, target_line_id, target_direction, tram_number):
        """
        Scrapes stop links with their names and numbers, and then fetches their timetables.

        Args:
            url (str): The URL of the website to scrape for stop links.
            target_line_id (str): The lineId value to filter by in the href.
            target_direction (str): The direction value to filter by in the href.
            tram_number (str): The number or identifier of the tram line.

        Returns:
            dict: A dictionary where keys are stop names with stop numbers and values are
                  dictionaries of their timetable data.
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            link_elements = soup.select(self.stop_links_selector)
            stop_data = {}
            for a in link_elements:
                if 'href' in a.attrs and \
                   f'lineId={target_line_id}' in a['href'] and \
                   f'direction={target_direction}' in a['href'] and \
                   'timetableId' in a['href'] and \
                   'stopNumber' in a['href'] and \
                   'date' in a['href']:
                    stop_name = a.text.strip()
                    href = a['href']
                    match = re.search(r'stopNumber=(\d+)', href)
                    stop_number = match.group(1) if match else None
                    if stop_number:
                        formatted_key = f"{stop_name} ({stop_number})"
                        full_timetable_url = self.base_url + href
                        timetable = self.scrape_timetable(full_timetable_url, tram_number)
                        stop_data[formatted_key] = timetable
            return stop_data
        except requests.exceptions.RequestException as e:
            print(f"Error fetching the URL: {e}")
            return {}
        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            return {}

    def process_tram_line(self, line, line_id, directions=[1, 2]):
        """
        Processes a single tram line for both directions, scraping and saving timetables
        into a common folder named 'Timetables'.

        Args:
            line (str): The tram line number or identifier.
            line_id (str): The MPK identifier for the tram line.
            directions (list, optional): A list of directions to scrape (default: [1, 2]).
        """
        tram_dir = os.path.join(self.output_base_folder, str(line))
        if not os.path.exists(tram_dir):
            os.makedirs(tram_dir)
        for direction in directions:
            website_url = f"https://www.mpk.lodz.pl/rozklady/trasa.jsp?lineId={line_id}&date={self.current_date}"
            print(f"Scraping tram {line}, direction {direction} from {website_url}")
            extracted_stop_timetables = self.scrape_stop_links_and_timetables(
                website_url, line_id, direction, line
            )
            filename = os.path.join(tram_dir, f"{line}_{direction}.json")
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(extracted_stop_timetables, f, ensure_ascii=False, indent=4)
                print(f"Timetable for Tram {line} (Direction {direction}) saved to {filename}")
            except Exception as e:
                print(f"Error saving timetable for Tram {line} (Direction {direction}): {e}")

if __name__ == "__main__":
    tram_lines = {
        "1": "1208",
        "2": "1192",
        "3": "1163",
        "5": "1193",
        "6": "1086",
        "7": "1255",
        "8A": "1273",
        "8B": "1274",
        "9": "1275",
        "10A": "904",
        "10B": "733",
        "11": "1094",
        "12": "1102",
        "14": "1190",
        "15": "658",
        "16": "1249",
        "17": "1256",
        "18": "1194",
        "19": "1245",
        "41": "1170",
        "43": "1238",
        "45": "1221",
    }
    scraper = TimetableScraper()
    for line, line_id in tram_lines.items():
        scraper.process_tram_line(line, line_id)
