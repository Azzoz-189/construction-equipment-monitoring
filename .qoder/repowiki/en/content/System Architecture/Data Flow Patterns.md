# Data Flow Patterns

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [settings.yaml](file://config/settings.yaml)
- [docker-compose.yml](file://docker-compose.yml)
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)
- [main.py](file://services/cv_service/src/main.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [main.py](file://services/analytics_backend/src/main.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [api.py](file://services/analytics_backend/src/api.py)
- [app.py](file://services/dashboard/src/app.py)
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
This document explains the end-to-end data flow in the EagleVision system, from video ingestion through the computer vision pipeline to real-time dashboard visualization. The system uses an event-driven architecture powered by Apache Kafka for asynchronous messaging between services. It covers message formats, topic organization, transformation stages, persistence and caching strategies, and error handling in distributed flows.

## Project Structure
The system is composed of six primary services orchestrated by Docker Compose:
- Video ingestion service: extracts frames from video files
- CV service: detection, tracking, motion analysis, activity classification, time tracking, and Kafka publishing
- Analytics backend: Kafka consumer, database persistence, and FastAPI REST endpoints
- Dashboard: Streamlit UI that queries the backend REST API
- Apache Kafka: event streaming platform
- PostgreSQL with TimescaleDB: time-series data storage

```mermaid
graph TB
subgraph "Video Ingestion"
VP["FrameProducer<br/>frame_producer.py"]
end
subgraph "CV Pipeline"
DET["Detector<br/>detector.py"]
TRK["Tracker<br/>tracker.py"]
MOT["MotionAnalyzer<br/>motion_analyzer.py"]
ACT["ActivityClassifier<br/>activity_classifier.py"]
TT["TimeTracker<br/>time_tracker.py"]
KP["KafkaProducer<br/>kafka_producer.py"]
end
subgraph "Analytics Backend"
KC["KafkaConsumer<br/>consumer.py"]
DB["PostgreSQL/TimescaleDB<br/>db_models.py"]
API["FastAPI REST<br/>api.py"]
end
subgraph "Dashboard"
UI["Streamlit App<br/>app.py"]
end
subgraph "Infra"
KAF["Apache Kafka"]
ZK["Zookeeper"]
PG["PostgreSQL/TimescaleDB"]
end
VP --> DET
DET --> TRK
TRK --> MOT
MOT --> ACT
ACT --> TT
TT --> KP
KP --> KAF
KAF --> KC
KC --> DB
DB --> API
API --> UI
```

**Diagram sources**
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [api.py](file://services/analytics_backend/src/api.py)
- [app.py](file://services/dashboard/src/app.py)
- [docker-compose.yml](file://docker-compose.yml)

**Section sources**
- [README.md](file://README.md)
- [docker-compose.yml](file://docker-compose.yml)

## Core Components
- Video ingestion: Produces frames with configurable frame skipping and resizing.
- CV pipeline: Runs detection, tracking, motion analysis, activity classification, and time tracking; publishes normalized events to Kafka.
- Analytics backend: Consumes Kafka events, persists to PostgreSQL/TimescaleDB, and exposes REST endpoints.
- Dashboard: Queries the REST API and renders real-time equipment status and utilization metrics.

Key configuration is centralized in settings.yaml, including video processing parameters, detection thresholds, motion analysis settings, activity classification parameters, Kafka connectivity, database credentials, and dashboard preferences.

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [frame_producer.py](file://services/video_ingestion/src/frame_producer.py)
- [main.py](file://services/cv_service/src/main.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [api.py](file://services/analytics_backend/src/api.py)
- [app.py](file://services/dashboard/src/app.py)

## Architecture Overview
The system follows an event-driven pattern:
- CV service generates events per tracked equipment per processed frame.
- Kafka delivers events reliably to the analytics backend.
- Analytics backend persists events to PostgreSQL/TimescaleDB.
- Dashboard queries the REST API for real-time visualization.

```mermaid
sequenceDiagram
participant V as "Video Ingestion"
participant CV as "CV Service"
participant K as "Kafka"
participant A as "Analytics Backend"
participant DB as "PostgreSQL/TimescaleDB"
participant D as "Dashboard"
V->>CV : "Frames (skipped/resized)"
CV->>CV : "Detect → Track → Motion → Classify → Time"
CV->>K : "Publish Equipment Event"
K-->>A : "Consume Equipment Event"
A->>DB : "Persist Event"
D->>A : "HTTP GET /api/*"
A-->>D : "JSON Response"
```

**Diagram sources**
- [main.py](file://services/cv_service/src/main.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [api.py](file://services/analytics_backend/src/api.py)
- [app.py](file://services/dashboard/src/app.py)

## Detailed Component Analysis

### Data Journey Through the CV Pipeline
The CV service orchestrates the computer vision pipeline and emits normalized events for each tracked equipment.

```mermaid
flowchart TD
Start(["Frame Input"]) --> Detect["Detector<br/>YOLOv8n"]
Detect --> Track["Tracker<br/>ByteTrack"]
Track --> Gray["Grayscale Conversion"]
Gray --> Motion["MotionAnalyzer<br/>Farneback OF"]
Motion --> Classify["ActivityClassifier<br/>Rule-based + Smoothing"]
Classify --> Time["TimeTracker<br/>Accumulate Seconds"]
Time --> Build["Build Event<br/>utilization + time_analytics"]
Build --> Publish["KafkaProducer<br/>Partition by equipment_id"]
Publish --> End(["Event Published"])
```

**Diagram sources**
- [main.py](file://services/cv_service/src/main.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)

**Section sources**
- [main.py](file://services/cv_service/src/main.py)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)

### Kafka Topic Organization and Message Schema
- Topic: equipment-events
- Partitioning: by equipment_id to ensure ordering per equipment
- Delivery semantics: at-least-once with manual commit in the consumer
- Message schema: standardized JSON envelope with utilization and time analytics

```mermaid
erDiagram
EQUIPMENT_EVENT {
int id PK
int frame_id
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
- [db_models.py](file://services/analytics_backend/src/db_models.py)

**Section sources**
- [settings.yaml](file://config/settings.yaml)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [README.md](file://README.md)

### Analytics Backend Persistence and REST API
- Consumer: reads from equipment-events, batches writes, commits offsets after successful DB writes
- Database: PostgreSQL with TimescaleDB hypertable on equipment_events for time-series optimization
- API: provides health, equipment list, history, utilization summary, latest frame, and stats

```mermaid
sequenceDiagram
participant KC as "KafkaConsumer"
participant DB as "PostgreSQL/TimescaleDB"
participant API as "FastAPI"
participant UI as "Streamlit"
KC->>KC : "poll()"
KC->>KC : "parse JSON"
KC->>DB : "bulk_save_objects(batch)"
KC->>KC : "commit offsets"
UI->>API : "GET /api/equipment"
API->>DB : "query latest per equipment"
DB-->>API : "results"
API-->>UI : "JSON"
```

**Diagram sources**
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [api.py](file://services/analytics_backend/src/api.py)
- [app.py](file://services/dashboard/src/app.py)

**Section sources**
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [api.py](file://services/analytics_backend/src/api.py)
- [app.py](file://services/dashboard/src/app.py)

### Dashboard Real-Time Visualization
- Polls REST endpoints with configurable refresh intervals
- Uses caching decorators to limit API calls
- Renders equipment status, utilization metrics, and latest frame overlay

```mermaid
flowchart TD
Dash["Streamlit App"] --> Health["/api/health"]
Dash --> Equip["/api/equipment"]
Dash --> Util["/api/utilization/summary"]
Dash --> Latest["/api/latest-frame"]
Dash --> Stats["/api/stats"]
Dash --> Cache["Cache Layer"]
Health --> Cache
Equip --> Cache
Util --> Cache
Latest --> Cache
Stats --> Cache
```

**Diagram sources**
- [app.py](file://services/dashboard/src/app.py)
- [api.py](file://services/analytics_backend/src/api.py)

**Section sources**
- [app.py](file://services/dashboard/src/app.py)
- [api.py](file://services/analytics_backend/src/api.py)

## Dependency Analysis
- CV service depends on detector, tracker, motion analyzer, activity classifier, time tracker, and Kafka producer.
- Analytics backend depends on Kafka consumer, SQLAlchemy models, and FastAPI.
- Dashboard depends on REST API endpoints.
- Infrastructure: Kafka and Zookeeper managed by Docker Compose; PostgreSQL/TimescaleDB managed by Docker Compose.

```mermaid
graph LR
CV["CV Service"] --> DET["Detector"]
CV --> TRK["Tracker"]
CV --> MOT["MotionAnalyzer"]
CV --> ACT["ActivityClassifier"]
CV --> TT["TimeTracker"]
CV --> KP["KafkaProducer"]
KP --> KAF["Kafka"]
KAF --> KC["KafkaConsumer"]
KC --> DB["PostgreSQL/TimescaleDB"]
DB --> API["FastAPI"]
API --> UI["Streamlit"]
```

**Diagram sources**
- [main.py](file://services/cv_service/src/main.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [db_models.py](file://services/analytics_backend/src/db_models.py)
- [api.py](file://services/analytics_backend/src/api.py)
- [app.py](file://services/dashboard/src/app.py)
- [docker-compose.yml](file://docker-compose.yml)

**Section sources**
- [docker-compose.yml](file://docker-compose.yml)

## Performance Considerations
- CPU optimization: YOLOv8n, frame skipping, frame resizing, crop-based optical flow
- Producer tuning: linger.ms, batch.size, acks=all for reliability
- Consumer tuning: manual commit, batch size and timeout, max.poll.interval.ms
- Database: bulk inserts, TimescaleDB hypertable for time-series efficiency
- Dashboard: client-side caching and controlled refresh intervals

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
- Kafka connectivity: verify bootstrap servers and topic existence; check consumer group offsets
- Database connectivity: ensure PostgreSQL is healthy and TimescaleDB extension is available
- Producer errors: buffer full conditions trigger flush and retry; inspect delivery callbacks
- Consumer errors: JSON decode failures, batch commit exceptions, partition EOF handling
- Dashboard connectivity: health endpoint checks; fallback UI when backend is unavailable

**Section sources**
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)
- [consumer.py](file://services/analytics_backend/src/consumer.py)
- [api.py](file://services/analytics_backend/src/api.py)
- [app.py](file://services/dashboard/src/app.py)

## Conclusion
The EagleVision system implements a robust, event-driven pipeline that transforms raw video frames into actionable equipment utilization insights. Kafka decouples producers and consumers, enabling scalability and resilience. PostgreSQL/TimescaleDB provides efficient time-series persistence, while the FastAPI backend and Streamlit dashboard deliver real-time visibility. Centralized configuration enables tuning for performance and accuracy.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Message Formats and Transformation Stages
- Input: video frames (skipped and resized)
- Detection: bounding boxes, class IDs, confidence
- Tracking: persistent equipment IDs with class prefixes
- Motion analysis: region-based optical flow magnitudes and directions
- Activity classification: rule-based classification with N-frame smoothing
- Time tracking: accumulated seconds and utilization percentages
- Kafka event: normalized JSON envelope for downstream processing

**Section sources**
- [README.md](file://README.md)
- [settings.yaml](file://config/settings.yaml)
- [detector.py](file://services/cv_service/src/detector.py)
- [tracker.py](file://services/cv_service/src/tracker.py)
- [motion_analyzer.py](file://services/cv_service/src/motion_analyzer.py)
- [activity_classifier.py](file://services/cv_service/src/activity_classifier.py)
- [time_tracker.py](file://services/cv_service/src/time_tracker.py)
- [kafka_producer.py](file://services/cv_service/src/kafka_producer.py)