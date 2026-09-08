"""
IBVAP — Heatmap Tracker
=======================
Accumulates position data from tracked objects over time to generate a live heatmap.
"""

import time
import numpy as np
import cv2
from typing import Dict, List, Tuple
from collections import deque
from loguru import logger

class HeatmapTracker:
    """
    Generates a heatmap overlay based on tracked object positions.
    """
    def __init__(self, width: int = 1280, height: int = 720, history_minutes: int = 60):
        self.width = width
        self.height = height
        self.history_seconds = history_minutes * 60
        # Store (timestamp, x, y)
        self.points: deque = deque()
        self.max_points = 50000  # Cap to prevent memory issues

    def add_points(self, tracks_dict: dict):
        """Add center points of active tracks."""
        now = time.time()
        for track in tracks_dict.values():
            if track.is_active:
                x_center, y_center = track.centroid
                
                # Scale if necessary (assuming tracks are in original resolution, but we can scale to heatmap res)
                # For simplicity, let's assume standard 1280x720 or adjust dynamically
                self.points.append((now, x_center, y_center))
                
        # Maintain deque size
        while len(self.points) > self.max_points:
            self.points.popleft()

    def _clean_old_points(self, window_seconds: float):
        """Remove points older than the time window."""
        cutoff_time = time.time() - window_seconds
        while self.points and self.points[0][0] < cutoff_time:
            self.points.popleft()

    def generate_heatmap(self, window_seconds: float = 300, blur_ksize: int = 41) -> np.ndarray:
        """
        Generate a heatmap image (RGBA).
        window_seconds: How much history to include (e.g., 300 = 5 mins).
        """
        self._clean_old_points(window_seconds)
        
        # Create an empty single-channel image
        heatmap_gray = np.zeros((self.height, self.width), dtype=np.float32)
        
        if not self.points:
            # Return transparent image if no points
            return np.zeros((self.height, self.width, 4), dtype=np.uint8)

        # Accumulate points
        for _, x, y in self.points:
            if 0 <= x < self.width and 0 <= y < self.height:
                heatmap_gray[y, x] += 1.0

        # Apply Gaussian Blur to smooth points into blobs
        heatmap_gray = cv2.GaussianBlur(heatmap_gray, (blur_ksize, blur_ksize), 0)
        
        # Normalize to 0-255
        max_val = np.max(heatmap_gray)
        if max_val > 0:
            heatmap_gray = (heatmap_gray / max_val * 255).astype(np.uint8)
        else:
            heatmap_gray = heatmap_gray.astype(np.uint8)

        # Apply colormap (JET is classic for heatmaps)
        heatmap_color = cv2.applyColorMap(heatmap_gray, cv2.COLORMAP_JET)
        
        # Create alpha channel based on intensity (0 intensity = fully transparent)
        alpha_channel = heatmap_gray.copy()
        
        # Combine into RGBA
        b, g, r = cv2.split(heatmap_color)
        heatmap_rgba = cv2.merge((b, g, r, alpha_channel))
        
        return heatmap_rgba

