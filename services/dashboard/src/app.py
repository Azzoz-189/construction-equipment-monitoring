"""
Equipment Utilization Monitor - Streamlit Dashboard.

A real-time CCTV-style dashboard for monitoring equipment utilization,
activity classification, and status tracking.

Architecture: Uses @st.fragment for independent refresh zones so that
the MJPEG video stream is rendered ONCE and never disrupted by data
refreshes.
"""

import time
import logging
from datetime import timedelta
from typing import Dict, List, Optional, Any

import requests
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import yaml
from PIL import Image
import io

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

def load_config() -> Dict[str, Any]:
    """Load configuration from settings.yaml."""
    config_paths = [
        "/app/config/settings.yaml",
        "config/settings.yaml",
        "../../../config/settings.yaml",
    ]

    for path in config_paths:
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            continue

    # Return default config if file not found
    return {
        "dashboard": {
            "api_url": "http://analytics-backend:8000",
            "refresh_interval": 1,
            "page_title": "Equipment Utilization Monitor"
        }
    }


# Load config once
CONFIG = load_config()
DASHBOARD_CONFIG = CONFIG.get("dashboard", {})
API_URL = DASHBOARD_CONFIG.get("api_url", "http://analytics-backend:8000")
REFRESH_INTERVAL = DASHBOARD_CONFIG.get("refresh_interval", 1)
PAGE_TITLE = DASHBOARD_CONFIG.get("page_title", "Equipment Utilization Monitor")


# ============================================================================
# Custom CSS - CCTV Monitoring Theme
# ============================================================================

CCTV_CSS = """
<style>
/* Dark monitoring theme */
.stApp {
    background-color: #0e1117;
}

/* Main header styling */
.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    padding: 15px 25px;
    border-radius: 10px;
    margin-bottom: 20px;
    border: 1px solid #2a2a4a;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
}

.main-header h1 {
    color: #e2e8f0;
    font-size: 1.8em;
    margin: 0;
}

.main-header .subtitle {
    color: #94a3b8;
    font-size: 0.9em;
    margin: 0;
}

.header-left {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.header-right {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}

.header-status {
    color: #94a3b8;
    font-size: 0.82em;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* Panel/card styling */
.monitor-panel {
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 15px;
}

.panel-header {
    color: #e2e8f0;
    font-size: 1.1em;
    font-weight: 600;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid #2a2a4a;
}

/* Status indicators */
.status-active {
    color: #22c55e;
    font-weight: bold;
}

.status-inactive {
    color: #ef4444;
    font-weight: bold;
}

/* Live indicator */
.live-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.85em;
    font-weight: 600;
}

.live-badge::before {
    content: '';
    width: 8px;
    height: 8px;
    background: #ef4444;
    border-radius: 50%;
    animation: pulse 1.5s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}

/* Equipment table styling */
.equipment-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
}

.equipment-table th {
    background: #16213e;
    color: #94a3b8;
    padding: 8px 12px;
    text-align: left;
    position: sticky;
    top: 0;
    z-index: 1;
}

.equipment-table td {
    padding: 6px 12px;
    border-bottom: 1px solid #2a2a4a;
    color: #e2e8f0;
}

.equipment-table tr:hover {
    background: rgba(59, 130, 246, 0.1);
}

/* Metric cards */
.metric-card {
    background: #16213e;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: center;
}

.metric-value {
    font-size: 1.8em;
    font-weight: 700;
    color: #3b82f6;
}

.metric-label {
    font-size: 0.8em;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Override Streamlit metric styling for dark theme */
.stMetric {
    background-color: #16213e;
    padding: 10px;
    border-radius: 8px;
    border: 1px solid #2a2a4a;
    transition: all 0.3s ease-in-out;
}

/* Smooth transitions for stats updates */
.metric-card {
    transition: all 0.3s ease-in-out;
}

.metric-value {
    transition: color 0.3s ease-in-out;
}

/* Stream quality indicator */
.stream-status-live {
    color: #00ff00;
    font-weight: 600;
    font-size: 0.8em;
    text-shadow: 0 0 4px rgba(0, 255, 0, 0.4);
}

.stream-status-reconnecting {
    color: #ffaa00;
    font-weight: 600;
    font-size: 0.8em;
    animation: pulse 1s infinite;
}

div[data-testid="stMetricValue"] {
    font-size: 24px;
    color: #e2e8f0;
}

div[data-testid="stMetricLabel"] {
    color: #94a3b8;
}

.stProgress > div > div > div > div {
    background-color: #3b82f6;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #111827;
    border-right: 1px solid #2a2a4a;
}

section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] .stCheckbox label {
    color: #94a3b8;
}

/* Channel badge */
.channel-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(59, 130, 246, 0.15);
    color: #3b82f6;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.82em;
    font-weight: 600;
}

.connected-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.82em;
    font-weight: 600;
}
</style>
"""


