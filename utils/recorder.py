"""Evidence Clip + Snapshot Recorder"""

import cv2
import os


class ClipRecorder:
    def __init__(self, recordings_dir):
        self.dir = recordings_dir
        os.makedirs(recordings_dir, exist_ok=True)

    def save_clip(self, frames, camera_id, timestamp, fps, width, height):
        path   = os.path.join(self.dir, f"accident_{camera_id}_{timestamp}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(path, fourcc, float(fps), (width, height))
        for f in frames:
            if f.shape[1] != width or f.shape[0] != height:
                f = cv2.resize(f, (width, height))
            writer.write(f)
        writer.release()
        mb = os.path.getsize(path) / 1024 / 1024
        print(f"[CLIP]     Saved: accident_{camera_id}_{timestamp}.mp4 ({mb:.1f} MB)")
        return path

    def save_snapshot(self, frame, camera_id, timestamp):
        path = os.path.join(self.dir, f"snapshot_{camera_id}_{timestamp}.jpg")
        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        print(f"[SNAPSHOT] Saved: snapshot_{camera_id}_{timestamp}.jpg")
        return path
