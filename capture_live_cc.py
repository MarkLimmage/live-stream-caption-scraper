#!/usr/bin/env python3
"""
YouTube Live Stream Closed Caption Scraper

This script captures and outputs closed captions (CC) and associated metadata
from a YouTube live stream in real-time.

Author: Generated for live-stream-caption-scraper project
License: MIT
"""

import argparse
import json
import re
import sys
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class YouTubeLiveCaptionScraper:
    """
    A scraper for extracting live closed captions from YouTube live streams.
    """

    def __init__(self, video_id: str, headless: bool = True):
        """
        Initialize the scraper.

        Args:
            video_id: YouTube video ID
            headless: Whether to run browser in headless mode
        """
        self.video_id = video_id
        self.headless = headless
        self.driver = None
        self.caption_base_url = None
        self.session = requests.Session()
        self.seen_segments = set()

    def _setup_driver(self):
        """Set up and configure the Selenium WebDriver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    @staticmethod
    def _extract_video_id(url: str) -> str:
        """
        Extract video ID from a YouTube URL.

        Args:
            url: YouTube URL

        Returns:
            Video ID string

        Raises:
            ValueError: If video ID cannot be extracted
        """
        # If already a video ID (11 characters)
        if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
            return url

        # Parse URL
        parsed = urlparse(url)

        # Standard watch URL
        if 'youtube.com' in parsed.netloc:
            query = parse_qs(parsed.query)
            if 'v' in query:
                return query['v'][0]

        # Short URL
        if 'youtu.be' in parsed.netloc:
            return parsed.path.lstrip('/')

        raise ValueError(f"Could not extract video ID from: {url}")

    def _load_youtube_page(self) -> str:
        """
        Load the YouTube watch page and return the page source.

        Returns:
            Page source HTML

        Raises:
            Exception: If page fails to load
        """
        url = f"https://www.youtube.com/watch?v={self.video_id}"

        try:
            self.driver.get(url)

            # Wait for the player to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "movie_player"))
            )

            # Give additional time for all scripts to execute
            time.sleep(3)

            return self.driver.page_source
        except Exception as e:
            raise Exception(f"Failed to load YouTube page: {str(e)}")

    def _extract_player_response(self, page_source: str) -> Optional[Dict[str, Any]]:
        """
        Extract ytInitialPlayerResponse from the page source.

        Args:
            page_source: HTML source of the page

        Returns:
            Parsed player response dictionary or None
        """
        soup = BeautifulSoup(page_source, 'html.parser')

        # Look for ytInitialPlayerResponse in script tags
        for script in soup.find_all('script'):
            script_text = script.string
            if script_text and 'ytInitialPlayerResponse' in script_text:
                # Extract the JSON object
                match = re.search(r'var ytInitialPlayerResponse\s*=\s*({.+?});', script_text)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        continue

        return None

    def _find_caption_tracks(self, player_response: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        Find caption tracks from player response.

        Args:
            player_response: Parsed player response

        Returns:
            List of caption track dictionaries or None
        """
        try:
            captions = player_response.get('captions', {})
            player_captions = captions.get('playerCaptionsTracklistRenderer', {})
            caption_tracks = player_captions.get('captionTracks', [])
            return caption_tracks if caption_tracks else None
        except (KeyError, AttributeError):
            return None

    def _get_live_caption_url(self, caption_tracks: List[Dict[str, Any]]) -> Optional[str]:
        """
        Get the base URL for live captions.

        Args:
            caption_tracks: List of caption tracks

        Returns:
            Caption base URL or None
        """
        # Prefer English captions, but fall back to any available
        en_track = None
        any_track = None

        for track in caption_tracks:
            if any_track is None:
                any_track = track

            lang_code = track.get('languageCode', '')
            if lang_code.startswith('en'):
                en_track = track
                break

        selected_track = en_track or any_track

        if selected_track:
            return selected_track.get('baseUrl')

        return None

    def _parse_caption_segment(self, segment_data: str) -> List[Dict[str, str]]:
        """
        Parse caption segment data (JSON3 format used by YouTube).

        Args:
            segment_data: Raw segment data

        Returns:
            List of caption dictionaries with timestamp and text
        """
        captions = []

        try:
            data = json.loads(segment_data)

            # YouTube uses a JSON3 format with events
            events = data.get('events', [])

            for event in events:
                # Look for segments with actual text
                segs = event.get('segs', [])
                if segs:
                    text_parts = []
                    for seg in segs:
                        if 'utf8' in seg:
                            text_parts.append(seg['utf8'])

                    if text_parts:
                        text = ''.join(text_parts).strip()
                        if text:
                            # Get timestamp (in milliseconds, convert to HH:MM:SS.mmm)
                            tStartMs = event.get('tStartMs', 0)
                            timestamp = self._format_timestamp(tStartMs)

                            captions.append({
                                'timestamp': timestamp,
                                'text': text
                            })
        except (json.JSONDecodeError, KeyError, AttributeError):
            # If JSON3 parsing fails, try other formats or return empty
            pass

        return captions

    def _format_timestamp(self, milliseconds: int) -> str:
        """
        Format timestamp from milliseconds to HH:MM:SS.mmm format.

        Args:
            milliseconds: Timestamp in milliseconds

        Returns:
            Formatted timestamp string
        """
        total_seconds = milliseconds / 1000
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        millis = int(milliseconds % 1000)

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"

    def _fetch_caption_data(self, url: str) -> Optional[str]:
        """
        Fetch caption data from a URL.

        Args:
            url: Caption data URL

        Returns:
            Raw caption data or None
        """
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return None

    def initialize(self):
        """
        Initialize the scraper by loading the page and finding caption URLs.

        Raises:
            Exception: If initialization fails
        """
        self._setup_driver()

        print("Loading YouTube page...", file=sys.stderr)
        page_source = self._load_youtube_page()

        print("Extracting player response...", file=sys.stderr)
        player_response = self._extract_player_response(page_source)

        if not player_response:
            raise Exception("Could not find ytInitialPlayerResponse in page")

        print("Finding caption tracks...", file=sys.stderr)
        caption_tracks = self._find_caption_tracks(player_response)

        if not caption_tracks:
            raise Exception("No live captions found")

        self.caption_base_url = self._get_live_caption_url(caption_tracks)

        if not self.caption_base_url:
            raise Exception("No live captions found")

        print(f"Found caption track: {self.caption_base_url}", file=sys.stderr)

    def run(self, poll_interval: float = 2.0):
        """
        Run the scraper, continuously polling for new captions.

        Args:
            poll_interval: Time between polls in seconds
        """
        print("Starting caption capture (press Ctrl+C to stop)...", file=sys.stderr)

        try:
            while True:
                # Fetch the latest caption data
                caption_data = self._fetch_caption_data(self.caption_base_url)

                if caption_data:
                    captions = self._parse_caption_segment(caption_data)

                    for caption in captions:
                        # Create a unique identifier for this caption
                        caption_id = f"{caption['timestamp']}:{caption['text']}"

                        if caption_id not in self.seen_segments:
                            self.seen_segments.add(caption_id)
                            # Output as JSON
                            print(json.dumps(caption, ensure_ascii=False))
                            sys.stdout.flush()

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\nCaption capture stopped by user.", file=sys.stderr)
        except Exception as e:
            print(f"\nError during caption capture: {str(e)}", file=sys.stderr)
            print("Live stream may have ended or caption feed was interrupted.", file=sys.stderr)

    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Capture live closed captions from YouTube live streams',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  %(prog)s dQw4w9WgXcQ
  %(prog)s "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --poll-interval 1.5
        """
    )

    parser.add_argument(
        'url',
        help='YouTube Live stream URL or Video ID'
    )

    parser.add_argument(
        '--poll-interval',
        type=float,
        default=2.0,
        help='Time between caption polls in seconds (default: 2.0)'
    )

    parser.add_argument(
        '--visible',
        action='store_true',
        help='Run browser in visible mode (not headless)'
    )

    args = parser.parse_args()

    scraper = None

    try:
        # Extract video ID from URL
        video_id = YouTubeLiveCaptionScraper._extract_video_id(args.url)

        # Create scraper instance
        scraper = YouTubeLiveCaptionScraper(video_id, headless=not args.visible)

        # Initialize (load page, find captions)
        scraper.initialize()

        # Run the caption capture loop
        scraper.run(poll_interval=args.poll_interval)

    except ValueError as e:
        print(f"Error: Invalid URL or Video ID - {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    finally:
        if scraper:
            scraper.cleanup()


if __name__ == '__main__':
    main()