# ============================================================================
# Helper Functions
# ============================================================================

def format_seconds(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    if seconds is None or seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_dwell_mmss(seconds: float) -> str:
    """Convert seconds to MM:SS format for dwell time display."""
    if seconds is None or seconds < 0:
        seconds = 0
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def get_dwell_color(seconds: float) -> str:
    """Get color for dwell time: green (<5min), yellow (5-15min), red (>15min)."""
    if seconds is None:
        seconds = 0
    if seconds < 300:  # < 5 min
        return "#22c55e"
    elif seconds < 900:  # 5-15 min
        return "#f59e0b"
    else:  # > 15 min
        return "#ef4444"


def get_state_color(state: str) -> str:
    """Get color for equipment state."""
    return "#22c55e" if state == "ACTIVE" else "#ef4444"


def get_state_emoji(state: str) -> str:
    """Get emoji indicator for equipment state."""
    return "🟢" if state == "ACTIVE" else "🔴"


def get_activity_badge(activity: str) -> str:
    """Get styled badge for activity type."""
    colors = {
        "DIGGING": "#3b82f6",
        "SWINGING_LOADING": "#06b6d4",
        "DUMPING": "#f59e0b",
        "WAITING": "#6b7280",
        "UNKNOWN": "#6b7280"
    }
    color = colors.get(activity, "#6b7280")
    return f'<span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{activity}</span>'


def get_channel_param() -> str:
    """Get the channel query parameter string for API calls."""
    selected = st.session_state.get("selected_channel", None)
    if selected and str(selected).lower() != "all":
        return f"?channel={selected}"
    return ""


# ============================================================================
# API Communication (all per-channel aware)
# ============================================================================

def check_api_health() -> bool:
    """Check if the API backend is available."""
    try:
        response = requests.get(f"{API_URL}/api/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def fetch_latest_frame_image():
    """Fetch the latest annotated frame image from API (no caching for live frames)."""
    try:
        channel = get_channel_param()
        response = requests.get(
            f"{API_URL}/api/latest-frame-image{channel}",
            timeout=5,
            headers={"Cache-Control": "no-cache"}
        )
        if response.status_code == 200 and len(response.content) > 0:
            return response.content  # Raw JPEG bytes
        return None
    except Exception as e:
        logger.error(f"Error fetching latest frame image: {e}")
        return None


def fetch_equipment_list() -> Optional[List[Dict]]:
    """Fetch current equipment list from API (per-channel)."""
    try:
        channel = get_channel_param()
        response = requests.get(f"{API_URL}/api/equipment{channel}", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching equipment: {e}")
        return None


def fetch_utilization_summary() -> Optional[Dict]:
    """Fetch utilization summary from API (per-channel)."""
    try:
        channel = get_channel_param()
        response = requests.get(f"{API_URL}/api/utilization/summary{channel}", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching utilization summary: {e}")
        return None


def fetch_latest_frame() -> Optional[Dict]:
    """Fetch latest frame data from API (per-channel)."""
    try:
        channel = get_channel_param()
        response = requests.get(f"{API_URL}/api/latest-frame{channel}", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching latest frame: {e}")
        return None


def fetch_stats() -> Optional[Dict]:
    """Fetch general statistics from API (per-channel)."""
    try:
        channel = get_channel_param()
        response = requests.get(f"{API_URL}/api/stats{channel}", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return None


def fetch_video_channels() -> Optional[Dict]:
    """Fetch available video channels from API."""
    try:
        response = requests.get(f"{API_URL}/api/videos", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching video channels: {e}")
        return None


def select_video_channel(filename: str) -> bool:
    """Select a video channel to monitor."""
    try:
        response = requests.post(
            f"{API_URL}/api/videos/select",
            json={"filename": filename},
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error selecting video channel: {e}")
        return False


# ============================================================================
# Sidebar (renders once; triggers rerun only on explicit channel change)
# ============================================================================

def render_sidebar():
    """Render the sidebar with controls. Returns settings dict."""
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center; padding: 10px 0;">'
            '<span style="font-size:1.4em; font-weight:700; color:#e2e8f0;">⚙️ Control Panel</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Connection status
        api_healthy = check_api_health()
        if api_healthy:
            st.markdown(
                '<div class="connected-badge" style="margin-bottom:8px;">● API Connected</div>',
                unsafe_allow_html=True,
            )
        else:
            st.error("🔴 API Disconnected")
            st.caption(f"Trying: {API_URL}")

        st.divider()

        # ------------------------------------------------------------------
        # Video Channel Selector
        # ------------------------------------------------------------------
        st.markdown(
            '<span style="color:#e2e8f0; font-weight:600;">📡 Channel Selector</span>',
            unsafe_allow_html=True,
        )

        channels_data = fetch_video_channels()
        channel_options = ["All Channels (Sequential)"]
        channel_filenames = ["all"]  # maps index -> filename to POST
        current_video = None
        total_channels = 0

        if channels_data:
            videos = channels_data.get("videos", [])
            current_video = channels_data.get("current_video", None)
            total_channels = channels_data.get("total_channels", len(videos))
            for v in videos:
                label = v.get("channel_id") or v.get("filename", "unknown")
                size = v.get("size_mb", 0)
                display = f"CH {label}  ({size:.0f} MB)" if size else f"CH {label}"
                channel_options.append(display)
                channel_filenames.append(v.get("filename", ""))

            st.caption(f"📺 {total_channels} channels available")
        else:
            st.caption("📺 Channel info unavailable")

        # Determine default index based on current_video
        default_idx = 0
        if current_video and current_video in channel_filenames:
            default_idx = channel_filenames.index(current_video)

        # Initialize selected_channel in session state
        if "selected_channel" not in st.session_state:
            st.session_state.selected_channel = channel_filenames[default_idx] if channel_filenames else "all"

        def _on_channel_change():
            """Callback: user changed the channel selector."""
            idx = st.session_state.channel_selector
            chosen = channel_filenames[idx]
            st.session_state.selected_channel = chosen
            # POST channel selection to backend
            if chosen != st.session_state.get("prev_channel", None):
                ok = select_video_channel(chosen)
                st.session_state.prev_channel = chosen
                if not ok:
                    logger.warning("Failed to switch channel via API")

        selected_ch_idx = st.selectbox(
            "Select Channel",
            range(len(channel_options)),
            format_func=lambda i: channel_options[i],
            index=default_idx,
            key="channel_selector",
            on_change=_on_channel_change,
        )

        # Keep prev_channel in sync on first load
        if "prev_channel" not in st.session_state:
            st.session_state.prev_channel = channel_filenames[selected_ch_idx]
            st.session_state.selected_channel = channel_filenames[selected_ch_idx]

        # Show active channel indicator
        if current_video and current_video != "all":
            st.markdown(
                f'<div class="channel-badge" style="margin-top:4px;">▶ Active: {current_video[:30]}</div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # Manual refresh button
        st.markdown(
            '<span style="color:#e2e8f0; font-weight:600;">🔄 Refresh</span>',
            unsafe_allow_html=True,
        )
        if st.button("🔄 Manual Refresh", use_container_width=True):
            st.rerun()

        st.divider()

        # Equipment filter
        st.markdown(
            '<span style="color:#e2e8f0; font-weight:600;">🔍 Equipment Filter</span>',
            unsafe_allow_html=True,
        )
        equipment_list = fetch_equipment_list()
        equipment_ids = ["All"]
        if equipment_list:
            equipment_ids.extend([eq["equipment_id"] for eq in equipment_list])

        selected_equipment = st.selectbox(
            "Focus Equipment",
            options=equipment_ids,
            index=0,
            help="Select specific equipment to highlight",
        )

        st.divider()

        # Database stats
        stats = fetch_stats()
        if stats:
            st.markdown(
                '<span style="color:#e2e8f0; font-weight:600;">🗄️ Database Stats</span>',
                unsafe_allow_html=True,
            )
            st.metric("Total Events", f"{stats.get('total_events', 0):,}")
            st.metric("Unique Equipment", stats.get("unique_equipment", 0))
            frame_range = stats.get("frame_range", {})
            st.caption(
                f"Frame Range: {frame_range.get('min', 0)} - {frame_range.get('max', 0)}"
            )

        return {
            "selected_equipment": selected_equipment,
            "api_healthy": api_healthy,
        }


# ============================================================================
# Static UI Components (rendered once)
# ============================================================================

def render_header(api_healthy: bool, equipment_count: int, channel_count: int):
    """Render the professional CCTV-style header."""
    status_color = "#22c55e" if api_healthy else "#ef4444"
    status_text = "System Online" if api_healthy else "System Offline"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    st.markdown(
        f"""
        <div class="main-header">
            <div class="header-left">
                <h1>🎯 EagleVision Monitoring System</h1>
                <p class="subtitle">Real-time equipment detection &amp; utilization tracking</p>
            </div>
            <div class="header-right">
                <span class="live-badge">LIVE</span>
                <span class="connected-badge" style="background:rgba({('34,197,94' if api_healthy else '239,68,68')},0.15); color:{status_color};">● {status_text}</span>
                <span class="channel-badge">📺 {channel_count} CH</span>
                <span class="header-status">🏗️ {equipment_count} tracked</span>
                <span class="header-status">🕒 {timestamp}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_video_stream():
    """Render the MJPEG video stream as static HTML — called ONCE, never refreshed."""
    st.markdown(
        '<div class="monitor-panel">'
        '<div class="panel-header">📹 Live Video Feed</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    stream_url = "http://localhost:8000/api/stream/mjpeg"

    mjpeg_html = f"""
    <link rel="preconnect" href="http://analytics-backend:8000">
    <div id="stream-wrapper" style="width:100%; display:flex; flex-direction:column; align-items:center; background:#000; border-radius:8px; overflow:hidden; border:1px solid #2a2a4a;">
        <img id="mjpeg-stream"
             src="{stream_url}?t={int(time.time()*1000)}"
             style="width:100%; max-width:960px; display:block;"
             alt="Live Equipment Detection Feed">
        <div id="stream-error" style="display:none; padding:20px; color:#ef4444; text-align:center;">
            ⚠️ Stream reconnecting...
        </div>
        <div style="width:100%; padding:6px 12px; background:#16213e; display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#ef4444; font-size:0.8em; font-weight:600;">● REC</span>
            <span id="stream-status" style="font-size:0.8em; font-weight:600; color:#00ff00; text-shadow: 0 0 4px rgba(0,255,0,0.4);">LIVE</span>
            <span style="color:#94a3b8; font-size:0.78em;">Live — equipment detection with bounding boxes</span>
            <span id="frame-counter-bar" style="color:#94a3b8; font-size:0.78em; transition: all 0.3s ease;">Frame #---</span>
        </div>
    </div>
    <script>
    (function() {{
        var img = document.getElementById('mjpeg-stream');
        var errDiv = document.getElementById('stream-error');
        var statusEl = document.getElementById('stream-status');
        var frameCounter = document.getElementById('frame-counter-bar');
        var retryCount = 0;
        var maxRetries = 120;
        var retryTimer = null;
        var frameCount = 0;

        function reconnect() {{
            if (retryCount >= maxRetries) return;
            retryCount++;
            var url = '{stream_url}?t=' + Date.now();
            img.src = '';
            setTimeout(function() {{ img.src = url; }}, 100);
        }}

        img.onerror = function() {{
            img.style.display = 'none';
            errDiv.style.display = 'block';
            statusEl.textContent = 'RECONNECTING...';
            statusEl.style.color = '#ffaa00';
            statusEl.style.textShadow = '0 0 4px rgba(255,170,0,0.4)';
            if (retryTimer) clearTimeout(retryTimer);
            retryTimer = setTimeout(reconnect, 2000);
        }};

        img.onload = function() {{
            img.style.display = 'block';
            errDiv.style.display = 'none';
            retryCount = 0;
            statusEl.textContent = 'LIVE';
            statusEl.style.color = '#00ff00';
            statusEl.style.textShadow = '0 0 4px rgba(0,255,0,0.4)';
            // Increment visible frame counter for stream-alive indication
            frameCount++;
            frameCounter.textContent = 'Frame #' + frameCount;
        }};

        // Proactively reconnect every 115s before server-side 120s timeout
        setInterval(function() {{
            reconnect();
        }}, 115000);
    }})();
    </script>
    """
    components.html(mjpeg_html, height=520)


# ============================================================================
# Fragment: Stats Section (auto-refreshes every 2 seconds)
# ============================================================================

@st.fragment(run_every=timedelta(seconds=2))
def render_stats_fragment():
    """Auto-refreshing stats section: metrics + frame info + equipment table."""
    selected_equipment = st.session_state.get("_selected_equipment", "All")

    # Fetch per-channel data
    latest_frame = fetch_latest_frame()
    equipment_list = fetch_equipment_list()
    utilization_data = fetch_utilization_summary()

    # --- Frame metrics above table ---
    if latest_frame:
        frame_id = latest_frame.get("frame_id", 0)
        eq_in_frame = latest_frame.get("equipment", [])
        mc1, mc2 = st.columns(2)
        with mc1:
            st.markdown(
                f'<div class="metric-card"><div class="metric-value">#{frame_id}</div>'
                f'<div class="metric-label">Current Frame</div></div>',
                unsafe_allow_html=True,
            )
        with mc2:
            st.markdown(
                f'<div class="metric-card"><div class="metric-value">{len(eq_in_frame)}</div>'
                f'<div class="metric-label">Equipment Detected</div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("⏳ Waiting for frame data...")

    # --- Summary metric cards ---
    if utilization_data:
        total = utilization_data.get("total_equipment", 0)
        active = utilization_data.get("active_count", 0)
        inactive = utilization_data.get("inactive_count", 0)
        avg_util = utilization_data.get("avg_utilization", 0)

        cols = st.columns(4)
        cards = [
            ("Total", str(total), "#3b82f6"),
            ("Active", str(active), "#22c55e"),
            ("Inactive", str(inactive), "#ef4444"),
            ("Avg Util", f"{avg_util:.1f}%", "#f59e0b"),
        ]
        for col, (label, value, color) in zip(cols, cards):
            with col:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-value" style="color:{color};">{value}</div>'
                    f'<div class="metric-label">{label}</div></div>',
                    unsafe_allow_html=True,
                )

    # --- Longest Idle & Re-ID metric cards ---
    if equipment_list:
        # Find equipment with longest current idle streak
        longest_idle_eq = max(
            equipment_list,
            key=lambda e: (e.get("current_idle_streak_seconds") or 0),
            default=None,
        )
        total_re_ids = sum(e.get("times_re_identified", 0) or 0 for e in equipment_list)

        if longest_idle_eq:
            idle_secs = longest_idle_eq.get("current_idle_streak_seconds", 0) or 0
            idle_id = longest_idle_eq.get("equipment_id", "N/A")
            dw_color = get_dwell_color(idle_secs)
            d_cols = st.columns(2)
            with d_cols[0]:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-value" style="color:{dw_color};">{format_dwell_mmss(idle_secs)}</div>'
                    f'<div class="metric-label">Longest Idle ({idle_id})</div></div>',
                    unsafe_allow_html=True,
                )
            with d_cols[1]:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-value" style="color:#6366f1;">{total_re_ids}</div>'
                    f'<div class="metric-label">Re-ID Count</div></div>',
                    unsafe_allow_html=True,
                )

    # --- Live Equipment Status Table ---
    st.markdown(
        '<div class="monitor-panel">'
        '<div class="panel-header">📊 Live Equipment Status</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if equipment_list is None:
        st.info("⏳ Connecting to API...")
        return

    if not equipment_list:
        st.warning("No equipment data available")
        return

    # Filter by selected equipment
    display_list = equipment_list
    if selected_equipment != "All":
        display_list = [eq for eq in equipment_list if eq.get("equipment_id") == selected_equipment]

    activity_colors = {
        "DIGGING": "#3b82f6",
        "SWINGING_LOADING": "#06b6d4",
        "DUMPING": "#f59e0b",
        "WAITING": "#6b7280",
        "UNKNOWN": "#6b7280",
    }

    rows_html = ""
    for eq in display_list:
        eq_id = eq.get("equipment_id", "Unknown")
        eq_class = eq.get("equipment_class", "unknown")
        state = eq.get("current_state", "UNKNOWN")
        activity = eq.get("current_activity", "UNKNOWN")
        utilization = eq.get("utilization_percent", 0)
        idle_dwell = eq.get("current_idle_streak_seconds", 0) or 0
        re_id_count = eq.get("times_re_identified", 0) or 0
        state_color = "#22c55e" if state == "ACTIVE" else "#ef4444"
        act_color = activity_colors.get(activity, "#6b7280")
        dwell_color = get_dwell_color(idle_dwell)
        dwell_display = format_dwell_mmss(idle_dwell)
        re_id_badge = f' <span style="background:#6366f1;color:#fff;padding:1px 5px;border-radius:3px;font-size:10px;">Re-ID x{re_id_count}</span>' if re_id_count > 0 else ""

        rows_html += f"""
        <tr>
            <td style="font-weight:600;">{eq_id}{re_id_badge}</td>
            <td>{eq_class.title()}</td>
            <td><span style="color:{state_color}; font-weight:700;">● {state}</span></td>
            <td><span style="background:{act_color}; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px;">{activity}</span></td>
            <td><span style="color:{dwell_color}; font-weight:600;">{dwell_display}</span></td>
            <td>
                <div style="display:flex; align-items:center; gap:6px;">
                    <div style="flex:1; height:6px; background:#1e293b; border-radius:3px; overflow:hidden;">
                        <div style="width:{min(utilization, 100):.0f}%; height:100%; background:#3b82f6; border-radius:3px;"></div>
                    </div>
                    <span style="font-size:0.8em;">{utilization:.1f}%</span>
                </div>
            </td>
        </tr>
        """

    scrollable_table_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ margin:0; padding:0; background:transparent; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .scroll-container {{
            max-height: 350px;
            overflow-y: auto;
            border: 1px solid #2a2a4a;
            border-radius: 8px;
            background: #0e1117;
        }}
        .scroll-container::-webkit-scrollbar {{ width: 6px; }}
        .scroll-container::-webkit-scrollbar-track {{ background: #1a1a2e; border-radius: 3px; }}
        .scroll-container::-webkit-scrollbar-thumb {{ background: #3b82f6; border-radius: 3px; }}
        table.equipment-table {{ width:100%; border-collapse:collapse; font-size:0.85em; }}
        table.equipment-table th {{
            background: #16213e;
            color: #94a3b8;
            padding: 8px 12px;
            text-align: left;
            position: sticky;
            top: 0;
            z-index: 1;
            font-weight: 600;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }}
        table.equipment-table td {{
            padding: 6px 12px;
            border-bottom: 1px solid #2a2a4a;
            color: #e2e8f0;
        }}
        table.equipment-table tr:hover {{
            background: rgba(59, 130, 246, 0.08);
        }}
    </style>
    </head>
    <body>
    <div class="scroll-container">
        <table class="equipment-table">
            <thead>
                <tr>
                    <th>Equipment ID</th>
                    <th>Class</th>
                    <th>State</th>
                    <th>Activity</th>
                    <th>Dwell Time</th>
                    <th>Utilization</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    </body>
    </html>
    """

    num_rows = len(display_list)
    display_height = min(60 + num_rows * 38, 380)
    components.html(scrollable_table_html, height=display_height, scrolling=False)

    # DataFrame view option
    with st.expander("📋 View as DataFrame"):
        df = pd.DataFrame(display_list)
        if not df.empty:
            display_cols = ["equipment_id", "equipment_class", "current_state", "current_activity", "utilization_percent"]
            available_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available_cols], use_container_width=True, hide_index=True)


# ============================================================================
# Fragment: Utilization Section (auto-refreshes every 5 seconds)
# ============================================================================

@st.fragment(run_every=timedelta(seconds=5))
def render_utilization_fragment():
    """Auto-refreshing utilization dashboard."""
    selected_equipment = st.session_state.get("_selected_equipment", "All")

    utilization_data = fetch_utilization_summary()

    st.markdown(
        '<div class="monitor-panel">'
        '<div class="panel-header">📈 Utilization Dashboard</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if utilization_data is None:
        st.info("⏳ Loading utilization data...")
        return

    # Summary metrics
    summary_cols = st.columns(4)
    with summary_cols[0]:
        st.metric("Total Equipment", utilization_data.get("total_equipment", 0), help="Total number of tracked equipment")
    with summary_cols[1]:
        st.metric("Active", utilization_data.get("active_count", 0), help="Currently active equipment")
    with summary_cols[2]:
        st.metric("Inactive", utilization_data.get("inactive_count", 0), help="Currently inactive equipment")
    with summary_cols[3]:
        avg_util = utilization_data.get("avg_utilization", 0)
        st.metric("Avg Utilization", f"{avg_util:.1f}%", help="Average utilization across all equipment")

    st.progress(min(avg_util / 100, 1.0), text=f"Average Utilization: {avg_util:.1f}%")

    st.divider()

    # Per-equipment utilization cards
    equipment_list = utilization_data.get("equipment", [])
    if not equipment_list:
        st.info("No equipment utilization data available")
        return

    if selected_equipment != "All":
        equipment_list = [eq for eq in equipment_list if eq.get("equipment_id") == selected_equipment]

    st.markdown("#### Per-Equipment Metrics")

    cols_per_row = 3
    num_equipment = len(equipment_list)

    for i in range(0, num_equipment, cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= num_equipment:
                break
            eq = equipment_list[idx]
            eq_id = eq.get("equipment_id", "Unknown")
            eq_class = eq.get("equipment_class", "unknown")
            total_active = eq.get("total_active_seconds", 0)
            total_idle = eq.get("total_idle_seconds", 0)
            utilization = eq.get("utilization_percent", 0)

            with col:
                st.markdown(
                    f"""
                    <div style="
                        border: 1px solid #2a2a4a;
                        border-radius: 12px;
                        padding: 15px;
                        margin-bottom: 10px;
                        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    ">
                        <h4 style="margin:0 0 5px 0; color:#e2e8f0;">{eq_id}</h4>
                        <p style="margin:0 0 10px 0; color:#94a3b8; font-size:12px;">{eq_class.title()}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.metric("Working Time", format_seconds(total_active), help="Total active/working time")
                st.metric("Idle Time", format_seconds(total_idle), help="Total idle/waiting time")
                st.progress(min(utilization / 100, 1.0), text=f"Utilization: {utilization:.1f}%")
                st.caption(f"Events: {eq.get('event_count', 0)}")


# ============================================================================
# Main Application
# ============================================================================

def main():
    """Main application entry point."""
    # Page configuration
    st.set_page_config(
        page_title="Technical Construction Equipment Tracking & Monitoring System",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inject CCTV dark theme CSS
    st.markdown(CCTV_CSS, unsafe_allow_html=True)

    # Render sidebar and get settings (runs once per page load / explicit rerun)
    settings = render_sidebar()

    # Store selected_equipment in session state for fragments to read
    st.session_state["_selected_equipment"] = settings["selected_equipment"]

    # Fetch data for header info (lightweight, runs once on page load)
    equipment_list = fetch_equipment_list()
    channels_data = fetch_video_channels()
    eq_count = len(equipment_list) if equipment_list else 0
    ch_count = channels_data.get("total_channels", 0) if channels_data else 0

    # Render header (static)
    render_header(settings["api_healthy"], eq_count, ch_count)

    # Check API connection
    if not settings["api_healthy"]:
        st.error("⚠️ Cannot connect to Analytics API. Please ensure the backend is running.")
        st.info(f"Attempting to connect to: {API_URL}")
        # Still show fragments so they can auto-retry
        render_video_stream()
        render_stats_fragment()
        render_utilization_fragment()
        return

    # --- MJPEG Video Stream: rendered ONCE, never re-rendered by fragments ---
    render_video_stream()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # --- Stats fragment: auto-refreshes every 2s ---
    render_stats_fragment()

    st.divider()

    # --- Utilization fragment: auto-refreshes every 5s ---
    render_utilization_fragment()

    # Footer (static)
    st.divider()
    st.markdown(
        f'<div style="text-align:center; color:#64748b; font-size:0.8em; padding:8px 0;">'
        f'EagleVision Monitoring System — Stats auto-refresh every 2s / Utilization every 5s — '
        f'Channel: {st.session_state.get("selected_channel", "all")}</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
