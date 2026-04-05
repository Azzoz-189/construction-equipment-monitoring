# Computer Vision Pipeline

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [settings.yaml](file://config/settings.yaml)
- [main.py](file://services/cv_service/src/main.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [test_activity_classifier.py](file://tests/test_activity_classifier.py)
- [test_motion_analyzer.py](file://tests/test_motion_analyzer.py)
- [test_time_tracker.py](file://tests/test_time_tracker.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document explains the computer vision processing pipeline that powers equipment monitoring. The pipeline performs multi-stage processing on video streams to detect, track, and classify construction equipment activities in real time. It integrates YOLOv8 object detection, ByteTrack multi-object tracking, region-based optical flow analysis, rule-based activity classification, and utilization time tracking. The pipeline publishes structured events to Apache Kafka for downstream analytics and dashboard consumption.

The pipeline is designed for CPU-only environments with aggressive optimizations (frame skipping, resizing, and lightweight models) to enable real-time processing on modest hardware. It uses a zero-shot approach for detection (COCO classes mapped to construction vehicles) and a region-based optical flow technique to distinguish articulated motion (e.g., excavator arm) from whole-body motion.

## Project Structure
The pipeline is implemented as a modular Python service with clear separation of concerns. The central orchestrator coordinates all stages, while specialized modules handle detection, tracking, motion analysis, classification, and time accounting. Configuration is centralized in a YAML file, and events are streamed to Kafka for persistence and visualization.

```mermaid
graph TB
subgraph "CV Service"
M["main.py<br/>Pipeline Orchestrator"]
D["detector.py<br/>YOLOv8 Detector"]
T["tracker.py<br/>ByteTrack Tracker"]
MA["motion_analyzer.py<br/>Region-based OF"]
AC["activity_classifier.py<br/>Rule-based Classifier"]
TT["time_tracker.py<br/>Utilization Timer"]
KP["kafka_producer.py<br/>Event Publisher"]
end
subgraph "External Systems"
K["Apache Kafka"]
P["PostgreSQL + TimescaleDB"]
DB["Dashboard (Streamlit)"]
end
M --> D --> T --> MA --> AC --> TT --> KP --> K
K --> P
P --> DB
```

**Diagram sources**
- [main.py:42-498](file://services/cv_service/src/main.py#L42-L498)
- [detector.py:18-170](file://services/cv_service/src/detector.py#L18-L170)
- [tracker.py:19-341](file://services/cv_service/src/tracker.py#L19-L341)
- [motion_analyzer.py:24-442](file://services/cv_service/src/motion_analyzer.py#L24-L442)
- [activity_classifier.py:23-306](file://services/cv_service/src/activity_classifier.py#L23-L306)
- [time_tracker.py:21-265](file://services/cv_service/src/time_tracker.py#L21-L265)
- [kafka_producer.py:17-228](file://services/cv_service/src/kafka_producer.py#L17-L228)

**Section sources**
- [README.md:1-391](file://README.md#L1-L391)
- [settings.yaml:1-59](file://config/settings.yaml#L1-L59)

## Core Components
This section outlines the five core stages of the pipeline and their roles:

- EquipmentDetector: Runs YOLOv8 to detect vehicles/equipment in each frame and filters results to target classes.
- EquipmentTracker: Assigns persistent IDs to detections using ByteTrack and maintains track continuity across frames.
- MotionAnalyzer: Computes region-based optical flow (upper arm/boom vs lower base/tracks) to classify motion sources.
- ActivityClassifier: Applies rule-based logic with N-frame smoothing to classify activities (DIGGING, SWINGING_LOADING, DUMPING, WAITING).
- TimeTracker: Accumulates utilization time per equipment and computes utilization percentages.

Each stage produces structured outputs consumed by the next stage, culminating in Kafka events enriched with time analytics.

**Section sources**
- [detector.py:18-170](file://services/cv_service/src/detector.py#L18-L170)
- [tracker.py:19-341](file://services/cv_service/src/tracker.py#L19-L341)
- [motion_analyzer.py:24-442](file://services/cv_service/src/motion_analyzer.py#L24-L442)
- [activity_classifier.py:23-306](file://services/cv_service/src/activity_classifier.py#L23-L306)
- [time_tracker.py:21-265](file://services/cv_service/src/time_tracker.py#L21-L265)

## Architecture Overview
The pipeline is orchestrated by a single entry point that iterates frames, applies detection and tracking, analyzes motion, classifies activities, tracks utilization, and publishes events. The orchestrator manages configuration, resource initialization, and graceful shutdown.

```mermaid
sequenceDiagram
participant V as "Video Source"
participant O as "CVServicePipeline"
participant DET as "EquipmentDetector"
participant TRK as "EquipmentTracker"
participant MA as "MotionAnalyzer"
participant AC as "ActivityClassifier"
participant TT as "TimeTracker"
participant KP as "KafkaProducer"
V->>O : "Next frame"
O->>DET : "detect(frame)"
DET-->>O : "detections"
O->>TRK : "update(detections, frame)"
TRK-->>O : "tracked_objects"
O->>MA : "analyze(prev_gray, gray, tracked)"
MA-->>O : "motion_results"
O->>AC : "classify(tracked, motion_results)"
AC-->>O : "activities"
O->>TT : "update(tracked, activities, timestamp, fps)"
TT-->>O : "time_stats"
O->>KP : "publish(event)"
KP-->>O : "ack"
```

**Diagram sources**
- [main.py:323-421](file://services/cv_service/src/main.py#L323-L421)
- [detector.py:85-170](file://services/cv_service/src/detector.py#L85-L170)
- [tracker.py:159-265](file://services/cv_service/src/tracker.py#L159-L265)
- [motion_analyzer.py:88-167](file://services/cv_service/src/motion_analyzer.py#L88-L167)
- [activity_classifier.py:71-126](file://services/cv_service/src/activity_classifier.py#L71-L126)
- [time_tracker.py:53-121](file://services/cv_service/src/time_tracker.py#L53-L121)
- [kafka_producer.py:91-169](file://services/cv_service/src/kafka_producer.py#L91-L169)

## Detailed Component Analysis

### EquipmentDetector (YOLOv8)
- Purpose: Detect vehicles/equipment using YOLOv8 and filter to target classes.
- Inputs: Single BGR frame.
- Outputs: List of detections with bounding boxes, confidence, class ID, and class name.
- Key configuration:
  - model: Path to YOLOv8 model weights.
  - confidence_threshold: Minimum detection confidence.
  - device: CPU/CUDA device selection.
  - input_size: Inference resolution.
  - target_classes: COCO class IDs mapped to equipment (e.g., [2, 5, 7]).
  - class_names: Mapping from class IDs to friendly names.

Implementation highlights:
- Validates configuration keys and loads the model.
- Runs inference and parses results into a standardized format.
- Filters detections by confidence and target classes.

Practical example:
- A frame containing a truck triggers detection with a high-confidence bounding box and class name "truck".

**Section sources**
- [detector.py:18-170](file://services/cv_service/src/detector.py#L18-L170)
- [settings.yaml:8-20](file://config/settings.yaml#L8-L20)

### EquipmentTracker (ByteTrack)
- Purpose: Assign persistent equipment IDs to detections and maintain track continuity.
- Inputs: Detections from EquipmentDetector and the current frame.
- Outputs: Tracked objects with equipment_id, equipment_class, bbox, confidence, and internal track_id.
- Key configuration:
  - track_thresh: Detection confidence threshold for track activation.
  - track_buffer: Frames to keep lost tracks alive.
  - match_thresh: IOU threshold for matching detections to tracks.
  - equipment_id_prefix: Prefix mapping per class (e.g., truck -> "DT").

Implementation highlights:
- Converts detections to supervision format and updates the tracker.
- Generates unique equipment IDs with class-based prefixes.
- Uses IoU-based matching to associate tracked detections with original detections.

Practical example:
- A newly detected truck gets equipment_id "DT-001" and persists across frames.

**Section sources**
- [tracker.py:19-341](file://services/cv_service/src/tracker.py#L19-L341)
- [settings.yaml:21-30](file://config/settings.yaml#L21-L30)

### MotionAnalyzer (Region-based Optical Flow)
- Purpose: Detect motion sources by computing optical flow in upper and lower regions of tracked equipment bounding boxes.
- Inputs: Previous and current grayscale frames, tracked objects.
- Outputs: Motion classification per tracked object (full_body, arm_only, none) with flow statistics and dominant direction.
- Key configuration:
  - magnitude_threshold: Minimum optical flow magnitude to consider motion.
  - upper_region_ratio: Fraction of bbox height for upper region (default 0.5).
  - flow_method: Optical flow algorithm (currently Farneback).

Implementation highlights:
- Clips bounding boxes to frame boundaries and validates sizes.
- Splits each region and computes dense optical flow.
- Computes mean magnitudes and flow vectors per region.
- Classifies motion source based on region magnitudes and determines dominant direction.

Practical example:
- Upper region motion with high vertical flow indicates arm_only motion; lower region motion indicates full_body motion.

**Section sources**
- [motion_analyzer.py:24-442](file://services/cv_service/src/motion_analyzer.py#L24-L442)
- [settings.yaml:31-35](file://config/settings.yaml#L31-L35)

### ActivityClassifier (Rule-based Classification)
- Purpose: Classify equipment activity using motion analysis results and N-frame smoothing.
- Inputs: Tracked objects and motion results.
- Outputs: Activity classification per equipment (DIGGING, SWINGING_LOADING, DUMPING, WAITING) with state and motion source.
- Key configuration:
  - smoothing_window: N-frame smoothing window.
  - vertical_flow_threshold: Vertical motion threshold for arm-only activities.
  - horizontal_flow_threshold: Horizontal motion threshold for swinging/loading.

Implementation highlights:
- Builds a motion map keyed by equipment_id.
- Applies raw classification rules:
  - arm_only with dominant downward motion -> DIGGING
  - arm_only with dominant upward motion -> DUMPING
  - horizontal motion -> SWINGING_LOADING
  - no motion -> WAITING
- Applies N-frame smoothing via mode-based voting to prevent flickering.
- Maps activity to state: ACTIVE for non-WAITING, INACTIVE otherwise.

Practical example:
- An excavator arm moving downward is classified as DIGGING; smoothing prevents rapid flips.

**Section sources**
- [activity_classifier.py:23-306](file://services/cv_service/src/activity_classifier.py#L23-L306)
- [settings.yaml:36-40](file://config/settings.yaml#L36-L40)

### TimeTracker (Utilization Time Tracking)
- Purpose: Track total tracked seconds, active seconds, idle seconds, and utilization percentage per equipment.
- Inputs: Tracked objects, activities, frame timestamp, and FPS.
- Outputs: Aggregated time analytics per equipment and helpers for totals.
- Key behavior:
  - Initializes per-equipment counters on first appearance.
  - Increments total_tracked_seconds every processed frame.
  - Increments total_active_seconds if current_state is ACTIVE, else total_idle_seconds.
  - Calculates utilization_percent as total_active_seconds / total_tracked_seconds.
  - Persists counters across temporary disappearances.

Practical example:
- Over 10 seconds of processing at 30 FPS, a piece of equipment accumulating 7 seconds active yields 70% utilization.

**Section sources**
- [time_tracker.py:21-265](file://services/cv_service/src/time_tracker.py#L21-L265)

### Kafka Producer (Event Publishing)
- Purpose: Publish structured events to Kafka topic "equipment-events".
- Inputs: Event dictionary built from pipeline outputs.
- Key schema:
  - frame_id, equipment_id, equipment_class, timestamp
  - utilization: current_state, current_activity, motion_source
  - time_analytics: total_tracked_seconds, total_active_seconds, total_idle_seconds, utilization_percent
- Behavior:
  - Serializes events to JSON.
  - Partitions by equipment_id for ordering.
  - Asynchronous produce with delivery callbacks and retry logic.
  - Flushes remaining messages on completion.

Practical example:
- A frame with a truck classified as ACTIVE in DIGGING state generates a Kafka message with time analytics.

**Section sources**
- [kafka_producer.py:17-228](file://services/cv_service/src/kafka_producer.py#L17-L228)
- [settings.yaml:41-46](file://config/settings.yaml#L41-L46)

## Dependency Analysis
The pipeline exhibits clear stage-to-stage dependencies and external integrations:

- Stage dependencies:
  - Detector -> Tracker (detections to tracked objects)
  - Tracker -> MotionAnalyzer (tracked objects to motion results)
  - MotionAnalyzer -> ActivityClassifier (motion results to activities)
  - ActivityClassifier -> TimeTracker (activities to time stats)
  - TimeTracker -> KafkaProducer (events to Kafka)
- External dependencies:
  - YOLOv8 model for detection.
  - ByteTrack via supervision for tracking.
  - OpenCV for optical flow and image processing.
  - Kafka for event streaming.
  - PostgreSQL/TimescaleDB for persistence.

```mermaid
graph LR
DET["Detector"] --> TRK["Tracker"]
TRK --> MA["MotionAnalyzer"]
MA --> AC["ActivityClassifier"]
AC --> TT["TimeTracker"]
TT --> KP["KafkaProducer"]
KP --> K["Kafka"]
K --> P["PostgreSQL/TimescaleDB"]
```

**Diagram sources**
- [main.py:345-372](file://services/cv_service/src/main.py#L345-L372)
- [kafka_producer.py:91-169](file://services/cv_service/src/kafka_producer.py#L91-L169)

**Section sources**
- [main.py:104-142](file://services/cv_service/src/main.py#L104-L142)
- [kafka_producer.py:17-228](file://services/cv_service/src/kafka_producer.py#L17-L228)

## Performance Considerations
- CPU-first design:
  - YOLOv8n (nano) reduces parameter count and improves speed.
  - Frame skipping (default 3) reduces processing load.
  - Resize width (default 640) lowers pixel count.
  - Crop-based optical flow avoids full-frame computation.
- Practical tuning guidelines:
  - Increase smoothing_window to reduce flickering.
  - Adjust magnitude_threshold and flow thresholds for sensitivity.
  - Increase frame_skip or reduce resize_width for CPU savings.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:

- Detection failures:
  - Verify model path and device availability.
  - Adjust confidence_threshold and target_classes.
- Tracking gaps:
  - Tune track_thresh, track_buffer, and match_thresh.
  - Ensure sufficient overlap between frames for matching.
- Motion classification anomalies:
  - Check magnitude_threshold and upper_region_ratio.
  - Validate frame quality and lighting conditions.
- Activity flickering:
  - Increase smoothing_window.
  - Review horizontal and vertical thresholds.
- Time tracking inconsistencies:
  - Confirm FPS passed to update() matches video FPS.
  - Ensure activities include current_state consistently.
- Kafka publishing errors:
  - Verify bootstrap_servers and topic configuration.
  - Check producer buffer limits and network connectivity.

**Section sources**
- [detector.py:68-84](file://services/cv_service/src/detector.py#L68-L84)
- [tracker.py:61-84](file://services/cv_service/src/tracker.py#L61-L84)
- [motion_analyzer.py:72-87](file://services/cv_service/src/motion_analyzer.py#L72-L87)
- [activity_classifier.py:56-69](file://services/cv_service/src/activity_classifier.py#L56-L69)
- [time_tracker.py:82-87](file://services/cv_service/src/time_tracker.py#L82-L87)
- [kafka_producer.py:59-69](file://services/cv_service/src/kafka_producer.py#L59-L69)

## Conclusion
The pipeline combines efficient computer vision primitives with robust state management to deliver real-time equipment monitoring. By leveraging region-based optical flow and rule-based classification, it accurately distinguishes articulated motion from whole-body movement, enabling precise activity classification and utilization tracking. The modular design, centralized configuration, and event-driven architecture support scalability and maintainability.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Practical Example: End-to-End Workflow
- Input: A video file placed in the configured input directory.
- Processing:
  - Frame iteration with resizing and skipping.
  - YOLOv8 detection of target classes.
  - ByteTrack assignment of persistent equipment IDs.
  - Region-based optical flow analysis to classify motion sources.
  - Rule-based activity classification with smoothing.
  - Time tracking and utilization computation.
  - Kafka event publication.
- Output: Events stored in PostgreSQL/TimescaleDB and visualized in the dashboard.

```mermaid
flowchart TD
Start(["Start"]) --> Read["Read Video Frames"]
Read --> Detect["Detect Equipment"]
Detect --> Track["Track Equipment"]
Track --> Gray["Convert to Grayscale"]
Gray --> Motion["Compute Region-based Optical Flow"]
Motion --> Classify["Classify Activity"]
Classify --> Time["Update Time Statistics"]
Time --> Build["Build Kafka Event"]
Build --> Publish["Publish to Kafka"]
Publish --> Persist["Persist to Database"]
Persist --> End(["End"])
```

[No sources needed since this diagram shows conceptual workflow, not actual code structure]

### Configuration Reference
Key parameters and their impact:
- video.frame_skip: Controls processing rate.
- video.resize_width: Reduces inference cost.
- detection.model/confidence_threshold/device/input_size/target_classes/class_names: Detection behavior.
- tracking.track_thresh/track_buffer/match_thresh/equipment_id_prefix: Tracking behavior.
- motion.magnitude_threshold/upper_region_ratio/flow_method: Motion analysis behavior.
- activity.smoothing_window/vertical_flow_threshold/horizontal_flow_threshold: Classification behavior.
- kafka.bootstrap_servers/topic/client_id/consumer_group: Event streaming behavior.
- database.host/port/name/user/password/uri: Persistence configuration.
- dashboard.api_url/refresh_interval/page_title: Dashboard behavior.

**Section sources**
- [settings.yaml:3-59](file://config/settings.yaml#L3-L59)

### Data Model for Persistence
Events are persisted in PostgreSQL with TimescaleDB support for time-series optimization. The model captures equipment state, activity, motion source, and utilization metrics.

```mermaid
erDiagram
EQUIPMENT_EVENT {
integer id PK
integer frame_id
string equipment_id
string equipment_class
string timestamp
string current_state
string current_activity
string motion_source
float total_tracked_seconds
float total_active_seconds
float total_idle_seconds
float utilization_percent
timestamp created_at
}
```

**Diagram sources**
- [db_models.py:22-67](file://services/analytics_backend/src/db_models.py#L22-L67)

### Validation via Tests
Unit tests validate each component’s behavior:
- ActivityClassifier tests cover rule-based classification and smoothing.
- MotionAnalyzer tests cover optical flow computation, region splitting, and direction detection.
- TimeTracker tests cover time accumulation, utilization calculation, and edge cases.

**Section sources**
- [test_activity_classifier.py:1-543](file://tests/test_activity_classifier.py#L1-L543)
- [test_motion_analyzer.py:1-411](file://tests/test_motion_analyzer.py#L1-L411)
- [test_time_tracker.py:1-482](file://tests/test_time_tracker.py#L1-L482)