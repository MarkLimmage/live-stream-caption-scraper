# YouTube Live Stream Closed Caption Scraper

A robust Python system for capturing and outputting closed captions (CC) and associated metadata from YouTube live streams in real-time.

## Overview

This system provides a command-line tool that monitors YouTube live streams and extracts closed captions as they are generated. The tool uses Selenium to interact with the YouTube web interface, extracts caption manifest URLs from the embedded player data, and continuously polls for new caption segments. All captured captions are output as structured JSON objects to the standard output, making it easy to pipe the data to other processes or save to files.

### Key Features

- **Real-time Caption Capture**: Monitors live streams and outputs captions as they appear
- **Multiple Input Formats**: Accepts full YouTube URLs or just video IDs
- **Structured Output**: Emits captions as JSON objects with timestamps and text
- **Automatic WebDriver Management**: Uses webdriver-manager for hassle-free browser driver setup
- **Robust Parsing**: Handles YouTube's JSON3 caption format
- **Error Resilient**: Gracefully handles network issues and stream endings

## EARS Requirements

The system's requirements are specified using the EARS (Easy Approach to Requirements Syntax) format:

## Technical Architecture

### Dual Caption Extraction Approach

The scraper implements two methods for extracting live captions, selectable via the `--method` CLI parameter:

#### 1. API Method (DASH Manifest) - Experimental
- Extracts `ytInitialPlayerResponse` from the YouTube page
- Locates the DASH manifest URL in `streamingData.dashManifestUrl`
- Parses the DASH manifest XML to find caption track `BaseURL`
- Fetches caption segments sequentially using segment numbers
- **Limitations**: 
  - DASH manifest URLs expire (typically after 6 hours)
  - URL refresh logic may fail with expired manifests
  - Less reliable for long-running captures
  - Error recovery incomplete
- **Status**: Experimental, not recommended for production use

#### 2. DOM Scraping Method (Default, Recommended)
- Polls the caption container elements in the rendered page
- Extracts visible caption text using Selenium WebDriver
- Combines multi-line captions with newline separation
- Implements 5-second deduplication window to prevent duplicate captures
- **Advantages**: 
  - Reliable, works consistently without URL expiration issues
  - Proven for long-running captures (tested 8+ hours)
  - Robust error handling and recovery
- **Recommended** for production use and long-running captures

**Method Selection**: Use `--method dom` (default) or `--method api`. The scraper no longer automatically falls back between methods; if one fails, you must manually restart with a different method.

### Caption Flow

```
YouTube Page Load
  ├─> Extract ytInitialPlayerResponse
  ├─> Check for captions in playerResponse
  ├─> Parse DASH manifest URL
  │     └─> Extract caption track BaseURL
  │           ├─> API Method: Fetch segments by number
  │           └─> If API fails/expires → DOM Scraping
  └─> DOM Scraping: Poll caption container elements
        └─> Collate captions over configurable intervals
              └─> Save to timestamped JSON files
```

### DOM Scraping Workflow (Detailed)

The DOM scraping approach is the primary caption extraction method due to its reliability and simplicity. Here's how it works:

#### Phase 1: Initialization & Page Setup

1. **WebDriver Configuration**
   ```
   - Launch Chrome with Selenium WebDriver
   - Configure user agent to avoid bot detection
   - Set headless mode (optional)
   - Disable automation flags
   ```

2. **YouTube Page Loading** (`_load_youtube_page()`)
   ```
   Step 1: Navigate to YouTube watch URL
   Step 2: Wait for video player to load (WebDriverWait for #movie_player)
   Step 3: Wait 8 seconds for JavaScript execution and ad loading
   Step 4: Attempt to skip any pre-roll ads (click .ytp-ad-skip-button)
   Step 5: Click play button to start video playback
   Step 6: Enable captions via UI automation:
           - Click settings button (.ytp-settings-button)
           - Navigate to subtitles/CC menu item
           - Select first available caption option (avoid "off")
           - Close settings menu
   Step 7: Wait 2 seconds for captions to activate
   ```

