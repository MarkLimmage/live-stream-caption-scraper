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

    def __init__(self, video_id: str, headless: bool = True, method: str = 'dom'):
        """
        Initialize the scraper.

        Args:
            video_id: YouTube video ID
            headless: Whether to run browser in headless mode
            method: Caption extraction method ('dom' or 'api')
        """
        self.video_id = video_id
        self.headless = headless
        self.method = method  # 'dom' or 'api'
        self.driver = None
        self.caption_base_url = None
        self.dash_manifest_url = None  # Store the manifest URL for refreshing
        self.caption_url_last_refresh = 0  # Track when we last refreshed the URL
        self.session = requests.Session()
        self.seen_segments = set()
        self.last_caption_text = None  # Track the last caption to avoid immediate duplicates
        self.last_caption_time = 0  # Timestamp of last new caption
        self.starting_segment = None  # Starting segment number for API method

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
        if parsed.netloc in ('www.youtube.com', 'youtube.com', 'm.youtube.com'):
            query = parse_qs(parsed.query)
            if 'v' in query:
                return query['v'][0]

        # Short URL
        if parsed.netloc == 'youtu.be':
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

            # Give additional time for all scripts to execute and ads to potentially load
            print("Waiting for page to fully load (including potential ads)...", file=sys.stderr)
            time.sleep(8)  # Increased wait time for ads
            
            # Try to skip ad if present
            try:
                skip_button = self.driver.find_element(By.CLASS_NAME, "ytp-ad-skip-button")
                if skip_button.is_displayed():
                    print("Skipping ad...", file=sys.stderr)
                    skip_button.click()
                    time.sleep(2)
            except:
                pass  # No ad or couldn't skip
            
            # Click play button to start the video
            print("Starting video playback...", file=sys.stderr)
            try:
                # Click on the video player to start playback
                player = self.driver.find_element(By.ID, "movie_player")
                player.click()
                time.sleep(2)
            except Exception as e:
                print(f"Could not click play button: {e}", file=sys.stderr)
            
            # Try to enable captions via the settings button
            print("Attempting to enable captions...", file=sys.stderr)
            try:
                # Click the settings/gear button
                settings_button = self.driver.find_element(By.CLASS_NAME, "ytp-settings-button")
                settings_button.click()
                time.sleep(1)
                
                # Look for subtitles/CC menu item
                menu_items = self.driver.find_elements(By.CLASS_NAME, "ytp-menuitem")
                for item in menu_items:
                    if "subtitle" in item.text.lower() or "cc" in item.text.lower() or "caption" in item.text.lower():
                        item.click()
                        time.sleep(1)
                        # Select first available caption option
                        submenu_items = self.driver.find_elements(By.CLASS_NAME, "ytp-menuitem")
                        for subitem in submenu_items:
                            if subitem.is_displayed() and "off" not in subitem.text.lower():
                                subitem.click()
                                print(f"Enabled captions: {subitem.text}", file=sys.stderr)
                                time.sleep(2)
                                break
                        break
                        
                # Close settings menu
                try:
                    settings_button.click()
                except:
                    pass
            except Exception as e:
                print(f"Could not enable captions via UI: {e}", file=sys.stderr)

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
                # Extract the JSON object by finding balanced braces
                match = re.search(r'var ytInitialPlayerResponse\s*=\s*({)', script_text)
                if match:
                    start_pos = match.end(1) - 1  # Position of opening brace
                    brace_count = 0
                    in_string = False
                    escape_next = False

                    for i, char in enumerate(script_text[start_pos:], start=start_pos):
                        if escape_next:
                            escape_next = False
                            continue

                        if char == '\\':
                            escape_next = True
                            continue

                        if char == '"' and not escape_next:
                            in_string = not in_string
                            continue

                        if not in_string:
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    # Found the matching closing brace
                                    json_str = script_text[start_pos:i+1]
                                    try:
                                        response = json.loads(json_str)
                                        return response
                                    except json.JSONDecodeError as e:
                                        print(f"Error parsing player response: {e}", file=sys.stderr)
                                        break

        return None

    def _scrape_captions_from_dom(self) -> List[Dict[str, str]]:
        """
        Scrape captions directly from the DOM (for when API method fails).
        
        Returns:
            List of caption dictionaries with text
        """
        captions = []
        try:
            # Look for caption container elements - YouTube uses various classes
            caption_selectors = [
                "ytp-caption-segment",
                "captions-text",  
                "ytp-caption-window-container"
            ]
            
            # Collect all caption text on screen and combine into one caption
            caption_texts = []
            
            for selector in caption_selectors:
                try:
                    elements = self.driver.find_elements(By.CLASS_NAME, selector)
                    for element in elements:
                        if element.is_displayed():
                            text = element.text.strip()
                            if text and text not in caption_texts:
                                caption_texts.append(text)
                    if caption_texts:  # If we found captions with this selector, stop trying others
                        break
                except:
                    continue
            
            # Combine all visible caption lines into a single caption entry
            if caption_texts:
                combined_text = '\n'.join(caption_texts)  # Use newline to preserve multi-line structure
                captions.append({
                    'text': combined_text,
                    'timestamp': time.strftime("%H:%M:%S")
                })
                    
        except Exception as e:
            pass  # Silently handle errors during scraping
        
        return captions

    def _find_caption_tracks(self, player_response: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        Find caption tracks from player response.

        Args:
            player_response: Parsed player response

        Returns:
            List of caption track dictionaries or None
        """
        try:
            # Debug: Show what's in the captions structure
            captions = player_response.get('captions', {})
            
            if not captions:
                print("DEBUG: No 'captions' key in player response", file=sys.stderr)
                return None
            
            print(f"DEBUG: Found 'captions' key with subkeys: {list(captions.keys())}", file=sys.stderr)
            
            player_captions = captions.get('playerCaptionsTracklistRenderer', {})
            
            if not player_captions:
                print("DEBUG: No 'playerCaptionsTracklistRenderer' in captions", file=sys.stderr)
                # Check for alternative structures
                if 'playerCaptionsRenderer' in captions:
                    print("DEBUG: Found 'playerCaptionsRenderer' instead", file=sys.stderr)
                return None
            
            print(f"DEBUG: playerCaptionsTracklistRenderer keys: {list(player_captions.keys())}", file=sys.stderr)
            
            caption_tracks = player_captions.get('captionTracks', [])
            
            if caption_tracks:
                print(f"DEBUG: Found {len(caption_tracks)} caption tracks", file=sys.stderr)
            else:
                print("DEBUG: No 'captionTracks' in playerCaptionsTracklistRenderer", file=sys.stderr)
                
            return caption_tracks if caption_tracks else None
        except (KeyError, AttributeError) as e:
            print(f"DEBUG: Exception in _find_caption_tracks: {e}", file=sys.stderr)
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

    def _parse_dash_manifest(self, manifest_url: str) -> Optional[str]:
        """
        Parse DASH manifest XML and extract caption track BaseURL.
        
        Args:
            manifest_url: URL to the DASH manifest
            
        Returns:
            Caption BaseURL or None
        """
        try:
            import xml.etree.ElementTree as ET
            
            print(f"Fetching DASH manifest from: {manifest_url[:100]}...", file=sys.stderr)
            response = self.session.get(manifest_url, timeout=10)
            response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.content)
            
            # Find AdaptationSet with text/vtt mimeType
            for elem in root.iter():
                if elem.tag.endswith('AdaptationSet'):
                    mime = elem.get('mimeType', '')
                    if 'text/vtt' in mime:
                        print(f"✓ Found caption track with mimeType={mime}", file=sys.stderr)
                        
                        # Find BaseURL child
                        for child in elem.iter():
                            if child.tag.endswith('BaseURL'):
                                caption_url = child.text
                                print(f"✓ Extracted caption BaseURL (length: {len(caption_url)})", file=sys.stderr)
                                return caption_url
                        break
            
            print("⚠ No caption track found in DASH manifest", file=sys.stderr)
            return None
            
        except Exception as e:
            print(f"Error parsing DASH manifest: {e}", file=sys.stderr)
            return None

    def _refresh_caption_url(self) -> bool:
        """
        Refresh the caption BaseURL by re-fetching the DASH manifest.
        URLs expire after some time, so we need to refresh periodically.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.dash_manifest_url:
            return False
            
        current_time = time.time()
        
        # Only refresh if it's been more than 5 minutes (URLs typically expire after ~6 hours but refresh more frequently to be safe)
        if current_time - self.caption_url_last_refresh < 300:  # 5 minutes
            return True
            
        print("Refreshing caption URL (URLs expire periodically)...", file=sys.stderr)
        new_url = self._parse_dash_manifest(self.dash_manifest_url)
        
        if new_url:
            self.caption_base_url = new_url
            self.caption_url_last_refresh = current_time
            print("✓ Caption URL refreshed successfully", file=sys.stderr)
            return True
        else:
            print("⚠ Failed to refresh caption URL", file=sys.stderr)
            return False

    def _fetch_caption_segment(self, segment_number: int) -> Optional[str]:
        """
        Fetch a specific caption segment using the DASH BaseURL.
        
        Args:
            segment_number: Segment sequence number
            
        Returns:
            Caption text from the segment or None
        """
        if not self.caption_base_url:
            return None
            
        try:
            # Construct segment URL: BaseURL + /sq/SEGMENT_NUMBER
            segment_url = f"{self.caption_base_url}/sq/{segment_number}"
            
            response = self.session.get(segment_url, timeout=5)
            
            # Check if segment exists
            if response.status_code == 404:
                return None  # Segment doesn't exist yet
            
            response.raise_for_status()
            
            # Parse WebVTT format
            content = response.text
            
            # Extract caption text from WebVTT
            # WebVTT format has timing lines followed by text
            lines = content.split('\n')
            caption_texts = []
            
            for i, line in enumerate(lines):
                # Skip WEBVTT header, timing lines, and empty lines
                if line.startswith('WEBVTT') or '-->' in line or not line.strip():
                    continue
                # Collect actual caption text
                caption_texts.append(line.strip())
            
            if caption_texts:
                return ' '.join(caption_texts)
            
            return None
            
        except Exception as e:
            # Don't log every 404 - it's normal when catching up
            if "404" not in str(e):
                print(f"Error fetching segment {segment_number}: {e}", file=sys.stderr)
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

        print("Extracting player response (initial)...", file=sys.stderr)
        player_response = self._extract_player_response(page_source)

        if not player_response:
            raise Exception("Could not find ytInitialPlayerResponse in page")

        print("Finding caption tracks (initial)...", file=sys.stderr)
        caption_tracks = self._find_caption_tracks(player_response)
        
        if caption_tracks:
            print(f"Found {len(caption_tracks)} caption tracks in initial response", file=sys.stderr)
        else:
            print("No caption tracks in initial response", file=sys.stderr)

        # Try extracting player response AGAIN after captions are enabled and playing
        print("\nRe-extracting player response after captions enabled...", file=sys.stderr)
        time.sleep(2)  # Give time for any dynamic updates
        
        # Get fresh page source
        updated_page_source = self.driver.page_source
        updated_player_response = self._extract_player_response(updated_page_source)
        
        if updated_player_response:
            print("Re-extracted player response successfully", file=sys.stderr)
            
            # Save for debugging
            with open('debug_player_response_after_captions.json', 'w') as f:
                json.dump(updated_player_response, f, indent=2)
            print("DEBUG: Saved player response to debug_player_response_after_captions.json", file=sys.stderr)
            
            # Check for alternative caption data structures
            print("\nDEBUG: Searching for alternative caption sources...", file=sys.stderr)
            
            # Check streamingData for caption-related URLs
            streaming_data = updated_player_response.get('streamingData', {})
            if 'dashManifestUrl' in streaming_data:
                dash_url = streaming_data['dashManifestUrl']
                self.dash_manifest_url = dash_url  # Store for later refreshing
                print(f"  Found DASH manifest URL", file=sys.stderr)
                print(f"  Attempting to extract caption track from DASH manifest...", file=sys.stderr)
                
                # Try to parse DASH manifest for caption BaseURL
                caption_base_url_from_dash = self._parse_dash_manifest(dash_url)
                
                if caption_base_url_from_dash:
                    print(f"  ✓ Successfully extracted caption BaseURL from DASH manifest!", file=sys.stderr)
                    self.caption_base_url = caption_base_url_from_dash
                    
                    # Try to find the current live segment number
                    print(f"  Finding current live segment...", file=sys.stderr)
                    # Start from a reasonable estimate and search backwards
                    # Typically live streams have been running for a while, so start high
                    test_segment = 5765000  # Approximate current segment based on our observations
                    
                    # Binary search for current segment
                    found = False
                    for offset in range(0, 100, 10):
                        test_url = f"{self.caption_base_url}/sq/{test_segment + offset}"
                        try:
                            resp = self.session.head(test_url, timeout=2)
                            if resp.status_code == 200:
                                self.starting_segment = test_segment + offset
                                print(f"  ✓ Found current segment: {self.starting_segment}", file=sys.stderr)
                                found = True
                                break
                        except:
                            pass
                    
                    if not found:
                        # Fallback to a reasonable default
                        self.starting_segment = test_segment
                        print(f"  Using estimated starting segment: {self.starting_segment}", file=sys.stderr)
                else:
                    print(f"  Could not extract caption BaseURL from DASH manifest", file=sys.stderr)
                    
            if 'hlsManifestUrl' in streaming_data:
                print(f"  Found HLS manifest URL (may contain caption tracks)", file=sys.stderr)
            
            # Check for any keys containing 'caption', 'subtitle', or 'text'
            def search_for_captions(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        key_lower = key.lower()
                        if any(term in key_lower for term in ['caption', 'subtitle', 'text', 'timedtext']):
                            print(f"  Found potential caption key: {path}.{key}", file=sys.stderr)
                        search_for_captions(value, f"{path}.{key}")
                elif isinstance(obj, list) and len(obj) > 0:
                    search_for_captions(obj[0], f"{path}[0]")
            
            search_for_captions(updated_player_response, "playerResponse")
            
            updated_caption_tracks = self._find_caption_tracks(updated_player_response)
            
            if updated_caption_tracks:
                print(f"Found {len(updated_caption_tracks)} caption tracks after enabling captions!", file=sys.stderr)
                caption_tracks = updated_caption_tracks
                player_response = updated_player_response
                
                # Show details of available tracks
                for i, track in enumerate(updated_caption_tracks):
                    lang = track.get('languageCode', 'unknown')
                    name = track.get('name', {})
                    track_name = name.get('simpleText', 'Unknown') if isinstance(name, dict) else str(name)
                    base_url = track.get('baseUrl', '')
                    print(f"  Track {i+1}: {lang} - {track_name}", file=sys.stderr)
                    print(f"    URL available: {'Yes' if base_url else 'No'}", file=sys.stderr)
            else:
                print("Still no caption tracks after re-extraction", file=sys.stderr)

        # Handle method selection
        if self.method == 'dom':
            print("\n" + "═" * 70, file=sys.stderr)
            print("Selected method: DOM Scraping", file=sys.stderr)
            print("Captions will be extracted from rendered page elements", file=sys.stderr)
            print("═" * 70, file=sys.stderr)
            self.caption_base_url = None  # Force DOM scraping
        elif self.method == 'api':
            print("\n" + "═" * 70, file=sys.stderr)
            print("Selected method: API (DASH Manifest)", file=sys.stderr)
            print("═" * 70, file=sys.stderr)
            
            if not self.caption_base_url:
                raise Exception(
                    "API method selected but no caption BaseURL found.\n"
                    "This stream may not have API-accessible captions.\n"
                    "Try using --method dom instead."
                )
            else:
                print(f"✓ Caption BaseURL available", file=sys.stderr)
                print(f"  Base URL: {self.caption_base_url[:100]}...", file=sys.stderr)
                if self.starting_segment:
                    print(f"  Starting segment: {self.starting_segment}", file=sys.stderr)
                print("═" * 70, file=sys.stderr)

    def run(self, poll_interval: float = 2.0, output_dir: str = "output", save_interval: float = 30.0):
        """
        Run the scraper, continuously polling for new captions.

        Args:
            poll_interval: Time between polls in seconds
            output_dir: Directory to save caption files
            save_interval: Time interval in seconds to collate captions before saving (default: 30.0)
        """
        print("\nStarting caption capture (press Ctrl+C to stop)...", file=sys.stderr)
        print(f"Saving caption files every {save_interval} seconds to {output_dir}/", file=sys.stderr)
        
        use_api = self.method == 'api' and self.caption_base_url is not None

        # Create output directory if it doesn't exist
        import os
        os.makedirs(output_dir, exist_ok=True)

        try:
            collated_captions = []
            interval_start_time = time.time()
            current_segment = self.starting_segment if self.starting_segment else 0  # Track current segment for API method
            
            while True:
                if use_api:
                    # Fetch caption segments via API
                    captions = []
                    
                    # Refresh URL if needed (they expire)
                    self._refresh_caption_url()
                    
                    # Try to fetch the next few segments
                    for offset in range(5):  # Check next 5 segments
                        segment_text = self._fetch_caption_segment(current_segment + offset)
                        
                        if segment_text:
                            # Found a new segment
                            segment_id = f"seg_{current_segment + offset}"
                            
                            # Check if we've already seen this segment
                            if segment_id not in self.seen_segments:
                                self.seen_segments.add(segment_id)
                                captions.append({
                                    'text': segment_text,
                                    'timestamp': time.strftime("%H:%M:%S"),
                                    'segment': current_segment + offset
                                })
                                current_segment = current_segment + offset + 1
                                break  # Found a new segment, stop searching
                else:
                    # Scrape captions from DOM
                    captions = self._scrape_captions_from_dom()

                for caption in captions:
                    # Only use text for deduplication to avoid capturing same text multiple times
                    # Allow same text to appear again if it's been at least 5 seconds since last capture
                    caption_text = caption['text']
                    current_time = time.time()
                    
                    # Check if this is a new caption (different text or enough time has passed)
                    is_new_caption = (
                        caption_text != self.last_caption_text or 
                        (current_time - self.last_caption_time) > 5.0
                    )
                    
                    if is_new_caption:
                        self.last_caption_text = caption_text
                        self.last_caption_time = current_time
                        
                        # Add to collated captions
                        collated_captions.append(caption)
                        # Also output to stdout for monitoring
                        print(json.dumps(caption, ensure_ascii=False))
                        sys.stdout.flush()

                # Check if it's time to save the collated captions
                current_time = time.time()
                if current_time - interval_start_time >= save_interval:
                    if collated_captions:
                        # Generate filename with timestamp
                        timestamp = time.strftime("%Y%m%d-%H%M%S")
                        filename = f"{output_dir}/test-stream-{timestamp}.json"
                        
                        # Save collated captions to file
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump({
                                "interval_start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(interval_start_time)),
                                "interval_end": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_time)),
                                "duration_seconds": current_time - interval_start_time,
                                "caption_count": len(collated_captions),
                                "captions": collated_captions
                            }, f, ensure_ascii=False, indent=2)
                        
                        print(f"\nSaved {len(collated_captions)} captions to {filename}", file=sys.stderr)
                    
                    # Reset for next interval
                    collated_captions = []
                    interval_start_time = current_time

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            # Save any remaining captions before exiting
            if collated_captions:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                filename = f"{output_dir}/test-stream-{timestamp}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump({
                        "interval_start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(interval_start_time)),
                        "interval_end": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "duration_seconds": time.time() - interval_start_time,
                        "caption_count": len(collated_captions),
                        "captions": collated_captions
                    }, f, ensure_ascii=False, indent=2)
                print(f"\nSaved final {len(collated_captions)} captions to {filename}", file=sys.stderr)
            
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
  %(prog)s dQw4w9WgXcQ --method api
  %(prog)s "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --method dom --poll-interval 1.5
        """
    )

    parser.add_argument(
        'url',
        help='YouTube Live stream URL or Video ID'
    )

    parser.add_argument(
        '--method',
        type=str,
        choices=['dom', 'api'],
        default='dom',
        help='Caption extraction method: "dom" for DOM scraping (default), "api" for DASH manifest API'
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

    parser.add_argument(
        '--output-dir',
        type=str,
        default='output',
        help='Directory to save caption files (default: output)'
    )

    parser.add_argument(
        '--save-interval',
        type=float,
        default=30.0,
        help='Time interval in seconds to collate captions before saving (default: 30.0)'
    )

    args = parser.parse_args()

    scraper = None

    try:
        # Extract video ID from URL
        video_id = YouTubeLiveCaptionScraper._extract_video_id(args.url)

        # Create scraper instance with selected method
        scraper = YouTubeLiveCaptionScraper(
            video_id, 
            headless=not args.visible,
            method=args.method
        )

        # Initialize (load page, find captions)
        scraper.initialize()

        # Run the caption capture loop
        scraper.run(poll_interval=args.poll_interval, output_dir=args.output_dir, save_interval=args.save_interval)

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
