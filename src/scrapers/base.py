"""
Base scraper — rotação de User-Agents, delays, retry logic.
"""

import time
import random
import re
from typing import Optional
import requests


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class BaseScraper:
    """Base scraper com rotação de User-Agent, delays, retry."""

    def __init__(self, delay_range=(2.0, 5.0), timeout=20, max_retries=2):
        self.delay_range = delay_range
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    def get_headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }

    def sleep(self):
        time.sleep(random.uniform(*self.delay_range))

    def fetch(self, url: str) -> Optional[str]:
        """Fetch URL com retries."""
        for attempt in range(self.max_retries + 1):
            try:
                self.sleep()
                response = self.session.get(url, headers=self.get_headers(), timeout=self.timeout)
                if response.status_code == 200:
                    return response.text
                if response.status_code in (403, 429):
                    print(f"  [warn] Bloqueio {response.status_code} em {url[:80]}")
                    time.sleep(10 * (attempt + 1))
                else:
                    print(f"  [warn] Status {response.status_code} em {url[:80]}")
            except requests.exceptions.RequestException as e:
                print(f"  [erro] {e.__class__.__name__} em {url[:80]}")
                time.sleep(3 * (attempt + 1))
        return None

    def parse_price(self, text: str) -> Optional[int]:
        """Extrai número de preço mensal em '€520/mes' ou '520 €'.

        Anúncios de temporada/turismo ('€/día', '€/noche') não são aluguel
        mensal — descartados para não contaminar o ranking com valores
        de diária muito abaixo do teto de aluguel.
        """
        if not text:
            return None
        lowered = text.lower()
        if "día" in lowered or "dia" in lowered or "noche" in lowered:
            return None
        cleaned = text.replace(".", "").replace("\xa0", " ")
        match = re.search(r"(\d[\d\s]*)", cleaned)
        if not match:
            return None
        digits = match.group(1).replace(" ", "")
        try:
            return int(digits)
        except ValueError:
            return None

    def parse_rooms(self, text: str) -> Optional[int]:
        """Extrai número de quartos de '2 hab' ou '3 dorm'."""
        if not text:
            return None
        match = re.search(r"(\d+)\s*(?:hab|dorm|habitación|habitaci)", text.lower())
        return int(match.group(1)) if match else None

    def parse_m2(self, text: str) -> Optional[int]:
        """Extrai metragem de '65 m²' ou '65m2'."""
        if not text:
            return None
        match = re.search(r"(\d+)\s*m", text.lower())
        return int(match.group(1)) if match else None