3. **Browser State After Initialization**
   ```
   ✓ Video is playing
   ✓ Captions are enabled and visible on screen
   ✓ WebDriver session remains active
   ✓ Page stays loaded (no navigation)
   ```

#### Phase 2: Caption Extraction Loop

1. **DOM Element Polling** (`_scrape_captions_from_dom()`)
   
   **Selector Strategy** (tries in order until captions found):
   ```python
   Priority 1: "ytp-caption-segment"    # Primary YouTube caption element
   Priority 2: "captions-text"          # Alternative caption class
   Priority 3: "ytp-caption-window-container"  # Container element
   ```

   **Extraction Process**:
   ```
   For each selector:
     1. Find all elements matching the class name
     2. Check if element.is_displayed() (visible on screen)
     3. Extract element.text and strip whitespace
     4. Deduplicate within current poll (avoid double-counting)
     5. If captions found, stop trying other selectors
   ```

2. **Multi-line Caption Handling**
   ```
   YouTube often displays captions across multiple lines:
   
   Line 1: "with pomp pomp and ceremony It"
   Line 2: "derives directly from our"
   
   → Combined with newlines: "with pomp pomp and ceremony It\nderives directly from our"
   ```

3. **Caption Object Creation**
   ```python
   {
     'text': combined_text,        # All visible caption lines joined
     'timestamp': time.strftime("%H:%M:%S")  # Current time HH:MM:SS
   }
   ```

#### Phase 3: Deduplication Logic

**Problem**: YouTube captions update constantly (every ~2 seconds), but the same text may remain on screen for multiple poll cycles.

**Solution**: Time-window based deduplication in `run()` method:

```
For each captured caption:
  1. Compare caption text with last_caption_text
  2. Check time elapsed since last_caption_time
  3. Accept caption if:
     - Text is different from previous, OR
     - Same text but >5 seconds have passed
  4. Update last_caption_text and last_caption_time
```

**Why 5 seconds?**
- Captions typically change every 2-4 seconds
- 5 seconds allows legitimate repetition (speaker emphasis, replay)
- Prevents spam from rapid polling (2-second poll interval)

**Deduplication Example**:
```
22:32:20 → "colonial past yet it" ✓ (new text)
22:32:22 → "colonial past yet it" ✗ (duplicate, <5s)
22:32:24 → "colonial past yet it" ✗ (duplicate, <5s)
22:32:26 → "can most definitely"  ✓ (different text)
22:32:28 → "fill modern headlines" ✓ (different text)
```

#### Phase 4: Collation & File Saving

1. **Collation Window**
   ```
   Default: 30 seconds (configurable via --save-interval)
   
   Tracks:
   - interval_start_time: When collation period began
   - collated_captions[]: Array of all captions in this period
   ```

2. **Save Trigger**
   ```
   Every poll cycle:
     1. Check if (current_time - interval_start_time) >= save_interval
     2. If yes:
        - Generate filename: test-stream-YYYYMMDD-HHMMSS.json
        - Save collated captions with metadata
        - Reset collated_captions[] array
        - Reset interval_start_time
   ```

3. **JSON Output Structure**
   ```json
   {
     "interval_start": "2025-11-09 22:32:00",
     "interval_end": "2025-11-09 22:32:30",
     "duration_seconds": 30.0,
     "caption_count": 8,
     "captions": [
       {"text": "...", "timestamp": "22:32:20"},
       {"text": "...", "timestamp": "22:32:24"}
     ]
   }
   ```

#### Phase 5: Real-time Monitoring

**Dual Output**:
1. **stdout**: JSON objects for each caption (real-time monitoring)
   ```
   {"text": "colonial past yet it", "timestamp": "22:32:20"}
   {"text": "can most definitely", "timestamp": "22:32:24"}
   ```

2. **stderr**: Status messages and errors
   ```
   Using DOM scraping method
   Saved 8 captions to output/test-stream-20251109-223250.json
   ```

3. **File system**: Timestamped JSON files every 30 seconds

#### Phase 6: Graceful Termination

