# Configuration Management

<cite>
**Referenced Files in This Document**
- [settings.yaml](file://config/settings.yaml)
- [main.py](file://services/cv_service/src/main.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [main.py](file://services/analytics_backend/src/main.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)
- [docker-compose.yml](file://docker-compose.yml)
</cite>

## Update Summary
**Changes Made**
- Updated configuration structure to reflect comprehensive YAML-based configuration system
- Added detailed documentation for all parameter categories and their impact on system behavior
- Enhanced tuning guidelines with specific recommendations for reducing flickering and improving sensitivity
- Expanded coverage of equipment class support and detection model configurations
- Added practical examples for different deployment environments
- Updated troubleshooting section with configuration-specific guidance

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

## Introduction
This document describes the centralized configuration management system that defines all tunable parameters for the technical construction equipment monitoring pipeline. The configuration is managed through a comprehensive YAML file (`config/settings.yaml`) that serves as the single source of truth for all services in the pipeline. The system supports multiple equipment classes (vehicles, construction machinery) with specific detection models and threshold values, enabling flexible deployment across different operational environments.

The configuration system establishes critical parameters for video processing, equipment detection, tracking algorithms, motion analysis thresholds, and Kafka messaging integration. Each parameter is carefully tuned to balance accuracy, performance, and resource utilization while supporting production-grade reliability and scalability.

## Project Structure
The configuration system is implemented through a centralized YAML file that is mounted into all services and consumed by their respective components. The system supports multiple deployment environments with environment-specific overrides and validation mechanisms.

```mermaid
graph TB
A["config/settings.yaml<br/>Central Configuration File"] --> B["CV Service<br/>services/cv_service/src/main.py"]
A --> C["Analytics Backend<br/>services/analytics_backend/src/main.py"]
A --> D["Video Ingestion<br/>services/video_ingestion/src/frame_producer.py"]
B --> E["Detector<br/>services/cv_service/src/detector.py"]
B --> F["Tracker<br/>services/cv_service/src/tracker.py"]
B --> G["Motion Analyzer<br/>services/cv_service/src/motion_analyzer.py"]
B --> H["Activity Classifier<br/>services/cv_service/src/activity_classifier.py"]
B --> I["Time Tracker<br/>services/cv_service/src/time_tracker.py"]
B --> J["Kafka Producer<br/>services/cv_service/src/kafka_producer.py"]
C --> K["Kafka Consumer<br/>services/analytics_backend/src/consumer.py"]
L["Docker Compose<br/>docker-compose.yml"] --> A
L --> B
L --> C
L --> D
```

**Diagram sources**
- [settings.yaml](file://config/settings.yaml)
- [main.py](file://services/cv_service/src/main.py)
- [main.py](file://services/analytics_backend/src/main.py)
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)
- [docker-compose.yml](file://docker-compose.yml)

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [main.py](file://services/cv_service/src/main.py)
- [main.py](file://services/analytics_backend/src/main.py)
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)
- [docker-compose.yml](file://docker-compose.yml)

## Core Components
The configuration system is organized into six primary categories that align with the pipeline stages and functional requirements:

### Video Processing Configuration
Controls frame extraction, resizing, and input directory management for efficient video processing.

### Detection Configuration  
Manages YOLOv8 model parameters, confidence thresholds, and equipment class specifications for accurate equipment identification.

### Tracking Configuration
Defines multi-object tracking parameters including thresholds, buffer management, and equipment ID generation strategies.

### Motion Analysis Configuration
Establishes optical flow analysis parameters for detecting articulated equipment motion patterns.

### Activity Classification Configuration
Sets up rule-based activity classification with smoothing windows and directional thresholds for stable state transitions.

### Messaging Configuration
Configures Kafka integration for event streaming and analytics backend connectivity.

Each category contains specific parameters with defined acceptable ranges, default values, and measurable impacts on system performance and accuracy.

**Section sources**
- [settings.yaml](file://config/settings.yaml)

## Architecture Overview
The configuration system operates through a hierarchical loading mechanism where each service loads the central configuration file and passes relevant sections to their components. The CV service orchestrates the complete pipeline, while the analytics backend consumes processed events for persistence and visualization.

```mermaid
sequenceDiagram
participant User as "Operator"
participant CV as "CV Service"
participant Det as "Detector"
participant Trk as "Tracker"
participant MA as "Motion Analyzer"
participant AC as "Activity Classifier"
participant TT as "Time Tracker"
participant KP as "Kafka Producer"
participant KC as "Kafka Consumer"
participant DB as "PostgreSQL"
User->>CV : Start service with config
CV->>Det : Load detection config
CV->>Trk : Load tracking config
CV->>MA : Load motion config
CV->>AC : Load activity config
CV->>TT : Initialize time tracker
CV->>KP : Initialize producer with Kafka config
loop For each video frame
CV->>Det : detect(frame)
Det-->>CV : detections
CV->>Trk : update(detections, frame)
Trk-->>CV : tracked
CV->>MA : analyze(prev_gray, gray, tracked)
MA-->>CV : motion_results
CV->>AC : classify(tracked, motion_results)
AC-->>CV : activities
CV->>TT : update(tracked, activities, timestamp, fps)
TT-->>CV : time_stats
CV->>KP : publish(event)
end
KP-->>KC : Send events
KC->>DB : Persist events
```

**Diagram sources**
- [main.py](file://services/cv_service/src/main.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)

## Detailed Component Analysis

### Video Processing Configuration
Controls the fundamental video processing parameters that directly impact computational efficiency and accuracy.

**Parameters:**
- `frame_skip`: Integer ≥ 1, controls frame rate reduction for CPU efficiency. Default: 3. Higher values reduce inference cost but lower temporal resolution.
- `resize_width`: Integer ≥ 1, target width for resizing frames before inference. Default: 640. Reduces memory and compute costs.
- `input_dir`: String path, directory containing video files for processing. Default: "/app/videos".

**Impact on system behavior:**
- Lower frame_skip improves temporal fidelity but increases CPU usage proportionally.
- Smaller resize_width reduces memory bandwidth and speeds up inference but may decrease detection accuracy.
- Incorrect input_dir leads to no video processing and service startup warnings.

**Tuning guidelines:**
- Start with frame_skip 3–5 for moderate CPU savings in production environments.
- Adjust resize_width based on camera resolution and computational constraints; typical values 320–1280.
- Ensure input_dir exists and contains supported video formats (.mp4, .avi, .mov, .mkv, .webm).

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [main.py](file://services/cv_service/src/main.py)
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)

### Detection Configuration
Manages YOLOv8 model parameters and equipment class specifications for accurate detection across multiple equipment types.

**Parameters:**
- `model`: String path or filename, path to YOLOv8 nano weights. Default: "yolov8n.pt".
- `confidence_threshold`: Float in (0, 1], lower values increase recall but may raise false positives. Default: 0.4.
- `device`: String "cpu" or "cuda", determines inference device. Default: "cpu".
- `input_size`: Integer ≥ 1, model input size (e.g., 640). Default: 640.
- `target_classes`: List of COCO class IDs to detect. Default: [2, 5, 7] representing cars, buses, and trucks.
- `class_names`: Dict mapping COCO class IDs to friendly names. Default: {2: "car", 5: "bus", 7: "truck"}.

**Impact on system behavior:**
- Lower confidence_threshold increases detections but may degrade accuracy and increase post-processing load.
- CUDA acceleration significantly improves throughput on compatible hardware (recommended for production).
- Incorrect target_classes or class_names mislabels detections and breaks downstream tracking.
- Model path validation ensures proper resource allocation and prevents runtime errors.

**Tuning guidelines:**
- Start with confidence_threshold 0.3–0.5 depending on lighting conditions and camera angles.
- Use CUDA if available for production deployments; otherwise CPU inference is supported.
- Verify target_classes match intended equipment types; extend for specialized machinery if needed.
- Monitor GPU utilization when using CUDA to prevent overheating and thermal throttling.

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [detector.py](file://services/cv_service/src/detector.py)

### Tracking Configuration
Defines multi-object tracking parameters that ensure stable equipment identification across video sequences.

**Parameters:**
- `track_thresh`: Float in (0, 1], detection confidence threshold to activate tracks. Default: 0.25.
- `track_buffer`: Integer ≥ 1, number of frames to retain lost tracks. Default: 30.
- `match_thresh`: Float in (0, 1], IOU threshold for matching detections to tracks. Default: 0.8.
- `equipment_id_prefix`: Dict mapping class names to ID prefixes. Default: {truck: "DT", car: "VH", bus: "BU", default: "EQ"}.

**Impact on system behavior:**
- Lower track_thresh creates more tracks but increases fragmentation and tracking overhead.
- Larger track_buffer allows smoother re-identification after brief occlusions but consumes more memory.
- Lower match_thresh increases drift and tracking errors; higher values improves stability.
- Equipment ID prefixes enable clear identification and reporting across different equipment types.

**Tuning guidelines:**
- Start with track_thresh 0.2–0.35 and match_thresh 0.7–0.85 for balanced performance.
- Increase track_buffer for scenes with frequent occlusions (e.g., construction sites with heavy machinery).
- Use descriptive prefixes that match operational naming conventions for equipment fleets.

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [tracker.py](file://services/cv_service/src/tracker.py)

### Motion Analysis Configuration
Establishes optical flow analysis parameters for detecting articulated equipment motion patterns characteristic of construction machinery.

**Parameters:**
- `magnitude_threshold`: Float ≥ 0, minimum optical flow magnitude to consider as "moving". Default: 2.0.
- `upper_region_ratio`: Float in (0, 1), fraction of bounding box height for upper region (arm/boom). Default: 0.5.
- `flow_method`: String "farneback", optical flow algorithm used. Default: "farneback".

**Impact on system behavior:**
- Lower magnitude_threshold increases sensitivity to subtle motion but may cause flicker and false positives.
- upper_region_ratio determines which part of the equipment is considered for articulated motion detection.
- Farneback algorithm is optimized for construction equipment motion with multi-resolution pyramid processing.

**Tuning guidelines:**
- Start with magnitude_threshold 1.5–2.5; adjust based on scene noise and equipment characteristics.
- Use 0.4–0.6 for upper_region_ratio depending on equipment height and articulation complexity.
- Test different magnitude thresholds in controlled environments to establish baseline sensitivity.

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)

### Activity Classification Configuration
Sets up rule-based activity classification with smoothing windows to prevent rapid flickering between states.

**Parameters:**
- `smoothing_window`: Integer ≥ 1, number of frames for mode-based smoothing to reduce flicker. Default: 5.
- `vertical_flow_threshold`: Float ≥ 0, minimum vertical flow magnitude for direction decisions. Default: 1.5.
- `horizontal_flow_threshold`: Float ≥ 0, minimum horizontal flow magnitude for direction decisions. Default: 1.5.

**Impact on system behavior:**
- Larger smoothing_window stabilizes activity transitions but adds latency and memory usage.
- Lower thresholds increase sensitivity to small motions but may cause misclassification.
- Improper thresholds cause misclassification between activities like digging, swinging, and dumping.

**Tuning guidelines:**
- Start with smoothing_window 3–7 for balanced responsiveness and stability.
- Calibrate vertical and horizontal thresholds to match equipment motion patterns and site conditions.
- Monitor activity classification accuracy and adjust thresholds based on observed equipment behavior.

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)

### Kafka Configuration
Configures Apache Kafka integration for event streaming and analytics processing.

**Parameters:**
- `bootstrap_servers`: String host:port list, Kafka broker endpoints. Default: "kafka:9092".
- `topic`: String, topic name for equipment events. Default: "equipment-events".
- `client_id`: String, producer client identifier. Default: "cv-service-producer".
- `consumer_group`: String, consumer group for analytics backend. Default: "analytics-consumer".

**Impact on system behavior:**
- Incorrect bootstrap_servers prevents event publishing/consuming and service startup failures.
- Topic mismatch causes events to go unseen by consumers and data loss.
- Client ID conflicts can cause producer rebalancing and message duplication.

**Tuning guidelines:**
- Ensure bootstrap_servers reflect the deployed Kafka cluster configuration.
- Use distinct consumer groups for multiple consumers to enable parallel processing.
- Monitor Kafka producer lag and consumer offsets for performance optimization.

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)

### Database Configuration
Manages PostgreSQL/TimescaleDB connection parameters for persistent analytics storage.

**Parameters:**
- `host`: String hostname, database server location. Default: "postgres".
- `port`: Integer port number, database connection port. Default: 5432.
- `name`: String database name. Default: "equipment_analytics".
- `user`: String username for database authentication. Default: "postgres".
- `password`: String password for database authentication. Default: "postgres".
- `uri`: String connection URI combining all connection parameters. Default: "postgresql://postgres:postgres@postgres:5432/equipment_analytics".

**Impact on system behavior:**
- Incorrect credentials or URI prevent analytics backend from writing events and cause runtime exceptions.
- Database unavailability affects the entire analytics pipeline and event persistence.

**Tuning guidelines:**
- Use strong credentials and secure network access for production deployments.
- Ensure TimescaleDB availability and implement health checks for automatic recovery.
- Monitor database connection pool usage and optimize for concurrent analytics workloads.

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [main.py](file://services/analytics_backend/src/main.py)

### Dashboard Configuration
Configures the Streamlit dashboard for real-time equipment monitoring and visualization.

**Parameters:**
- `api_url`: String base URL for analytics backend REST API. Default: "http://analytics-backend:8000".
- `refresh_interval`: Integer seconds, how often the dashboard polls backend for updates. Default: 1 second.
- `page_title`: String page title for the dashboard UI. Default: "Technical Construction Equipment Tracking & Monitoring System".

**Impact on system behavior:**
- Incorrect api_url prevents dashboard from loading data and displays connection errors.
- Very short refresh intervals can overwhelm the backend API and database connections.

**Tuning guidelines:**
- Adjust refresh_interval based on backend capacity and network latency.
- Use reasonable intervals (1-5 seconds) to balance responsiveness with system load.
- Implement caching strategies for frequently accessed data to improve dashboard performance.

**Section sources**
- [settings.yaml](file://config/settings.yaml)

## Dependency Analysis
The configuration system creates a dependency hierarchy where all services depend on the central configuration file, with each service consuming only the relevant subsections for their specific functionality.

```mermaid
graph LR
CFG["config/settings.yaml"] --> CV["CV Service"]
CFG --> AB["Analytics Backend"]
CFG --> VI["Video Ingestion"]
CV --> DET["Detector"]
CV --> TRK["Tracker"]
CV --> MA["Motion Analyzer"]
CV --> AC["Activity Classifier"]
CV --> TT["Time Tracker"]
CV --> KP["Kafka Producer"]
AB --> KC["Kafka Consumer"]
KC --> DB["PostgreSQL"]
VI --> FP["Frame Producer"]
```

**Diagram sources**
- [settings.yaml](file://config/settings.yaml)
- [main.py](file://services/cv_service/src/main.py)
- [main.py](file://services/analytics_backend/src/main.py)
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)

**Key observations:**
- All services depend on the central configuration file for parameter initialization.
- CV service composes multiple components that each consume specific configuration subsections.
- Analytics backend and Kafka consumer share Kafka configuration for seamless event processing.
- Database configuration is consumed by the analytics backend for persistent storage.
- Video ingestion service uses only video processing parameters for frame extraction.

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [main.py](file://services/cv_service/src/main.py)
- [main.py](file://services/analytics_backend/src/main.py)
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)

## Performance Considerations

### CPU Usage Optimization
- **Frame Skipping Strategy**: Increase `frame_skip` to process fewer frames, reducing inference cost by proportional amount
- **Resolution Scaling**: Reduce `resize_width` to lower memory bandwidth and accelerate model inference
- **Hardware Acceleration**: Enable CUDA device for GPU acceleration when available, providing 10-50x speedup over CPU
- **Batch Processing**: Leverage Kafka producer batching and database consumer batch commits for reduced I/O overhead

### Sensitivity Tuning Guidelines
- **Motion Detection**: Increase `magnitude_threshold` to reduce false positives from wind/vehicle vibration
- **Classification Accuracy**: Decrease `smoothing_window` for faster response to state changes, increase for stability
- **Detection Confidence**: Adjust `confidence_threshold` based on lighting conditions and camera positioning
- **Tracking Stability**: Fine-tune `match_thresh` to balance between tracking drift and fragmentation

### Throughput Optimization Strategies
- **Kafka Configuration**: Tune `linger.ms` and `batch.size` for optimal producer batching efficiency
- **Database Performance**: Optimize `BATCH_SIZE` and `BATCH_TIMEOUT` for consumer batch processing
- **Memory Management**: Monitor `track_buffer` sizing to prevent memory exhaustion during extended video processing
- **Network Optimization**: Configure Kafka producer timeouts and retry policies for reliable event delivery

### Stability Enhancement Techniques
- **Flicker Reduction**: Increase `smoothing_window` values to 5-10 for highly mobile equipment
- **Occlusion Handling**: Increase `track_buffer` for scenes with frequent equipment occlusions
- **Threshold Calibration**: Use site-specific testing to establish optimal motion detection thresholds
- **Resource Monitoring**: Implement CPU/GPU utilization monitoring to prevent thermal throttling

## Troubleshooting Guide

### Configuration Loading Issues
- **Configuration File Not Found**: Services search multiple standard paths including `/app/config/settings.yaml`, `config/settings.yaml`, and project root locations. Verify file existence and Docker volume mounting.
- **YAML Parsing Errors**: Validate YAML syntax and indentation. Common issues include missing colons, incorrect quoting, and mixed indentation styles.
- **Environment Variable Conflicts**: Check for conflicting environment variables that might override configuration values.

### Detection and Tracking Problems
- **Model Loading Failures**: Verify YOLOv8 model file exists at specified path and has proper permissions. Check CUDA availability if using GPU acceleration.
- **Incorrect Equipment Classes**: Validate `target_classes` match COCO class IDs and `class_names` mappings are correct.
- **Tracking Fragmentation**: Adjust `track_thresh` and `match_thresh` parameters based on scene complexity and equipment density.
- **ID Generation Issues**: Ensure `equipment_id_prefix` dictionary contains entries for all detected equipment classes.

### Motion Analysis and Classification Errors
- **Motion Detection Instability**: Increase `magnitude_threshold` to filter out noise-induced motion. Adjust `upper_region_ratio` for equipment-specific articulation patterns.
- **Activity Classification Flicker**: Increase `smoothing_window` values to 5-10 frames for stable state transitions.
- **Direction Detection Problems**: Calibrate `vertical_flow_threshold` and `horizontal_flow_threshold` based on equipment motion characteristics.

### Kafka and Database Connectivity
- **Kafka Connection Failures**: Verify `bootstrap_servers` configuration matches deployed Kafka cluster. Check topic existence and consumer group permissions.
- **Database Persistence Issues**: Validate `host`, `port`, `user`, and `password` credentials. Ensure TimescaleDB is properly initialized and schema migration completed.
- **Event Loss Prevention**: Monitor Kafka producer pending message counts and configure appropriate retry policies.

### Performance and Resource Issues
- **High CPU Usage**: Reduce `resize_width` and increase `frame_skip` values. Consider GPU acceleration if available.
- **Memory Exhaustion**: Monitor `track_buffer` usage and adjust based on equipment density and video length.
- **Network Latency**: Optimize Kafka producer configuration and consumer batch sizes for network conditions.

**Section sources**
- [main.py](file://services/cv_service/src/main.py)
- [main.py](file://services/analytics_backend/src/main.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)

## Conclusion
The centralized configuration management system provides a comprehensive, maintainable framework for tuning the technical construction equipment monitoring pipeline. The YAML-based configuration approach enables consistent parameter management across all services while supporting environment-specific customizations and validation mechanisms.

The system's six primary categories (video processing, detection, tracking, motion analysis, activity classification, and messaging) collectively address the complex requirements of equipment monitoring in construction environments. Each parameter is carefully tuned to balance accuracy, performance, and resource utilization while maintaining operational flexibility.

Production deployments benefit from the system's robust validation, environment-specific overrides, and comprehensive monitoring capabilities. The configuration system's modular design enables easy adaptation to different equipment types, deployment scales, and environmental conditions while maintaining predictable behavior and performance characteristics.

Proper configuration of frame skipping, detection thresholds, motion analysis parameters, and activity classification settings yields significant improvements in accuracy, reduced flicker, and optimized CPU usage. The system's comprehensive error handling and troubleshooting guidance ensures reliable operation across diverse deployment scenarios.