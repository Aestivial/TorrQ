#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ==============================================================================
#  Torrent Search CLI - A Complete End-to-End Solution
# ==============================================================================
#
#  This script provides a command-line interface to search for torrents from
#  multiple sources, display them in a user-friendly format, and open the
#  selected magnet link in the system's default torrent client.
#
#  Features:
#  1.  Dependency Checker: Verifies required libraries are installed on startup.
#  2.  Multi-Provider Search: Aggregates results from different torrent sites.
#      - The Pirate Bay (via API)
#      - 1337x (via web scraping)
#  3.  Interactive UI: Uses the 'rich' library to display results in a sorted,
#      color-coded table for easy comparison.
#  4.  Download Hand-off: Opens the selected magnet link using the appropriate
#      system command for Linux, macOS, and Windows.
#  5.  Single-File Portability: All logic is contained within this single file.
#
#  Usage:
#      python torrent_client.py "Your Search Query"
#
# ==============================================================================

import sys
import os
import subprocess
import importlib.util
import argparse
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict
from urllib.parse import quote_plus, urljoin

# --- Dependency Management ---

# A list of required packages for this script to run.
REQUIRED_PACKAGES = [
    "requests",
    "beautifulsoup4",
    "rich",
    "cloudscraper",
]

def check_dependencies():
    """
    Checks if all required packages are installed. If not, prints instructions
    and exits. This must be run before any other imports from these packages.
    """
    missing_packages = []
    for package_name in REQUIRED_PACKAGES:
        # A special case for beautifulsoup4 which is imported as 'bs4'
        import_name = "bs4" if package_name == "beautifulsoup4" else package_name
        spec = importlib.util.find_spec(import_name)
        if spec is None:
            missing_packages.append(package_name)

    if missing_packages:
        print("Error: Missing required Python packages.", file=sys.stderr)
        print("The following dependencies were not found:", file=sys.stderr)
        for pkg in missing_packages:
            print(f"  - {pkg}", file=sys.stderr)
        print("\nTo install all necessary packages, please create a 'requirements.txt' file with the following content:", file=sys.stderr)
        print("--------------------")
        for pkg in REQUIRED_PACKAGES:
            print(pkg)
        print("--------------------")
        print("\nThen run the following command in your terminal:", file=sys.stderr)
        print("\n    pip install -r requirements.txt\n", file=sys.stderr)
        print("After installation, please run the application again.", file=sys.stderr)
        sys.exit(1)

# --- Perform Dependency Check before proceeding ---
check_dependencies()

# --- Main Imports (post-dependency check) ---
import requests
import cloudscraper
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

# --- Core Data Structures ---

@dataclass
class TorrentResult:
    """A standardized representation of a single torrent search result."""
    title: str
    size: str
    seeders: int
    leechers: int
    magnet_link: str  # Can be a magnet link or a detail page URL
    uploader: str
    source: str
    file_count: Optional[int] = None
    upload_date: Optional[str] = None

# --- Provider Framework ---

class Provider(ABC):
    """Abstract base class for all torrent providers."""
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def search(self, query: str) -> List[TorrentResult]:
        """
        Searches for torrents matching the query.

        Args:
            query (str): The search term.

        Returns:
            List[TorrentResult]: A list of standardized torrent results.
        """
        pass