**Keyboard Interrupt (Ctrl+C)**:
```
1. Catch KeyboardInterrupt exception
2. Check if collated_captions[] has any unsaved data
3. If yes:
   - Generate final filename with current timestamp
   - Save partial batch with accurate duration_seconds
4. Print summary message
5. Clean up WebDriver session
```

**Benefits**:
- No data loss on interruption
- Partial intervals are preserved
- Accurate timing metadata even for incomplete intervals

### DOM Scraping Advantages

1. **Reliability**: Captions are always visible in the DOM when enabled
2. **Simplicity**: No URL expiration, authentication, or segment tracking
3. **Accuracy**: Gets exactly what users see on screen
4. **Multi-line Support**: Preserves caption formatting with newlines
5. **Robust Error Handling**: Silent failures, continues polling
6. **Real-time**: 2-second poll interval catches all caption updates

### DOM Scraping Limitations

1. **Browser Overhead**: Requires full Chrome/Chromium instance
2. **Resource Usage**: Higher CPU/memory than pure API approach
3. **Network Dependency**: Page must stay loaded and connected
4. **UI Coupling**: Breaks if YouTube changes caption CSS classes
5. **No Historical Access**: Can only capture live captions, not past segments

### Performance Characteristics

- **Poll Interval**: 2 seconds (configurable)
- **Caption Latency**: 2-4 seconds behind live stream
- **CPU Usage**: ~5-10% (Chrome rendering)
- **Memory Usage**: ~200-300 MB (Chrome + Selenium)
- **Network Bandwidth**: Minimal after initial page load
- **Deduplication Window**: 5 seconds
- **Collation Interval**: 30 seconds (configurable)

## Requirements

### Caption Extraction Requirements

**REQ-01**: The system shall extract video ID from YouTube watch URLs or short URLs

**REQ-02 (Event-Driven)**: WHEN a valid URL/ID is provided, the system shall launch a selenium-controlled web browser to load the full YouTube "watch" page.

**REQ-03 (Event-Driven)**: WHEN the "watch" page has loaded, the system shall parse the page content to locate the live closed caption manifest URL.

**REQ-04 (Unwanted Behaviour)**: IF a live caption manifest URL cannot be found, THEN the system shall output a "No live captions found" error message and terminate.

**REQ-05 (State-Driven)**: WHILE the live stream is active, the system shall continuously poll the caption manifest for new data segments.

**REQ-06 (Event-Driven)**: WHEN a new caption segment is received, the system shall parse it to extract the caption text and its associated timestamp.

**REQ-07 (Event-Driven)**: WHEN caption text and a timestamp are successfully extracted, the system shall output them to the standard output as a single, structured JSON object.

**REQ-08 (State-Driven)**: WHILE captions are being captured, the system shall collate all captured captions with their timestamps for a configurable time interval (default: 30 seconds).

**REQ-09 (Event-Driven)**: WHEN the collation time interval has elapsed, the system shall save all collated captions to a JSON file in the output directory and begin a new collation interval.

**REQ-10 (Ubiquitous)**: The system shall name output files using the format `test-stream-YYYYMMDD-HHMMSS.json` where the timestamp represents the end of the collation interval.

**REQ-11 (Ubiquitous)**: Each output JSON file shall contain the following structured data: interval start time, interval end time, duration in seconds, caption count, and an array of caption objects with text and timestamp fields.

**REQ-12 (Unwanted Behaviour)**: IF the live stream ends or the caption feed is interrupted, THEN the system shall output a notification message and terminate gracefully.

## Setup & Installation

### Prerequisites

- Python 3.7 or higher
- Google Chrome browser installed
- Internet connection

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/MarkLimmage/live-stream-caption-scraper.git
   cd live-stream-caption-scraper
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

   The `requirements.txt` includes:
   - `selenium`: For browser automation and dynamic page loading
   - `beautifulsoup4`: For HTML/XML parsing
   - `requests`: For HTTP requests to fetch caption data
   - `webdriver-manager`: For automatic WebDriver management

### WebDriver Configuration

The system uses `webdriver-manager` to automatically download and manage the ChromeDriver. On first run, it will:

