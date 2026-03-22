"""
Stream type detection and management service.
"""
import re
from typing import Tuple


class StreamService:
    """Service for stream type detection and management."""
    
    @staticmethod
    def detect_stream_type(url: str) -> str:
        """
        Detect stream type from URL.
        
        Args:
            url: Stream URL
            
        Returns:
            Stream type: rtsp, hls, youtube_live, youtube, or http
        """
        url_lower = url.lower().strip()
        
        # RTSP streams
        if url_lower.startswith("rtsp://"):
            return "rtsp"
        
        # HLS streams
        if ".m3u8" in url_lower:
            return "hls"
        
        # YouTube detection
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            if "/live" in url_lower or "live_stream" in url_lower:
                return "youtube_live"
            # Check for live indicator in various formats
            if re.search(r'youtube\.com/live/[^/]+', url_lower):
                return "youtube_live"
            return "youtube"
        
        # HTTP/HTTPS streams (assume HLS for .m3u8 or generic HTTP)
        if url_lower.startswith(("http://", "https://")):
            # Check for common streaming patterns
            if any(pattern in url_lower for pattern in ["/hls/", "/live/", ".ts", "playlist"]):
                return "hls"
            return "hls"  # Default to HLS for HTTP streams
        
        return "rtsp"  # Default fallback
    
    @staticmethod
    def is_live_stream(url: str) -> bool:
        """Check if URL represents a live stream (not VOD)."""
        url_lower = url.lower()
        
        # RTSP is typically live
        if url_lower.startswith("rtsp://"):
            return True
        
        # YouTube Live
        if "youtube.com/live" in url_lower or "youtu.be/live" in url_lower:
            return True
        
        # HLS can be live or VOD, check for live indicators
        live_indicators = ["/live/", "live_stream", ".m3u8?", "_live"]
        return any(indicator in url_lower for indicator in live_indicators)
    
    @staticmethod
    def get_stream_display_name(stream_type: str) -> str:
        """Get human-readable display name for stream type."""
        display_names = {
            "rtsp": "RTSP Camera",
            "hls": "HLS Stream",
            "youtube": "YouTube",
            "youtube_live": "YouTube Live",
            "http": "HTTP Stream",
        }
        return display_names.get(stream_type, "Unknown")
    
    @staticmethod
    def validate_stream_url(url: str) -> Tuple[bool, str]:
        """
        Validate a stream URL format.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url or not url.strip():
            return False, "URL cannot be empty"
        
        url = url.strip()
        
        # Check for valid protocol
        valid_protocols = ["rtsp://", "http://", "https://", "rtmp://"]
        if not any(url.lower().startswith(p) for p in valid_protocols):
            return False, f"URL must start with one of: {', '.join(valid_protocols)}"
        
        # Basic URL structure check
        if " " in url:
            return False, "URL cannot contain spaces"
        
        if len(url) < 10:
            return False, "URL is too short"
        
        return True, ""
