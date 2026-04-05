"""
CV Service Main Entrypoint.

Processes video files through the detection -> tracking -> motion analysis ->
activity classification -> time tracking -> Kafka publishing pipeline.

This is the main orchestrator that wires together all CV pipeline components.
"""

import os
import sys
import signal
import logging
import time
import json
import subprocess
from pathlib import Path
from typing import Optional, Iterator, Tuple, Any
from datetime import datetime

import cv2
import yaml
import numpy as np

# Local imports
from .detector import EquipmentDetector
from .tracker import EquipmentTracker
from .motion_analyzer import MotionAnalyzer
from .activity_classifier import ActivityClassifier
from .time_tracker import TimeTracker
from .kafka_producer import EquipmentKafkaProducer

# Frame output directory
FRAME_OUTPUT_DIR = Path("/app/frames")
MAX_FRAME_HISTORY = 100

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class CVServicePipeline:
    """
    Main CV processing pipeline orchestrator.
    
    Coordinates all components: detection, tracking, motion analysis,
    activity classification, time tracking, and event publishing.
    """
    
    def __init__(self, config_path: str = "/app/config/settings.yaml"):
        """
        Initialize the CV service pipeline.
        
        Args:
            config_path: Path to the YAML configuration file
        """
        self._config = self._load_config(config_path)
        self._running = False
        self._shutdown_requested = False
        self.current_video_source = None
        
        # Initialize all pipeline components
        self._init_components()
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info("CV Service Pipeline initialized successfully")
    
    def _load_config(self, config_path: str) -> dict:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to config file
        
        Returns:
            Configuration dictionary
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config file is invalid
        """
        config_file = Path(config_path)
        
        # Try multiple config locations
        search_paths = [
            config_file,
            Path("/app/config/settings.yaml"),
            Path("config/settings.yaml"),
            Path("../../../config/settings.yaml"),
        ]
        
        for path in search_paths:
            if path.exists():
                logger.info(f"Loading config from: {path}")
                with open(path, "r") as f:
                    config = yaml.safe_load(f)
                return config
        
        raise FileNotFoundError(
            f"Config file not found. Searched: {[str(p) for p in search_paths]}"
        )
    
    def _init_components(self) -> None:
        """Initialize all pipeline components with configuration."""
        logger.info("Initializing pipeline components...")
        
        # Detection component
        detection_config = self._config.get("detection", {})
        self._detector = EquipmentDetector(detection_config)
        logger.info("Equipment detector initialized")
        
        # Tracking component
        tracking_config = self._config.get("tracking", {})
        self._tracker = EquipmentTracker(tracking_config)
        logger.info("Equipment tracker initialized")
        
        # Motion analysis component
        motion_config = self._config.get("motion", {})
        self._motion_analyzer = MotionAnalyzer(motion_config)
        logger.info("Motion analyzer initialized")
        
        # Activity classification component
        activity_config = self._config.get("activity", {})
        self._activity_classifier = ActivityClassifier(activity_config)
        logger.info("Activity classifier initialized")
        
        # Time tracking component
        self._time_tracker = TimeTracker()
        logger.info("Time tracker initialized")
        
        # Kafka producer
        kafka_config = self._config.get("kafka", {})
        self._kafka_producer = EquipmentKafkaProducer(kafka_config)
        logger.info("Kafka producer initialized")
        
        # Video configuration
        self._video_config = self._config.get("video", {})
        self._frame_skip = self._video_config.get("frame_skip", 3)
        self._resize_width = self._video_config.get("resize_width", 640)
        self._input_dir = self._video_config.get("input_dir", "/app/videos")
        
        # Ensure frame output directory exists
        FRAME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Frame output directory: {FRAME_OUTPUT_DIR}")
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        logger.info("Signal handlers configured")
    
    def _signal_handler(self, signum: int, frame: Any) -> None:
        """
        Handle shutdown signals gracefully.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        logger.info(f"Received signal {signal_name}, initiating graceful shutdown...")
        self._shutdown_requested = True
    
    def _get_video_files(self) -> list:
        """
        Get list of video files from input directory.
        
        Returns:
            List of video file paths
        """
        video_dir = Path(self._input_dir)
        if not video_dir.exists():
            logger.warning(f"Video directory not found: {video_dir}")
            return []
        
        # Supported video extensions
        extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        
        video_files = [
            f for f in video_dir.iterdir()
            if f.is_file() and f.suffix.lower() in extensions
        ]
        
        logger.info(f"Found {len(video_files)} video files in {video_dir}")
        return sorted(video_files)
    
    def _probe_video(self, video_path: Path) -> Tuple[float, int, int, int]:
        """
        Probe video file for metadata using ffprobe.
        
        Returns:
            Tuple of (fps, total_frames, width, height)
        """
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_streams', '-select_streams', 'v:0', str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                info = json.loads(result.stdout)
                stream = info.get('streams', [{}])[0]
                
                # Parse FPS from r_frame_rate (e.g. "30/1")
                fps_str = stream.get('r_frame_rate', '30/1')
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den) if float(den) != 0 else 30.0
                else:
                    fps = float(fps_str)
                
                total_frames = int(stream.get('nb_frames', 0))
                width = int(stream.get('width', 640))
                height = int(stream.get('height', 480))
                return fps, total_frames, width, height
        except Exception as e:
            logger.warning(f"ffprobe failed for {video_path.name}: {e}")
        
        return 30.0, 0, 640, 480

    def _iterate_video_frames(
        self, 
        video_path: Path
    ) -> Iterator[Tuple[int, str, np.ndarray]]:
        """
        Iterate over frames in a video file.
        
        Applies frame skipping and resizing based on configuration.
        Uses OpenCV first; falls back to ffmpeg subprocess for codecs
        OpenCV cannot handle (e.g. AV1).
        
        Args:
            video_path: Path to video file
        
        Yields:
            Tuple of (frame_id, timestamp_str, frame_array)
        """
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            logger.warning(f"OpenCV cannot open video: {video_path.name}, trying ffmpeg fallback")
            yield from self._iterate_video_frames_ffmpeg(video_path)
            return
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Calculate effective FPS accounting for frame skip
        effective_fps = fps / self._frame_skip
        self._effective_fps = effective_fps
        
        logger.info(
            f"Processing video: {video_path.name} "
            f"({total_frames} frames, {fps:.1f} FPS)"
        )
        
        frame_idx = 0
        processed_count = 0
        
        try:
            while cap.isOpened() and not self._shutdown_requested:
                ret, frame = cap.read()
                
                if not ret:
                    # If we never read any frame, the codec is unsupported
                    if frame_idx == 0:
                        logger.warning(
                            f"OpenCV cannot decode {video_path.name} "
                            f"(codec unsupported), trying ffmpeg fallback"
                        )
                        cap.release()
                        yield from self._iterate_video_frames_ffmpeg(video_path)
                        return
                    break
                
                # Apply frame skip
                if frame_idx % self._frame_skip != 0:
                    frame_idx += 1
                    continue
                
                # Calculate timestamp
                time_seconds = frame_idx / fps
                timestamp = self._format_timestamp(time_seconds)
                
                # Resize frame if configured
                if self._resize_width and frame.shape[1] != self._resize_width:
                    aspect_ratio = frame.shape[0] / frame.shape[1]
                    new_height = int(self._resize_width * aspect_ratio)
                    frame = cv2.resize(
                        frame, 
                        (self._resize_width, new_height),
                        interpolation=cv2.INTER_LINEAR
                    )
                
                yield processed_count, timestamp, frame
                
                processed_count += 1
                frame_idx += 1
                
        finally:
            cap.release()
            logger.info(f"Processed {processed_count} frames from {video_path.name}")

    def _iterate_video_frames_ffmpeg(
        self,
        video_path: Path
    ) -> Iterator[Tuple[int, str, np.ndarray]]:
        """
        Fallback frame iterator using ffmpeg subprocess for codecs
        that OpenCV cannot decode (e.g. AV1/dav1d).
        
        Args:
            video_path: Path to video file
        
        Yields:
            Tuple of (frame_id, timestamp_str, frame_array)
        """
        fps, total_frames, orig_w, orig_h = self._probe_video(video_path)
        
        # Determine output size
        out_w = self._resize_width or orig_w
        aspect = orig_h / orig_w if orig_w > 0 else 0.75
        out_h = int(out_w * aspect)
        # Ensure even dimensions for ffmpeg
        out_h = out_h if out_h % 2 == 0 else out_h + 1
        out_w = out_w if out_w % 2 == 0 else out_w + 1
        
        effective_fps = fps / self._frame_skip
        self._effective_fps = effective_fps
        
        logger.info(
            f"Processing video (ffmpeg): {video_path.name} "
            f"({total_frames} frames, {fps:.1f} FPS, output {out_w}x{out_h})"
        )
        
        # Build ffmpeg command to output raw BGR24 frames
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', f'{out_w}x{out_h}',
            '-v', 'warning',
            '-'
        ]
        
        frame_size = out_w * out_h * 3  # BGR24
        
        proc = None
        frame_idx = 0
        processed_count = 0
        
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=frame_size * 2
            )
            
            while not self._shutdown_requested:
                raw = proc.stdout.read(frame_size)
                if len(raw) != frame_size:
                    break  # End of stream or error
                
                # Apply frame skip
                if frame_idx % self._frame_skip != 0:
                    frame_idx += 1
                    continue
                
                frame = np.frombuffer(raw, dtype=np.uint8).reshape((out_h, out_w, 3))
                
                time_seconds = frame_idx / fps
                timestamp = self._format_timestamp(time_seconds)
                
                yield processed_count, timestamp, frame.copy()
                
                processed_count += 1
                frame_idx += 1
                
        except Exception as e:
            logger.error(f"ffmpeg fallback error for {video_path.name}: {e}")
        finally:
            if proc:
                proc.stdout.close()
                proc.terminate()
                proc.wait(timeout=5)
            logger.info(f"Processed {processed_count} frames (ffmpeg) from {video_path.name}")
    
    def _format_timestamp(self, seconds: float) -> str:
        """
        Format seconds as HH:MM:SS.mmm timestamp.
        
        Args:
            seconds: Time in seconds
        
        Returns:
            Formatted timestamp string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    def _build_event(
        self,
        frame_id: int,
        timestamp: str,
        equipment: dict,
        activities: dict,
        time_stats: dict
    ) -> dict:
        """
        Build a Kafka event from processing results.
        
        Args:
            frame_id: Current frame number
            timestamp: Frame timestamp
            equipment: Tracked equipment info
            activities: Activity classification results
            time_stats: Time tracking statistics
        
        Returns:
            Event dictionary matching the Kafka schema
        """
        equipment_id = equipment.get("equipment_id", "UNKNOWN")
        equipment_class = equipment.get("equipment_class", "unknown")
        
        # Get activity info for this equipment
        activity_info = activities.get(equipment_id, {})
        current_activity = activity_info.get("activity", "WAITING")
        motion_source = activity_info.get("motion_source", "none")
        
        # Determine state from activity
        current_state = "ACTIVE" if current_activity != "WAITING" else "INACTIVE"
        
        # Get time stats for this equipment
        equip_stats = time_stats.get(equipment_id, {})
        
        return {
            "frame_id": frame_id,
            "video_source": self.current_video_source,
            "equipment_id": equipment_id,
            "equipment_class": equipment_class,
            "timestamp": timestamp,
            "utilization": {
                "current_state": current_state,
                "current_activity": current_activity,
                "motion_source": motion_source
            },
            "time_analytics": {
                "total_tracked_seconds": equip_stats.get("total_tracked_seconds", 0.0),
                "total_active_seconds": equip_stats.get("total_active_seconds", 0.0),
                "total_idle_seconds": equip_stats.get("total_idle_seconds", 0.0),
                "utilization_percent": equip_stats.get("utilization_percent", 0.0)
            }
        }
    
    def process_frame(
        self,
        frame_id: int,
        timestamp: str,
        frame: np.ndarray,
        prev_gray: Optional[np.ndarray],
        fps: float = 30.0
    ) -> Tuple[list, Optional[np.ndarray]]:
        """
        Process a single frame through the entire pipeline.
        
        Args:
            frame_id: Current frame ID
            timestamp: Frame timestamp
            frame: BGR frame array
            prev_gray: Previous grayscale frame for motion analysis
        
        Returns:
            Tuple of (list of events, current grayscale frame)
        """
        events = []
        
        # 1. Detect equipment in frame
        detections = self._detector.detect(frame)
        
        # 2. Track detected equipment
        tracked = self._tracker.update(detections, frame)
        
        # 3. Convert to grayscale for motion analysis
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 4. Analyze motion (needs previous gray frame)
        motion_results = {}
        if prev_gray is not None:
            motion_results = self._motion_analyzer.analyze(prev_gray, gray, tracked)
        
        # 5. Classify activity for each equipment
        activities = self._activity_classifier.classify(tracked, motion_results)
        
        # 6. Update time tracking
        time_stats = self._time_tracker.update(tracked, activities, timestamp, fps=fps)
        
        # 7. Build events for each tracked equipment
        for equipment in tracked:
            event = self._build_event(
                frame_id, timestamp, equipment, activities, time_stats
            )
            events.append(event)
        
        return events, gray, tracked, activities
    
    def _save_annotated_frame(
        self,
        frame: np.ndarray,
        frame_id: int,
        tracked: list,
        activities: dict
    ) -> None:
        """
        Save an annotated frame with bounding boxes and labels.
        
        Args:
            frame: Raw BGR frame from video
            frame_id: Current frame number
            tracked: List of tracked equipment dicts
            activities: Dict mapping equipment_id to activity info
        """
        try:
            # Create a copy to avoid modifying the original
            annotated = frame.copy()
            
            # Colors
            COLOR_ACTIVE = (0, 255, 0)  # Green BGR
            COLOR_INACTIVE = (0, 0, 255)  # Red BGR
            COLOR_TEXT_BG = (0, 0, 0)  # Black background
            COLOR_TEXT = (255, 255, 255)  # White text
            
            # Font settings
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            thickness = 1
            
            # Draw each tracked equipment
            for equipment in tracked:
                eq_id = equipment.get("equipment_id", "UNKNOWN")
                eq_class = equipment.get("equipment_class", "unknown")
                bbox = equipment.get("bbox", [])
                
                if len(bbox) != 4:
                    continue
                
                x1, y1, x2, y2 = [int(v) for v in bbox]
                
                # Get activity info
                activity_info = activities.get(eq_id, {})
                current_state = activity_info.get("current_state", "INACTIVE")
                current_activity = activity_info.get("activity", "WAITING")
                
                # Determine color based on state
                color = COLOR_ACTIVE if current_state == "ACTIVE" else COLOR_INACTIVE
                
                # Draw bounding box
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                
                # Top label: Equipment ID + Class
                top_label = f"{eq_id} ({eq_class})"
                (tw, th), _ = cv2.getTextSize(top_label, font, font_scale, thickness)
                
                # Draw filled background for top label
                cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 4, y1), COLOR_TEXT_BG, -1)
                cv2.putText(annotated, top_label, (x1 + 2, y1 - 4), font, font_scale, COLOR_TEXT, thickness)
                
                # Bottom label: Activity
                bottom_label = current_activity
                (bw, bh), _ = cv2.getTextSize(bottom_label, font, font_scale, thickness)
                
                # Draw filled background for bottom label
                cv2.rectangle(annotated, (x1, y2), (x1 + bw + 4, y2 + bh + 8), COLOR_TEXT_BG, -1)
                cv2.putText(annotated, bottom_label, (x1 + 2, y2 + bh + 4), font, font_scale, color, thickness)
            
            # Frame info overlay at top-left
            info_text = f"Frame: {frame_id} | Equipment: {len(tracked)}"
            (iw, ih), _ = cv2.getTextSize(info_text, font, 0.6, 2)
            cv2.rectangle(annotated, (5, 5), (15 + iw, 15 + ih), COLOR_TEXT_BG, -1)
            cv2.putText(annotated, info_text, (10, 10 + ih), font, 0.6, COLOR_TEXT, 2)
            
            # Save latest frame (overwrite)
            latest_path = FRAME_OUTPUT_DIR / "latest_frame.jpg"
            cv2.imwrite(str(latest_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            # Save history frame
            history_path = FRAME_OUTPUT_DIR / f"frame_{frame_id:06d}.jpg"
            cv2.imwrite(str(history_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            # Cleanup old frames periodically
            if frame_id % 50 == 0:
                self._cleanup_old_frames()
                
        except Exception as e:
            logger.error(f"Error saving annotated frame {frame_id}: {e}")
    
    def _cleanup_old_frames(self) -> None:
        """
        Remove old frame files, keeping only the last MAX_FRAME_HISTORY frames.
        """
        try:
            # Get all history frame files
            frame_files = sorted(FRAME_OUTPUT_DIR.glob("frame_*.jpg"))
            
            # Remove oldest files if we have too many
            if len(frame_files) > MAX_FRAME_HISTORY:
                files_to_remove = frame_files[:-MAX_FRAME_HISTORY]
                for f in files_to_remove:
                    try:
                        f.unlink()
                    except Exception:
                        pass
                        
                logger.debug(f"Cleaned up {len(files_to_remove)} old frame files")
                
        except Exception as e:
            logger.error(f"Error cleaning up old frames: {e}")
    
    def _get_selected_video(self) -> Optional[str]:
        """Check if a specific video has been selected via control file."""
        control_file = Path("/app/frames/selected_video.txt")
        try:
            if control_file.exists():
                selected = control_file.read_text().strip()
                if selected and selected.lower() != "all":
                    logger.debug(f"Selected video from control file: '{selected}'")
                    return selected
        except Exception as e:
            logger.warning(f"Error reading selected_video.txt: {e}")
        return None

    def process_video(self, video_path: Path) -> None:
        """
        Process a single video file through the pipeline.
        
        Args:
            video_path: Path to the video file
        """
        logger.info(f"Starting processing: {video_path.name}")
        start_time = time.time()
        
        prev_gray: Optional[np.ndarray] = None
        event_count = 0
        self.current_video_source = video_path.name
        current_video_filename = video_path.name
        
        # Reset frame counter for each new video
        self._frame_id = 0
        
        # Reset all pipeline components for clean per-channel state
        self._reset_pipeline_components()
        
        for frame_id, timestamp, frame in self._iterate_video_frames(video_path):
            if self._shutdown_requested:
                logger.info("Shutdown requested, stopping video processing")
                break
            
            try:
                # Check every 10 frames if video selection changed
                if frame_id > 0 and frame_id % 10 == 0:
                    new_selected = self._get_selected_video()
                    if new_selected and new_selected != current_video_filename:
                        logger.info(f"Video channel switch requested: {new_selected}")
                        break  # Break out of current video processing loop
                
                # Process frame through pipeline
                events, gray, tracked, activities = self.process_frame(frame_id, timestamp, frame, prev_gray, fps=self._effective_fps)
                prev_gray = gray
                
                # Save annotated frame for dashboard visualization
                # Always save so MJPEG stream gets fresh frames even without detections
                self._save_annotated_frame(frame, frame_id, tracked, activities)
                
                # Publish events to Kafka
                for event in events:
                    self._kafka_producer.publish(event)
                    event_count += 1
                
                # Log progress periodically
                if frame_id > 0 and frame_id % 100 == 0:
                    logger.info(f"Processed frame {frame_id}, {event_count} events published")
                    
            except Exception as e:
                logger.error(f"Error processing frame {frame_id}: {e}", exc_info=True)
                continue
        
        # Flush remaining events
        self._kafka_producer.flush()
        
        elapsed = time.time() - start_time
        logger.info(
            f"Completed {video_path.name}: {event_count} events in {elapsed:.1f}s"
        )
    
    def _reset_pipeline_components(self) -> None:
        """Reset all pipeline components for a fresh channel start."""
        tracking_config = self._config.get("tracking", {})
        self._tracker = EquipmentTracker(tracking_config)
        
        activity_config = self._config.get("activity", {})
        self._activity_classifier = ActivityClassifier(activity_config)
        
        self._time_tracker = TimeTracker()
        
        # Re-create motion analyzer for clean state
        motion_config = self._config.get("motion", {})
        self._motion_analyzer = MotionAnalyzer(motion_config)
        
        logger.info("Pipeline components reset for new channel")

    def run_file_mode(self) -> None:
        """
        Process all video files in the input directory.
        
        Loops continuously for demo purposes - after all videos are
        processed, restarts from the beginning.
        Supports video channel selection via control file.
        """
        logger.info("Starting CV Service in FILE mode (looping)")
        self._running = True
        
        loop_count = 0
        
        while not self._shutdown_requested:
            loop_count += 1
            logger.info(f"=== Video processing loop #{loop_count} ===")
            
            video_files = self._get_video_files()
            
            if not video_files:
                logger.warning("No video files found to process, waiting...")
                time.sleep(5.0)
                continue
            
            # Check if a specific video is selected
            selected = self._get_selected_video()
            
            if selected:
                # Find the selected video in the list
                selected_path = None
                for vf in video_files:
                    if vf.name == selected:
                        selected_path = vf
                        break
                
                if selected_path:
                    logger.info(f"Channel selected: {selected}")
                    self.process_video(selected_path)
                else:
                    logger.warning(f"Selected video '{selected}' not found in video directory, processing all")
                    for video_path in video_files:
                        if self._shutdown_requested:
                            break
                        # Re-check selection between videos
                        new_selected = self._get_selected_video()
                        if new_selected and new_selected != video_path.name:
                            logger.info(f"Video channel switch detected, breaking loop")
                            break
                        self.process_video(video_path)
            else:
                # No specific selection - process all videos sequentially
                for video_path in video_files:
                    if self._shutdown_requested:
                        break
                    # Re-check selection between videos
                    new_selected = self._get_selected_video()
                    if new_selected:
                        logger.info(f"Video channel selected mid-loop: {new_selected}")
                        break  # Will pick up the selection on next loop iteration
                    self.process_video(video_path)
            
            if not self._shutdown_requested:
                logger.info(f"Loop #{loop_count} complete. Restarting in 2 seconds...")
                time.sleep(2.0)
        
        self._running = False
        logger.info("File mode processing stopped")
    
    def run_continuous_mode(self, poll_interval: float = 5.0) -> None:
        """
        Continuously watch for and process new video files.
        
        This mode keeps running and processes new videos as they appear.
        
        Args:
            poll_interval: Seconds between directory polls
        """
        logger.info("Starting CV Service in CONTINUOUS mode")
        self._running = True
        
        processed_files: set = set()
        
        while not self._shutdown_requested:
            try:
                # Get current video files
                video_files = self._get_video_files()
                
                # Find new files
                new_files = [f for f in video_files if str(f) not in processed_files]
                
                # Process new files
                for video_path in new_files:
                    if self._shutdown_requested:
                        break
                    
                    self.process_video(video_path)
                    processed_files.add(str(video_path))
                
                # Wait before next poll
                if not self._shutdown_requested:
                    time.sleep(poll_interval)
                    
            except Exception as e:
                logger.error(f"Error in continuous mode: {e}", exc_info=True)
                time.sleep(poll_interval)
        
        self._running = False
        logger.info("Continuous mode stopped")
    
    def shutdown(self) -> None:
        """Gracefully shutdown the pipeline and release resources."""
        logger.info("Shutting down CV Service Pipeline...")
        
        self._shutdown_requested = True
        
        # Close Kafka producer
        if self._kafka_producer:
            self._kafka_producer.close()
        
        # Release any other resources
        logger.info("CV Service Pipeline shutdown complete")


def main():
    """Main entry point for the CV service."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="CV Service - Equipment Detection and Activity Classification"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="/app/config/settings.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["file", "continuous"],
        default="file",
        help="Processing mode: 'file' for batch processing, 'continuous' for watching"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Directory poll interval in seconds (continuous mode only)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    logger.info("=" * 60)
    logger.info("CV Service Starting")
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Config: {args.config}")
    logger.info("=" * 60)
    
    pipeline = None
    
    try:
        # Initialize pipeline
        pipeline = CVServicePipeline(config_path=args.config)
        
        # Run in selected mode
        if args.mode == "file":
            pipeline.run_file_mode()
        else:
            pipeline.run_continuous_mode(poll_interval=args.poll_interval)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if pipeline:
            pipeline.shutdown()
    
    logger.info("CV Service stopped")


if __name__ == "__main__":
    main()