1. Detect your Chrome browser version
2. Download the appropriate ChromeDriver
3. Cache it for future use

No manual WebDriver setup is required!

## Usage

### Basic Usage

Run the script with a YouTube live stream URL:

```bash
python capture_live_cc.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Or use just the video ID:

```bash
python capture_live_cc.py VIDEO_ID
```

### Command-Line Options

```
usage: capture_live_cc.py [-h] [--poll-interval POLL_INTERVAL] [--visible] 
                          [--output-dir OUTPUT_DIR] [--save-interval SAVE_INTERVAL]
                          [--method {dom,api}] url

Capture live closed captions from YouTube live streams

positional arguments:
  url                   YouTube Live stream URL or Video ID

optional arguments:
  -h, --help            show this help message and exit
  --poll-interval POLL_INTERVAL
                        Time between caption polls in seconds (default: 2.0)
  --visible             Run browser in visible mode (not headless)
  --output-dir OUTPUT_DIR
                        Directory to save caption files (default: output)
  --save-interval SAVE_INTERVAL
                        Time interval in seconds to collate captions before saving (default: 30.0)
  --method {dom,api}    Caption extraction method: 'dom' (default) or 'api' (default: dom)
```

### Caption Extraction Methods

The scraper supports two distinct methods for extracting captions, selectable via the `--method` parameter:

#### DOM Scraping Method (Default: `--method dom`)

**How it works**:
- Polls caption container elements in the rendered YouTube page
- Extracts visible caption text using Selenium WebDriver
- Implements 5-second deduplication window
- 2-second polling interval

**Advantages**:
- ✅ **Reliable**: No URL expiration issues
- ✅ **Simple**: Always works when captions are visible
- ✅ **Accurate**: Captures exactly what users see
- ✅ **Robust**: Continues working indefinitely

**Limitations**:
- ⚠️ Higher resource usage (requires full Chrome instance)
- ⚠️ ~200-300 MB memory footprint
- ⚠️ Coupled to YouTube's UI structure

**Best for**: Long-running captures, production use, reliability

#### API Method (`--method api`)

**How it works**:
- Extracts DASH manifest URL from `ytInitialPlayerResponse`
- Parses DASH manifest XML to find caption track `BaseURL`
- Fetches caption segments sequentially using segment numbers
- Periodically refreshes DASH manifest to get new URLs

**Advantages**:
- ✅ Lower resource overhead (no DOM polling)
- ✅ Direct access to caption data via API
- ✅ Potentially lower latency

**Current Limitations**:
- ❌ **URL Expiration**: DASH manifest URLs expire after ~6 hours
- ❌ **Refresh Logic Incomplete**: Current URL refresh may fail with expired manifests
- ❌ **Less Tested**: Newer implementation path
- ❌ **Error Handling**: May not gracefully handle all API failures

**Status**: ⚠️ **Experimental** - Works but has known reliability issues with long-running captures

**Best for**: Short captures (<6 hours), testing, development

#### Selecting a Method

```bash
# Use DOM scraping (default, most reliable)
python capture_live_cc.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Explicitly specify DOM method
python capture_live_cc.py "https://www.youtube.com/watch?v=VIDEO_ID" --method dom

