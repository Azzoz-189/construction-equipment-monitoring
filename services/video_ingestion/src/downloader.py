"""
Video Downloader Module

Downloads YouTube videos using yt-dlp for processing by the CV pipeline.
Supports command-line URLs or batch downloads from a urls.txt file.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

import yt_dlp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Default paths
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "videos"
DEFAULT_URLS_FILE = DEFAULT_OUTPUT_DIR / "urls.txt"


class VideoDownloader:
    """
    Downloads YouTube videos using yt-dlp.
    
    Attributes:
        output_dir: Directory to save downloaded videos.
        max_height: Maximum video height (default 720p for CPU processing).
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        max_height: int = 720,
    ):
        """
        Initialize the video downloader.

        Args:
            output_dir: Directory to save downloaded videos. Defaults to videos/.
            max_height: Maximum video height in pixels. Defaults to 720.
        """
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.max_height = max_height
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Video output directory: {self.output_dir}")

    def _get_ydl_options(self) -> dict:
        """
        Get yt-dlp options for downloading.

        Returns:
            Dictionary of yt-dlp options.
        """
        return {
            # Output template
            "outtmpl": str(self.output_dir / "%(title)s.%(ext)s"),
            # Format selection: best mp4 up to max_height, or best available
            "format": f"bestvideo[height<={self.max_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={self.max_height}][ext=mp4]/best[height<={self.max_height}]",
            # Merge to mp4
            "merge_output_format": "mp4",
            # Progress hooks
            "progress_hooks": [self._progress_hook],
            # Logging
            "logger": logger,
            # Don't overwrite existing files
            "nooverwrites": True,
            # Ignore errors and continue with next video
            "ignoreerrors": True,
            # Restrict filenames to ASCII
            "restrictfilenames": True,
            # No playlist - download single videos only
            "noplaylist": True,
        }

    def _progress_hook(self, d: dict) -> None:
        """
        Progress hook for yt-dlp to show download progress.

        Args:
            d: Progress dictionary from yt-dlp.
        """
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                percent = (downloaded / total) * 100
                speed = d.get("speed", 0)
                speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "N/A"
                print(
                    f"\rDownloading: {percent:.1f}% | Speed: {speed_str}",
                    end="",
                    flush=True,
                )
        elif d["status"] == "finished":
            print()  # New line after progress
            logger.info(f"Download complete: {d.get('filename', 'Unknown')}")

    def download(self, url: str) -> bool:
        """
        Download a single video from URL.

        Args:
            url: YouTube video URL.

        Returns:
            True if download successful, False otherwise.
        """
        logger.info(f"Starting download: {url}")
        try:
            with yt_dlp.YoutubeDL(self._get_ydl_options()) as ydl:
                ydl.download([url])
            return True
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return False

    def download_batch(self, urls: List[str]) -> dict:
        """
        Download multiple videos from a list of URLs.

        Args:
            urls: List of YouTube video URLs.

        Returns:
            Dictionary with 'success' and 'failed' counts.
        """
        results = {"success": 0, "failed": 0, "total": len(urls)}
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Processing video {i}/{len(urls)}")
            if self.download(url):
                results["success"] += 1
            else:
                results["failed"] += 1
        
        logger.info(
            f"Batch download complete: {results['success']}/{results['total']} successful"
        )
        return results


def load_urls_from_file(filepath: Path) -> List[str]:
    """
    Load video URLs from a text file (one URL per line).

    Args:
        filepath: Path to the URLs file.

    Returns:
        List of URLs (empty lines and comments starting with # are ignored).
    """
    if not filepath.exists():
        logger.warning(f"URLs file not found: {filepath}")
        return []

    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith("#"):
                urls.append(line)
    
    logger.info(f"Loaded {len(urls)} URLs from {filepath}")
    return urls


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Download YouTube videos for equipment activity analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.downloader https://www.youtube.com/watch?v=VIDEO_ID
  python -m src.downloader URL1 URL2 URL3
  python -m src.downloader --from-file videos/urls.txt
  python -m src.downloader  # Reads from default videos/urls.txt
        """,
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="YouTube video URLs to download",
    )
    parser.add_argument(
        "--from-file",
        "-f",
        type=Path,
        default=None,
        help="Path to file containing URLs (one per line)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Output directory for downloaded videos",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=720,
        help="Maximum video height in pixels (default: 720)",
    )
    return parser.parse_args()


def main() -> int:
    """
    Main entry point for the video downloader.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    args = parse_args()
    
    # Determine output directory
    output_dir = args.output_dir
    if output_dir is None:
        # Check for Docker environment
        if os.path.exists("/app/videos"):
            output_dir = Path("/app/videos")
        else:
            output_dir = DEFAULT_OUTPUT_DIR
    
    # Initialize downloader
    downloader = VideoDownloader(
        output_dir=output_dir,
        max_height=args.max_height,
    )
    
    # Collect URLs from arguments and/or file
    urls = list(args.urls) if args.urls else []
    
    # Load from file if specified or if no URLs provided
    urls_file = args.from_file
    if urls_file is not None:
        urls.extend(load_urls_from_file(urls_file))
    elif not urls:
        # No URLs provided, try default file
        default_urls = load_urls_from_file(DEFAULT_URLS_FILE)
        urls.extend(default_urls)
    
    if not urls:
        logger.warning("No URLs provided. Use --help for usage information.")
        logger.info(f"You can also create {DEFAULT_URLS_FILE} with one URL per line.")
        return 0
    
    # Download videos
    results = downloader.download_batch(urls)
    
    if results["failed"] > 0:
        logger.warning(f"{results['failed']} video(s) failed to download")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
