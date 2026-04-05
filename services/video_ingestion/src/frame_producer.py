"""
Frame Producer Module

Provides a generator/iterator interface for extracting frames from video files.
Supports configurable frame skipping and resizing for efficient CPU processing.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Generator, Iterator, List, Optional, Tuple

import cv2
import numpy as np
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Default paths
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "settings.yaml"
DEFAULT_VIDEOS_DIR = Path(__file__).parent.parent.parent.parent / "videos"

# Frame tuple type: (frame_id, timestamp_str, frame_bgr)
FrameTuple = Tuple[int, str, np.ndarray]


class Config:
    """
    Configuration loader for video processing settings.
    
    Attributes:
        frame_skip: Process every Nth frame.
        resize_width: Target width for frame resizing.
        input_dir: Directory containing video files.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration from YAML file.

        Args:
            config_path: Path to settings.yaml. Defaults to config/settings.yaml.
        """
        self.config_path = config_path or self._find_config()
        self._load_config()

    def _find_config(self) -> Path:
        """
        Find the configuration file in standard locations.

        Returns:
            Path to the configuration file.

        Raises:
            FileNotFoundError: If config file is not found.
        """
        # Check Docker path first
        docker_config = Path("/app/config/settings.yaml")
        if docker_config.exists():
            return docker_config
        
        # Check default path
        if DEFAULT_CONFIG_PATH.exists():
            return DEFAULT_CONFIG_PATH
        
        raise FileNotFoundError(
            f"Configuration file not found. Checked: {docker_config}, {DEFAULT_CONFIG_PATH}"
        )

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        logger.info(f"Loading configuration from: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        video_config = config.get("video", {})
        self.frame_skip = video_config.get("frame_skip", 3)
        self.resize_width = video_config.get("resize_width", 640)
        self.input_dir = video_config.get("input_dir", "/app/videos")
        
        logger.info(
            f"Video config: frame_skip={self.frame_skip}, "
            f"resize_width={self.resize_width}, input_dir={self.input_dir}"
        )


def format_timestamp(frame_number: int, fps: float) -> str:
    """
    Convert frame number to timestamp string.

    Args:
        frame_number: The frame index (0-based).
        fps: Frames per second of the video.

    Returns:
        Timestamp string in format "HH:MM:SS.mmm".
    """
    if fps <= 0:
        return "00:00:00.000"
    
    total_seconds = frame_number / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def resize_frame(frame: np.ndarray, target_width: int) -> np.ndarray:
    """
    Resize frame maintaining aspect ratio.

    Args:
        frame: Input frame (BGR format).
        target_width: Target width in pixels.

    Returns:
        Resized frame with maintained aspect ratio.
    """
    height, width = frame.shape[:2]
    
    if width == target_width:
        return frame
    
    # Calculate new dimensions maintaining aspect ratio
    aspect_ratio = height / width
    new_height = int(target_width * aspect_ratio)
    
    return cv2.resize(
        frame,
        (target_width, new_height),
        interpolation=cv2.INTER_AREA if target_width < width else cv2.INTER_LINEAR,
    )


class FrameProducer:
    """
    Iterator/Generator for extracting frames from video files.
    
    Processes video files from a directory, applying frame skipping and resizing.
    Yields tuples of (frame_id, timestamp_str, frame_bgr).

    Attributes:
        videos_dir: Directory containing video files.
        frame_skip: Process every Nth frame.
        resize_width: Target width for frame resizing.
        config: Configuration object.
    """

    # Supported video extensions
    VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}

    def __init__(
        self,
        videos_dir: Optional[Path] = None,
        frame_skip: Optional[int] = None,
        resize_width: Optional[int] = None,
        config_path: Optional[Path] = None,
    ):
        """
        Initialize the frame producer.

        Args:
            videos_dir: Directory containing video files. If None, uses config.
            frame_skip: Process every Nth frame. If None, uses config (default 3).
            resize_width: Target width for resizing. If None, uses config (default 640).
            config_path: Path to configuration file.
        """
        # Load configuration
        self.config = Config(config_path)
        
        # Set parameters (command args override config)
        self.frame_skip = frame_skip if frame_skip is not None else self.config.frame_skip
        self.resize_width = resize_width if resize_width is not None else self.config.resize_width
        
        # Determine videos directory
        if videos_dir is not None:
            self.videos_dir = videos_dir
        elif os.path.exists(self.config.input_dir):
            self.videos_dir = Path(self.config.input_dir)
        else:
            self.videos_dir = DEFAULT_VIDEOS_DIR
        
        # Validate frame_skip
        if self.frame_skip < 1:
            raise ValueError("frame_skip must be at least 1")
        
        logger.info(
            f"FrameProducer initialized: videos_dir={self.videos_dir}, "
            f"frame_skip={self.frame_skip}, resize_width={self.resize_width}"
        )

    def get_video_files(self) -> List[Path]:
        """
        Get list of video files in the videos directory.

        Returns:
            Sorted list of video file paths.
        """
        if not self.videos_dir.exists():
            logger.warning(f"Videos directory does not exist: {self.videos_dir}")
            return []
        
        video_files = [
            f for f in self.videos_dir.iterdir()
            if f.is_file() and f.suffix.lower() in self.VIDEO_EXTENSIONS
        ]
        
        video_files.sort(key=lambda x: x.name)
        logger.info(f"Found {len(video_files)} video file(s) in {self.videos_dir}")
        
        return video_files

    def _process_video(
        self, video_path: Path, start_frame_id: int = 0
    ) -> Generator[FrameTuple, None, int]:
        """
        Process a single video file and yield frames.

        Args:
            video_path: Path to the video file.
            start_frame_id: Starting frame ID for this video.

        Yields:
            Tuples of (frame_id, timestamp_str, frame_bgr).

        Returns:
            The next frame ID after processing this video.
        """
        logger.info(f"Processing video: {video_path.name}")
        
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            logger.error(f"Failed to open video: {video_path}")
            return start_frame_id
        
        try:
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            logger.info(
                f"Video info: {width}x{height}, {fps:.2f} FPS, "
                f"{total_frames} frames, duration: {format_timestamp(total_frames, fps)}"
            )
            
            frame_id = start_frame_id
            video_frame_num = 0
            frames_yielded = 0
            
            while True:
                ret, frame = cap.read()
                
                if not ret:
                    break
                
                # Apply frame skip
                if video_frame_num % self.frame_skip == 0:
                    # Calculate timestamp
                    timestamp = format_timestamp(video_frame_num, fps)
                    
                    # Resize frame
                    resized_frame = resize_frame(frame, self.resize_width)
                    
                    yield (frame_id, timestamp, resized_frame)
                    
                    frame_id += 1
                    frames_yielded += 1
                
                video_frame_num += 1
            
            logger.info(
                f"Finished {video_path.name}: "
                f"{frames_yielded} frames yielded from {video_frame_num} total"
            )
            
            return frame_id
            
        finally:
            cap.release()

    def __iter__(self) -> Iterator[FrameTuple]:
        """
        Iterate over all frames from all videos in the directory.

        Yields:
            Tuples of (frame_id, timestamp_str, frame_bgr).
        """
        video_files = self.get_video_files()
        
        if not video_files:
            logger.warning("No video files found to process")
            return
        
        frame_id = 0
        
        for video_path in video_files:
            # Process video and update frame_id
            for frame_tuple in self._process_video(video_path, frame_id):
                yield frame_tuple
                frame_id = frame_tuple[0] + 1

    def process_single_video(self, video_path: Path) -> Generator[FrameTuple, None, None]:
        """
        Process a single video file.

        Args:
            video_path: Path to the video file.

        Yields:
            Tuples of (frame_id, timestamp_str, frame_bgr).
        """
        yield from self._process_video(video_path, start_frame_id=0)


def main():
    """
    Main entry point for testing the frame producer.
    
    Processes all videos in the configured directory and prints frame info.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract frames from video files for processing."
    )
    parser.add_argument(
        "--videos-dir",
        "-d",
        type=Path,
        default=None,
        help="Directory containing video files",
    )
    parser.add_argument(
        "--frame-skip",
        "-s",
        type=int,
        default=None,
        help="Process every Nth frame (default from config: 3)",
    )
    parser.add_argument(
        "--resize-width",
        "-w",
        type=int,
        default=None,
        help="Target width for resizing (default from config: 640)",
    )
    parser.add_argument(
        "--max-frames",
        "-m",
        type=int,
        default=None,
        help="Maximum number of frames to process (for testing)",
    )
    parser.add_argument(
        "--show-frames",
        action="store_true",
        help="Display frames in a window (requires GUI)",
    )
    
    args = parser.parse_args()
    
    # Initialize frame producer
    producer = FrameProducer(
        videos_dir=args.videos_dir,
        frame_skip=args.frame_skip,
        resize_width=args.resize_width,
    )
    
    # Process frames
    frame_count = 0
    try:
        for frame_id, timestamp, frame in producer:
            logger.info(
                f"Frame {frame_id}: timestamp={timestamp}, "
                f"shape={frame.shape}"
            )
            
            if args.show_frames:
                cv2.imshow("Frame", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    logger.info("User requested quit")
                    break
            
            frame_count += 1
            
            if args.max_frames and frame_count >= args.max_frames:
                logger.info(f"Reached max frames limit: {args.max_frames}")
                break
                
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
    finally:
        if args.show_frames:
            cv2.destroyAllWindows()
    
    logger.info(f"Total frames processed: {frame_count}")


if __name__ == "__main__":
    main()