# Use API method (experimental)
python capture_live_cc.py "https://www.youtube.com/watch?v=VIDEO_ID" --method api
```

**Note**: The scraper no longer automatically falls back between methods. If you select `--method api` and it fails, you must manually restart with `--method dom`.

### API Method: Known Issues & Remediation Plan

#### Issue 1: DASH Manifest URL Expiration

**Problem**: DASH manifest URLs expire after approximately 6 hours. When the URL expires, the refresh logic attempts to fetch a new manifest, but the original URL is already invalid.

**Symptoms**:
- Caption capture stops after 6+ hours
- HTTP 403 errors when fetching manifest
- "Refreshing caption URL" messages followed by failures

**Current Status**: Partial mitigation implemented (periodic refresh), but edge cases remain

**Remediation Steps**:
1. **Implement proactive refresh** (before expiration):
   - Track manifest age from initial extraction
   - Refresh at 5.5 hours (before 6-hour expiration)
   - Test with timestamps in manifest response

2. **Improve error recovery**:
   - Detect 403/410 HTTP errors specifically
   - Re-extract `ytInitialPlayerResponse` from live page
   - Parse fresh DASH manifest URL from updated response
   - Resume from last successful segment number

3. **Add resilience testing**:
   - Long-running test suite (8+ hours)
   - Simulate expiration scenarios
   - Validate segment continuity after refresh

4. **Consider hybrid approach**:
   - Start with API method for efficiency
   - Auto-switch to DOM method if API fails repeatedly
   - Add `--method auto` option for intelligent fallback

**Timeline**: 
- Phase 1 (proactive refresh): 1-2 days
- Phase 2 (error recovery): 2-3 days
- Phase 3 (testing): 2-3 days
- Phase 4 (hybrid approach): 3-5 days

#### Issue 2: Segment Number Estimation

**Problem**: Initial segment number is estimated from timestamp, which may not be accurate if the stream started at an unusual time or has gaps.

**Symptoms**:
- Missing initial captions
- 404 errors at startup
- Delayed caption capture start

**Remediation Steps**:
1. Parse segment duration from DASH manifest `<SegmentTemplate duration="...">` attribute
2. Calculate precise segment number from stream start time
3. Implement binary search to find current live edge if estimation fails
4. Fall back to segment 0 and scan forward if all else fails

**Timeline**: 1-2 days

#### Issue 3: Missing Caption Availability Check

**Problem**: API method may fail if stream doesn't provide DASH manifest captions (some streams only have captions in the UI layer).

**Symptoms**:
- "API method selected but no caption BaseURL found" error
- Immediate failure at startup

**Remediation Steps**:
1. Add caption availability pre-check before committing to API method
2. Provide clearer error messages suggesting DOM fallback
3. Add `--auto-detect` option to choose best method based on available APIs

**Timeline**: 1 day

### Output Format

The system saves captions to JSON files at regular intervals (default: 30 seconds). Each file contains:

```json
{
  "interval_start": "2025-11-07 18:30:00",
  "interval_end": "2025-11-07 18:30:30",
  "duration_seconds": 30.05,
  "caption_count": 15,
  "captions": [
    {
      "text": "Caption text here",
      "timestamp": "18:30:05"
    },
    {
      "text": "Another caption",
      "timestamp": "18:30:10"
    }
  ]
}
```

**File Naming Convention**: `test-stream-YYYYMMDD-HHMMSS.json`

Example: `test-stream-20251107-183030.json`

### Examples

1. **Capture captions with default settings** (DOM method, saves to `output/` every 30 seconds):
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   ```

2. **Use API method for lower resource usage** (experimental):
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --method api
   ```

3. **Save files every 60 seconds to a custom directory**:
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --save-interval 60 --output-dir captions
   ```

4. **Faster polling (check every 1 second)** with DOM method:
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --poll-interval 1.0
   ```

5. **Run with visible browser** (useful for debugging):
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --visible
   ```

6. **5-minute capture test with API method**:
   ```bash
   timeout 330 python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --method api
   ```

