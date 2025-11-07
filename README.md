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

**REQ-01 (Ubiquitous)**: The system shall accept a YouTube Live stream URL or Video ID as a command-line argument.

**REQ-02 (Event-Driven)**: WHEN a valid URL/ID is provided, the system shall launch a selenium-controlled web browser to load the full YouTube "watch" page.

**REQ-03 (Event-Driven)**: WHEN the "watch" page has loaded, the system shall parse the page content to locate the live closed caption manifest URL.

**REQ-04 (Unwanted Behaviour)**: IF a live caption manifest URL cannot be found, THEN the system shall output a "No live captions found" error message and terminate.

**REQ-05 (State-Driven)**: WHILE the live stream is active, the system shall continuously poll the caption manifest for new data segments.

**REQ-06 (Event-Driven)**: WHEN a new caption segment is received, the system shall parse it to extract the caption text and its associated timestamp.

**REQ-07 (Event-Driven)**: WHEN caption text and a timestamp are successfully extracted, the system shall output them to the standard output as a single, structured JSON object.

**REQ-08 (Unwanted Behaviour)**: IF the live stream ends or the caption feed is interrupted, THEN the system shall output a notification message and terminate gracefully.

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
usage: capture_live_cc.py [-h] [--poll-interval POLL_INTERVAL] [--visible] url

Capture live closed captions from YouTube live streams

positional arguments:
  url                   YouTube Live stream URL or Video ID

optional arguments:
  -h, --help            show this help message and exit
  --poll-interval POLL_INTERVAL
                        Time between caption polls in seconds (default: 2.0)
  --visible             Run browser in visible mode (not headless)
```

### Examples

1. **Capture captions with default settings**:
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   ```

2. **Faster polling (check every 1 second)**:
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --poll-interval 1.0
   ```

3. **Run with visible browser** (useful for debugging):
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --visible
   ```

4. **Save captions to a file**:
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" > captions.jsonl
   ```

5. **Process captions with jq**:
   ```bash
   python capture_live_cc.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" | jq '.text'
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