class ThePirateBayProvider(Provider):
    """Provider for The Pirate Bay using the apibay.org JSON API."""
    def __init__(self):
        super().__init__("ThePirateBay")
        self.api_url = "https://apibay.org/q.php"
        self.trackers = [
            "udp://tracker.coppersurfer.tk:6969/announce",
            "udp://9.rarbg.to:2920/announce",
            "udp://tracker.opentrackr.org:1337",
            "udp://tracker.internetwarriors.net:1337/announce",
            "udp://tracker.leechers-paradise.org:6969/announce",
        ]

    def search(self, query: str) -> List[TorrentResult]:
        results = []
        params = {'q': query, 'cat': '0'}
        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data or (isinstance(data, list) and len(data) > 0 and data[0].get("name") == "No results returned"):
                return []

            for item in data:
                magnet_link = self._build_magnet_link(item['info_hash'], item['name'])
                results.append(TorrentResult(
                    title=item.get('name', 'N/A'),
                    size=self._format_size(int(item.get('size', 0))),
                    seeders=int(item.get('seeders', 0)),
                    leechers=int(item.get('leechers', 0)),
                    magnet_link=magnet_link,
                    uploader=item.get('username', 'N/A'),
                    source=self.name,
                    upload_date=self._format_timestamp(int(item.get('added', 0)))
                ))
        except (requests.RequestException, json.JSONDecodeError) as e:
            # Use Rich console for formatted error printing
            Console().print(f"[bold red]Error searching {self.name}: {e}[/bold red]")
        return results

    def _build_magnet_link(self, info_hash: str, name: str) -> str:
        tracker_str = "".join([f"&tr={quote_plus(t)}" for t in self.trackers])
        return f"magnet:?xt=urn:btih:{info_hash}&dn={quote_plus(name)}{tracker_str}"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0 B"
        power = 1024
        n = 0
        power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size_bytes >= power and n < len(power_labels) -1:
            size_bytes /= power
            n += 1
        return f"{size_bytes:.2f} {power_labels[n]}B"

    @staticmethod
    def _format_timestamp(ts: int) -> str:
        from datetime import datetime
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