7. **Long-running production capture** (DOM method recommended):
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --method dom --save-interval 60
   ```

### Stopping the Script

Press `Ctrl+C` to stop the caption capture gracefully. The script will output a notification and clean up resources.

## Output Format

The script outputs one JSON object per line (JSON Lines format) to standard output. Each caption appears as:

```json
{"timestamp": "00:01:23.450", "text": "Hello and welcome to the live stream."}
{"timestamp": "00:01:25.100", "text": "Today we are discussing..."}
```

### JSON Object Structure

Each JSON object contains:

- **`timestamp`** (string): The caption's timestamp in `HH:MM:SS.mmm` format
  - This is the relative stream time (time since the stream started)
  - Format: Hours (00-99), Minutes (00-59), Seconds (00-59), Milliseconds (000-999)
  
- **`text`** (string): The caption text content
  - UTF-8 encoded, preserving special characters and emojis
  - Whitespace is trimmed

### Status Messages

The script outputs status messages to standard error (stderr), separate from caption data:

- `Loading YouTube page...`
- `Extracting player response...`
- `Finding caption tracks...`
- `Found caption track: [URL]`
- `Starting caption capture (press Ctrl+C to stop)...`
- Error messages and warnings

This separation allows you to easily redirect caption data while still seeing status updates:

```bash
python capture_live_cc.py VIDEO_ID 2> status.log > captions.jsonl
```

## Error Handling & Limitations

### Common Error Scenarios

1. **No Live Captions Found**
   - **Cause**: The stream does not have closed captions enabled, or they are not yet available
   - **Message**: `"No live captions found"`
   - **Solution**: Verify that the stream has captions enabled in YouTube's live settings

2. **Invalid URL or Video ID**
   - **Cause**: The provided URL or video ID is not in a recognized format
   - **Message**: `"Error: Invalid URL or Video ID"`
   - **Solution**: Check that the URL is a valid YouTube watch URL or an 11-character video ID

3. **Page Load Failure**
   - **Cause**: Network issues, YouTube being unavailable, or the video not existing
   - **Message**: `"Failed to load YouTube page"`
   - **Solution**: Check your internet connection and verify the video exists

4. **Stream Ends or Feed Interrupted**
   - **Cause**: The live stream ended or the caption feed stopped
   - **Message**: `"Live stream may have ended or caption feed was interrupted."`
   - **Behavior**: Script terminates gracefully

### Known Limitations

1. **YouTube UI Changes**: This tool parses YouTube's web interface, which may change without notice. If YouTube significantly updates their player structure, the script may need updates.

2. **Rate Limiting**: While unlikely, excessive polling or running multiple instances might trigger rate limiting from YouTube.

3. **Caption Delay**: There may be a slight delay (typically 1-3 seconds) between when captions appear on YouTube and when they are captured by this tool.

4. **Language Support**: The script prefers English captions but will fall back to any available language. For streams with multiple caption tracks, it selects the first available English track or the first track if no English is available.

5. **Browser Dependency**: Requires Chrome browser to be installed. The script will not work if Chrome is not available.

6. **Network Requirements**: Continuous internet connection is required. Brief network interruptions are handled, but extended outages will cause the script to fail.

### Debugging Tips

1. **Use `--visible` flag**: Run with `--visible` to see the browser and diagnose page loading issues:
   ```bash
   python capture_live_cc.py VIDEO_ID --visible
   ```

2. **Check status messages**: Status messages are printed to stderr - monitor them for diagnostics:
   ```bash
   python capture_live_cc.py VIDEO_ID
   ```

3. **Verify stream is live**: Ensure the stream is actually live and has captions enabled before running the script.

4. **Test with known working stream**: Try with a popular live news stream that reliably has captions enabled.

## Technical Details

### How It Works

1. **Page Loading**: Selenium launches a Chrome browser (headless by default) and navigates to the YouTube watch page for the specified video.

2. **Data Extraction**: The script parses the page's HTML to find the `ytInitialPlayerResponse` JavaScript object, which contains metadata about the video and available caption tracks.

3. **Caption Track Selection**: From the player response, the script identifies available caption tracks and selects an appropriate one (preferring English).

4. **Continuous Polling**: The script enters a loop where it periodically fetches the caption data from the base URL.

5. **Parsing & Output**: Each caption segment is parsed from YouTube's JSON3 format, deduplicated, and output as a JSON object.

### Caption Format

YouTube live streams use a JSON-based format (often called "JSON3") for captions. This format includes:
- Events with timestamps (`tStartMs`)
- Text segments (`segs`) containing UTF-8 text
- Duration information

The script handles this format and converts it to a simple, standardized JSON output.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

### Development Setup

```bash
git clone https://github.com/MarkLimmage/live-stream-caption-scraper.git
cd live-stream-caption-scraper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## License

This project is licensed under the MIT License.

## Disclaimer

This tool is for educational and research purposes. Please respect YouTube's Terms of Service and use this tool responsibly. The authors are not responsible for any misuse of this software.