class OneThreeThreeSevenXProvider(Provider):
    """Provider for 1337x.to using web scraping."""
    def __init__(self):
        super().__init__("1337x")
        self.base_url = "https://1337x.to"
        self.scraper = cloudscraper.create_scraper()

    def search(self, query: str) -> List[TorrentResult]:
        results = []
        search_url = f"{self.base_url}/search/{quote_plus(query)}/1/"
        try:
            response = self.scraper.get(search_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            table = soup.find('table', class_='table-list')
            if not table:
                return []

            for row in table.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) < 6: # Ensure row has enough columns
                    continue

                title_col = cols[0]
                title_anchor = title_col.find_all('a')[-1]
                title = title_anchor.text.strip()
                detail_url = urljoin(self.base_url, title_anchor['href'])

                seeders = int(cols[1].text.strip())
                leechers = int(cols[2].text.strip())
                upload_date = cols[3].text.strip()
                size = cols[4].text.strip()
                uploader_col = cols[5]
                uploader_anchor = uploader_col.find('a')
                uploader = uploader_anchor.text.strip() if uploader_anchor else uploader_col.text.strip()

                results.append(TorrentResult(
                    title=title,
                    size=size,
                    seeders=seeders,
                    leechers=leechers,
                    magnet_link=detail_url, # Store detail URL for later fetching
                    uploader=uploader,
                    source=self.name,
                    upload_date=upload_date
                ))
        except requests.RequestException as e:
            Console().print(f"[bold red]Error searching {self.name}: {e}[/bold red]")
        return results

    def get_magnet(self, detail_url: str) -> Optional[str]:
        """Fetches the magnet link from a torrent's detail page."""
        try:
            response = self.scraper.get(detail_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            magnet_anchor = soup.find('a', href=re.compile(r'^magnet:\?'))
            if magnet_anchor:
                return magnet_anchor['href']
        except requests.RequestException as e:
            Console().print(f"[bold red]Error fetching magnet from {self.name}: {e}[/bold red]")
        return None

# --- System Interaction ---

def open_magnet_link(magnet_link: str):
    """
    Opens the given magnet link in the system's default BitTorrent client.
    This function is cross-platform.
    """
    console = Console()
    console.print(f"\n[cyan]Attempting to open magnet link in your default client...[/cyan]")
    platform = sys.platform

    try:
        if platform.startswith('linux'):
            subprocess.run(['xdg-open', magnet_link], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif platform == 'darwin': # macOS
            subprocess.run(['open', magnet_link], check=True)
        elif platform == 'win32': # Windows
            os.startfile(magnet_link)
        else:
            console.print(f"[yellow]Unsupported operating system: {platform}[/yellow]")
            console.print("[yellow]Please copy the magnet link below and open it manually:[/yellow]")
            console.print(f"\n[bold]{magnet_link}[/bold]\n")
            return

        console.print("[bold green]Successfully sent magnet link to client.[/bold green]")

    except (FileNotFoundError, subprocess.CalledProcessError, OSError) as e:
        console.print(f"[bold red]Error: Could not automatically open the magnet link.[/bold red]")
        console.print("[yellow]This may be because you do not have a default torrent client set up.[/yellow]")
        console.print("[yellow]Please copy the magnet link below and open it manually in your client:[/yellow]")
        console.print(f"\n[bold]{magnet_link}[/bold]\n")
        console.print(f"(System Error: {e})", style="dim")

# --- Main Application ---

def main():
    """Main function to run the torrent search CLI."""
    parser = argparse.ArgumentParser(description="Search for torrents from the command line.")
    parser.add_argument("query", nargs='+', help="The search query for the torrent.")
    args = parser.parse_args()
    query = " ".join(args.query)

    console = Console()
    console.print(f"[bold cyan]Searching for: '{query}'...[/bold cyan]")

    providers: List[Provider] = [ThePirateBayProvider(), OneThreeThreeSevenXProvider()]
    all_results: List[TorrentResult] = []

    with console.status("[bold green]Aggregating results...") as status:
        for provider in providers:
            status.update(f"[bold green]Querying {provider.name}...")
            try:
                provider_results = provider.search(query)
                all_results.extend(provider_results)
            except Exception as e:
                console.print(f"[bold red]Failed to get results from {provider.name}: {e}[/bold red]")

    if not all_results:
        console.print("[bold yellow]No results found.[/bold yellow]")
        return

    # Sort results by seeders (descending) for best health
    all_results.sort(key=lambda x: x.seeders, reverse=True)

    table = Table(title=f"Search Results for '{query}'")
    table.add_column("Index", style="magenta", justify="right")
    table.add_column("Title", style="cyan", no_wrap=False, max_width=60)
    table.add_column("Size", style="yellow")
    table.add_column("SE", style="green", justify="right")
    table.add_column("LE", style="red", justify="right")
    table.add_column("Date", style="blue")
    table.add_column("Uploader", style="blue")
    table.add_column("Source", style="dim")

    for i, result in enumerate(all_results):
        # Color-code seeder count based on health
        seeder_style = "green" if result.seeders > 5 else "yellow" if result.seeders > 0 else "red"
        table.add_row(
            str(i + 1),
            result.title,
            result.size,
            f"[{seeder_style}]{result.seeders}[/{seeder_style}]",
            str(result.leechers),
            result.upload_date or 'N/A',
            result.uploader,
            result.source
        )

    console.print(table)

    while True:
        try:
            choice_str = Prompt.ask("\n[bold]Enter the index of the torrent to download (or 'q' to quit)[/bold]")
            if choice_str.lower().strip() == 'q':
                console.print("[yellow]Aborted.[/yellow]")
                break

            choice = int(choice_str) - 1
            if 0 <= choice < len(all_results):
                selected_torrent = all_results[choice]

                # If the provider is 1337x, we need to fetch the magnet link now
                if selected_torrent.source == "1337x":
                    with console.status(f"[cyan]Fetching magnet link for '{selected_torrent.title[:50]}...'[/cyan]"):
                        provider_1337x = next((p for p in providers if isinstance(p, OneThreeThreeSevenXProvider)), None)
                        if provider_1337x:
                            # The 'magnet_link' field currently holds the detail page URL
                            magnet = provider_1337x.get_magnet(selected_torrent.magnet_link)
                            if magnet:
                                selected_torrent.magnet_link = magnet
                            else:
                                console.print("[bold red]Failed to retrieve magnet link.[/bold red]")
                                continue # Ask for input again
                        else:
                            console.print("[bold red]Internal error: 1337x provider not found.[/bold red]")
                            continue # Ask for input again

                open_magnet_link(selected_torrent.magnet_link)
                break
            else:
                console.print("[bold red]Invalid index. Please try again.[/bold red]")
        except ValueError:
            console.print("[bold red]Invalid input. Please enter a number or 'q'.[/bold red]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Aborted.[/yellow]")
            break

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        # This handles Ctrl+C gracefully at any point in the main function
        print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        # Catch any other unexpected errors for graceful exit
        console = Console()
        console.print(f"\n[bold red]An unexpected error occurred:[/bold red]")
        console.print_exception(show_locals=True)
        sys.exit(1)

