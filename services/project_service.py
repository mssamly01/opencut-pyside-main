from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.sticker_clip import StickerClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.keyframe import Keyframe
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.domain.transition import Transition
from app.domain.word_timing import WordTiming


class ProjectService:
    _FORMAT_VERSION = "1.1"

    def save_project(self, project: Project, file_path: str) -> str:
        target_path = Path(file_path).expanduser().resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._project_to_dict(project)
        target_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return str(target_path)

    def load_project(self, file_path: str) -> Project:
        source_path = Path(file_path).expanduser().resolve()
        raw_text = source_path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            raise ValueError("Invalid project file: root JSON must be an object")
        return self._project_from_dict(payload)

    def _project_to_dict(self, project: Project) -> dict[str, Any]:
        return {
            "format_version": self._FORMAT_VERSION,
            "project_id": project.project_id,
            "name": project.name,
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
            "version": project.version,
            "media_items": [self._media_asset_to_dict(media_asset) for media_asset in project.media_items],
            "timeline": self._timeline_to_dict(project.timeline),
        }

    def _project_from_dict(self, payload: dict[str, Any]) -> Project:
        timeline_data = payload.get("timeline")
        if not isinstance(timeline_data, dict):
            raise ValueError("Invalid project file: missing timeline object")

        media_items_data = payload.get("media_items", [])
        if not isinstance(media_items_data, list):
            raise ValueError("Invalid project file: media_items must be a list")

        legacy_format_version = self._read_str(payload, "format_version", default="1.0")

        project = Project(
            project_id=self._read_str(payload, "project_id"),
            name=self._read_str(payload, "name"),
            width=self._read_int(payload, "width"),
            height=self._read_int(payload, "height"),
            fps=self._read_float(payload, "fps"),
            timeline=self._timeline_from_dict(timeline_data),
            media_items=[self._media_asset_from_dict(item) for item in media_items_data if isinstance(item, dict)],
            version=self._read_str(payload, "version", default="0.1.0"),
        )
        if legacy_format_version == "1.0":
            self._migrate_word_timings_to_clip_relative(project)
        return project

    @staticmethod
    def _migrate_word_timings_to_clip_relative(project: Project) -> None:
        for track in project.timeline.tracks:
            for clip in track.clips:
                if not isinstance(clip, TextClip):
                    continue
                if not clip.word_timings:
                    continue
                offset = float(clip.timeline_start)
                clip.word_timings = [
                    WordTiming(
                        start_seconds=max(0.0, float(word.start_seconds) - offset),
                        end_seconds=max(0.0, float(word.end_seconds) - offset),
                        text=word.text,
                    )
                    for word in clip.word_timings
                ]

    def _timeline_to_dict(self, timeline: Timeline) -> dict[str, Any]:
        return {
            "tracks": [self._track_to_dict(track) for track in timeline.tracks],
        }

    def _timeline_from_dict(self, payload: dict[str, Any]) -> Timeline:
        tracks_payload = payload.get("tracks", [])
        if not isinstance(tracks_payload, list):
            raise ValueError("Invalid project file: timeline.tracks must be a list")
        return Timeline(
            tracks=[self._track_from_dict(track_payload) for track_payload in tracks_payload if isinstance(track_payload, dict)],
        )

    def _track_to_dict(self, track: Track) -> dict[str, Any]:
        return {
            "track_id": track.track_id,
            "name": track.name,
            "track_type": track.track_type,
            "track_role": track.track_role,
            "is_muted": track.is_muted,
            "is_locked": track.is_locked,
            "is_hidden": track.is_hidden,
            "height": track.height,
            "clips": [self._clip_to_dict(clip) for clip in track.clips],
            "transitions": [
                {
                    "transition_id": transition.transition_id,
                    "transition_type": transition.transition_type,
                    "duration_seconds": float(transition.duration_seconds),
                    "from_clip_id": transition.from_clip_id,
                    "to_clip_id": transition.to_clip_id,
                }
                for transition in track.transitions
            ],
        }

    def _track_from_dict(self, payload: dict[str, Any]) -> Track:
        track_id = self._read_str(payload, "track_id")
        clips_payload = payload.get("clips", [])
        if not isinstance(clips_payload, list):
            raise ValueError("Invalid project file: track.clips must be a list")
        transitions_payload = payload.get("transitions", [])
        transitions: list[Transition] = []
        if isinstance(transitions_payload, list):
            for transition_payload in transitions_payload:
                if not isinstance(transition_payload, dict):
                    continue
                try:
                    transitions.append(
                        Transition(
                            transition_id=str(transition_payload.get("transition_id", "")),
                            transition_type=str(
                                transition_payload.get(
                                    "transition_type",
                                    "cross_dissolve",
                                )
                            ),
                            duration_seconds=float(
                                transition_payload.get("duration_seconds", 0.5)
                            ),
                            from_clip_id=str(transition_payload.get("from_clip_id", "")),
                            to_clip_id=str(transition_payload.get("to_clip_id", "")),
                        )
                    )
                except (TypeError, ValueError):
                    continue

        return Track(
            track_id=track_id,
            name=self._read_str(payload, "name"),
            track_type=self._read_str(payload, "track_type"),
            track_role=self._read_str(payload, "track_role", default="music"),
            is_muted=self._read_bool(payload, "is_muted", default=False),
            is_locked=self._read_bool(payload, "is_locked", default=False),
            is_hidden=self._read_bool(payload, "is_hidden", default=False),
            height=self._read_float(payload, "height", default=58.0),
            clips=[self._clip_from_dict(clip_payload, track_id) for clip_payload in clips_payload if isinstance(clip_payload, dict)],
            transitions=transitions,
        )

    def _clip_to_dict(self, clip: BaseClip) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "clip_type": self._clip_type_name(clip),
            "clip_id": clip.clip_id,
            "name": clip.name,
            "track_id": clip.track_id,
            "timeline_start": clip.timeline_start,
            "duration": clip.duration,
            "media_id": clip.media_id,
            "source_start": clip.source_start,
            "source_end": clip.source_end,
            "opacity": clip.opacity,
            "is_locked": clip.is_locked,
            "is_muted": clip.is_muted,
            "fade_in_seconds": clip.fade_in_seconds,
            "fade_out_seconds": clip.fade_out_seconds,
            "opacity_keyframes": self._keyframes_to_dict(clip.opacity_keyframes),
        }

        if isinstance(clip, VideoClip):
            payload["playback_speed"] = clip.playback_speed
            payload["is_reversed"] = clip.is_reversed
            payload["position_x"] = clip.position_x
            payload["position_y"] = clip.position_y
            payload["scale"] = clip.scale
            payload["rotation"] = clip.rotation
            payload["brightness"] = clip.brightness
            payload["contrast"] = clip.contrast
            payload["saturation"] = clip.saturation
            payload["blur"] = clip.blur
            payload["vignette"] = clip.vignette
            payload["color_preset"] = clip.color_preset
            payload["position_x_keyframes"] = self._keyframes_to_dict(clip.position_x_keyframes)
            payload["position_y_keyframes"] = self._keyframes_to_dict(clip.position_y_keyframes)
            payload["scale_keyframes"] = self._keyframes_to_dict(clip.scale_keyframes)
            payload["rotation_keyframes"] = self._keyframes_to_dict(clip.rotation_keyframes)
            payload["playback_speed_keyframes"] = self._keyframes_to_dict(clip.playback_speed_keyframes)
        elif isinstance(clip, StickerClip):
            payload["sticker_path"] = clip.sticker_path
            payload["scale"] = clip.scale
            payload["position_x"] = clip.position_x
            payload["position_y"] = clip.position_y
            payload["rotation"] = clip.rotation
            payload["position_x_keyframes"] = self._keyframes_to_dict(clip.position_x_keyframes)
            payload["position_y_keyframes"] = self._keyframes_to_dict(clip.position_y_keyframes)
            payload["scale_keyframes"] = self._keyframes_to_dict(clip.scale_keyframes)
            payload["rotation_keyframes"] = self._keyframes_to_dict(clip.rotation_keyframes)
        elif isinstance(clip, AudioClip):
            payload["gain_db"] = clip.gain_db
            payload["playback_speed"] = clip.playback_speed
            payload["gain_db_keyframes"] = self._keyframes_to_dict(clip.gain_db_keyframes)
        elif isinstance(clip, ImageClip):
            payload["scale"] = clip.scale
            payload["position_x"] = clip.position_x
            payload["position_y"] = clip.position_y
            payload["rotation"] = clip.rotation
            payload["brightness"] = clip.brightness
            payload["contrast"] = clip.contrast
            payload["saturation"] = clip.saturation
            payload["blur"] = clip.blur
            payload["vignette"] = clip.vignette
            payload["color_preset"] = clip.color_preset
            payload["position_x_keyframes"] = self._keyframes_to_dict(clip.position_x_keyframes)
            payload["position_y_keyframes"] = self._keyframes_to_dict(clip.position_y_keyframes)
            payload["scale_keyframes"] = self._keyframes_to_dict(clip.scale_keyframes)
            payload["rotation_keyframes"] = self._keyframes_to_dict(clip.rotation_keyframes)
        elif isinstance(clip, TextClip):
            payload["content"] = clip.content
            payload["font_size"] = clip.font_size
            payload["color"] = clip.color
            payload["position_x"] = clip.position_x
            payload["position_y"] = clip.position_y
            payload["font_family"] = clip.font_family
            payload["bold"] = clip.bold
            payload["italic"] = clip.italic
            payload["alignment"] = clip.alignment
            payload["outline_color"] = clip.outline_color
            payload["outline_width"] = clip.outline_width
            payload["background_color"] = clip.background_color
            payload["background_opacity"] = clip.background_opacity
            payload["shadow_color"] = clip.shadow_color
            payload["shadow_offset_x"] = clip.shadow_offset_x
            payload["shadow_offset_y"] = clip.shadow_offset_y
            payload["scale"] = clip.scale
            payload["rotation"] = clip.rotation
            payload["position_x_keyframes"] = self._keyframes_to_dict(clip.position_x_keyframes)
            payload["position_y_keyframes"] = self._keyframes_to_dict(clip.position_y_keyframes)
            payload["scale_keyframes"] = self._keyframes_to_dict(clip.scale_keyframes)
            payload["rotation_keyframes"] = self._keyframes_to_dict(clip.rotation_keyframes)
            payload["highlight_color"] = clip.highlight_color
            payload["word_timings"] = [
                {
                    "start_seconds": float(item.start_seconds),
                    "end_seconds": float(item.end_seconds),
                    "text": str(item.text),
                }
                for item in clip.word_timings
            ]
        return payload

    def _clip_from_dict(self, payload: dict[str, Any], track_id: str) -> BaseClip:
        clip_type = self._read_str(payload, "clip_type", default="video").lower()
        base_kwargs = {
            "clip_id": self._read_str(payload, "clip_id"),
            "name": self._read_str(payload, "name"),
            "track_id": track_id,
            "timeline_start": self._read_float(payload, "timeline_start"),
            "duration": self._read_float(payload, "duration"),
            "media_id": self._read_optional_str(payload, "media_id"),
            "source_start": self._read_float(payload, "source_start", default=0.0),
            "source_end": self._read_optional_float(payload, "source_end"),
            "opacity": self._read_float(payload, "opacity", default=1.0),
            "is_locked": self._read_bool(payload, "is_locked", default=False),
            "is_muted": self._read_bool(payload, "is_muted", default=False),
            "fade_in_seconds": self._read_float(payload, "fade_in_seconds", default=0.0),
            "fade_out_seconds": self._read_float(payload, "fade_out_seconds", default=0.0),
            "opacity_keyframes": self._keyframes_from_payload(payload.get("opacity_keyframes")),
        }

        if clip_type == "video":
            return VideoClip(
                **base_kwargs,
                playback_speed=self._read_float(payload, "playback_speed", default=1.0),
                is_reversed=self._read_bool(payload, "is_reversed", default=False),
                position_x=self._read_float(payload, "position_x", default=0.5),
                position_y=self._read_float(payload, "position_y", default=0.5),
                scale=self._read_float(payload, "scale", default=1.0),
                rotation=self._read_float(payload, "rotation", default=0.0),
                brightness=self._read_float(payload, "brightness", default=0.0),
                contrast=self._read_float(payload, "contrast", default=0.0),
                saturation=self._read_float(payload, "saturation", default=0.0),
                blur=self._read_float(payload, "blur", default=0.0),
                vignette=self._read_float(payload, "vignette", default=0.0),
                color_preset=self._read_str(payload, "color_preset", default="none"),
                position_x_keyframes=self._keyframes_from_payload(payload.get("position_x_keyframes")),
                position_y_keyframes=self._keyframes_from_payload(payload.get("position_y_keyframes")),
                scale_keyframes=self._keyframes_from_payload(payload.get("scale_keyframes")),
                rotation_keyframes=self._keyframes_from_payload(payload.get("rotation_keyframes")),
                playback_speed_keyframes=self._keyframes_from_payload(payload.get("playback_speed_keyframes")),
            )
        if clip_type == "sticker":
            return StickerClip(
                **base_kwargs,
                sticker_path=self._read_str(payload, "sticker_path", default=""),
                scale=self._read_float(payload, "scale", default=0.35),
                position_x=self._read_float(payload, "position_x", default=0.5),
                position_y=self._read_float(payload, "position_y", default=0.5),
                rotation=self._read_float(payload, "rotation", default=0.0),
                position_x_keyframes=self._keyframes_from_payload(payload.get("position_x_keyframes")),
                position_y_keyframes=self._keyframes_from_payload(payload.get("position_y_keyframes")),
                scale_keyframes=self._keyframes_from_payload(payload.get("scale_keyframes")),
                rotation_keyframes=self._keyframes_from_payload(payload.get("rotation_keyframes")),
            )
        if clip_type == "audio":
            return AudioClip(
                **base_kwargs,
                gain_db=self._read_float(payload, "gain_db", default=0.0),
                playback_speed=self._read_float(payload, "playback_speed", default=1.0),
                gain_db_keyframes=self._keyframes_from_payload(payload.get("gain_db_keyframes")),
            )
        if clip_type == "image":
            return ImageClip(
                **base_kwargs,
                scale=self._read_float(payload, "scale", default=1.0),
                position_x=self._read_float(payload, "position_x", default=0.5),
                position_y=self._read_float(payload, "position_y", default=0.5),
                rotation=self._read_float(payload, "rotation", default=0.0),
                brightness=self._read_float(payload, "brightness", default=0.0),
                contrast=self._read_float(payload, "contrast", default=0.0),
                saturation=self._read_float(payload, "saturation", default=0.0),
                blur=self._read_float(payload, "blur", default=0.0),
                vignette=self._read_float(payload, "vignette", default=0.0),
                color_preset=self._read_str(payload, "color_preset", default="none"),
                position_x_keyframes=self._keyframes_from_payload(payload.get("position_x_keyframes")),
                position_y_keyframes=self._keyframes_from_payload(payload.get("position_y_keyframes")),
                scale_keyframes=self._keyframes_from_payload(payload.get("scale_keyframes")),
                rotation_keyframes=self._keyframes_from_payload(payload.get("rotation_keyframes")),
            )
        if clip_type == "text":
            return TextClip(
                **base_kwargs,
                content=self._read_str(payload, "content", default=""),
                font_size=self._read_int(payload, "font_size", default=48),
                color=self._read_str(payload, "color", default="#ffffff"),
                position_x=self._read_float(payload, "position_x", default=0.5),
                position_y=self._read_float(payload, "position_y", default=0.5),
                font_family=self._read_str(payload, "font_family", default="Arial"),
                bold=self._read_bool(payload, "bold", default=False),
                italic=self._read_bool(payload, "italic", default=False),
                alignment=self._read_str(payload, "alignment", default="center"),
                outline_color=self._read_str(payload, "outline_color", default="#000000"),
                outline_width=self._read_float(payload, "outline_width", default=0.0),
                background_color=self._read_str(payload, "background_color", default="#000000"),
                background_opacity=self._read_float(payload, "background_opacity", default=0.0),
                shadow_color=self._read_str(payload, "shadow_color", default="#000000"),
                shadow_offset_x=self._read_float(payload, "shadow_offset_x", default=0.0),
                shadow_offset_y=self._read_float(payload, "shadow_offset_y", default=0.0),
                scale=self._read_float(payload, "scale", default=1.0),
                rotation=self._read_float(payload, "rotation", default=0.0),
                position_x_keyframes=self._keyframes_from_payload(payload.get("position_x_keyframes")),
                position_y_keyframes=self._keyframes_from_payload(payload.get("position_y_keyframes")),
                scale_keyframes=self._keyframes_from_payload(payload.get("scale_keyframes")),
                rotation_keyframes=self._keyframes_from_payload(payload.get("rotation_keyframes")),
                highlight_color=self._read_str(payload, "highlight_color", default="#ffd166"),
                word_timings=self._word_timings_from_payload(payload.get("word_timings")),
            )
        raise ValueError(f"Invalid project file: unsupported clip_type '{clip_type}'")

    @staticmethod
    def _clip_type_name(clip: BaseClip) -> str:
        if isinstance(clip, VideoClip):
            return "video"
        if isinstance(clip, AudioClip):
            return "audio"
        if isinstance(clip, ImageClip):
            return "image"
        if isinstance(clip, StickerClip):
            return "sticker"
        if isinstance(clip, TextClip):
            return "text"
        return "base"

    @staticmethod
    def _word_timings_from_payload(payload: Any) -> list[WordTiming]:
        if payload is None:
            return []
        if not isinstance(payload, list):
            return []
        word_timings: list[WordTiming] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            start = item.get("start_seconds", 0.0)
            end = item.get("end_seconds", 0.0)
            text = item.get("text", "")
            if not isinstance(start, (int, float)):
                continue
            if not isinstance(end, (int, float)):
                continue
            if not isinstance(text, str):
                continue
            word_timings.append(
                WordTiming(
                    start_seconds=float(start),
                    end_seconds=float(end),
                    text=text,
                )
            )
        return word_timings

    @staticmethod
    def _media_asset_to_dict(media_asset: MediaAsset) -> dict[str, Any]:
        return {
            "media_id": media_asset.media_id,
            "name": media_asset.name,
            "file_path": media_asset.file_path,
            "media_type": media_asset.media_type,
            "duration_seconds": media_asset.duration_seconds,
            "file_size_bytes": media_asset.file_size_bytes,
        }

    def _media_asset_from_dict(self, payload: dict[str, Any]) -> MediaAsset:
        return MediaAsset(
            media_id=self._read_str(payload, "media_id"),
            name=self._read_str(payload, "name"),
            file_path=self._read_str(payload, "file_path"),
            media_type=self._read_str(payload, "media_type"),
            duration_seconds=self._read_optional_float(payload, "duration_seconds"),
            file_size_bytes=self._read_optional_int(payload, "file_size_bytes"),
        )

    @staticmethod
    def _keyframes_to_dict(keyframes: list[Keyframe]) -> list[dict[str, Any]]:
        return [
            {
                "time_seconds": float(item.time_seconds),
                "value": float(item.value),
                "interpolation": item.interpolation,
                "bezier_cp1_dx": float(item.bezier_cp1_dx),
                "bezier_cp1_dy": float(item.bezier_cp1_dy),
                "bezier_cp2_dx": float(item.bezier_cp2_dx),
                "bezier_cp2_dy": float(item.bezier_cp2_dy),
            }
            for item in keyframes
        ]

    @staticmethod
    def _keyframes_from_payload(payload: Any) -> list[Keyframe]:
        if payload is None:
            return []
        if not isinstance(payload, list):
            raise ValueError("Invalid project file: keyframes must be a list")

        keyframes: list[Keyframe] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            time_seconds = item.get("time_seconds", item.get("time", 0.0))
            value = item.get("value", 0.0)
            interpolation = item.get("interpolation", "linear")
            bezier_cp1_dx = item.get("bezier_cp1_dx", 0.42)
            bezier_cp1_dy = item.get("bezier_cp1_dy", 0.0)
            bezier_cp2_dx = item.get("bezier_cp2_dx", 0.58)
            bezier_cp2_dy = item.get("bezier_cp2_dy", 1.0)
            if not isinstance(time_seconds, (int, float)):
                continue
            if not isinstance(value, (int, float)):
                continue
            if not isinstance(interpolation, str):
                continue
            if not isinstance(bezier_cp1_dx, (int, float)):
                continue
            if not isinstance(bezier_cp1_dy, (int, float)):
                continue
            if not isinstance(bezier_cp2_dx, (int, float)):
                continue
            if not isinstance(bezier_cp2_dy, (int, float)):
                continue
            keyframes.append(
                Keyframe(
                    time_seconds=float(time_seconds),
                    value=float(value),
                    interpolation=interpolation,
                    bezier_cp1_dx=float(bezier_cp1_dx),
                    bezier_cp1_dy=float(bezier_cp1_dy),
                    bezier_cp2_dx=float(bezier_cp2_dx),
                    bezier_cp2_dy=float(bezier_cp2_dy),
                )
            )
        keyframes.sort(key=lambda item: item.time_seconds)
        return keyframes

    @staticmethod
    def _read_str(payload: dict[str, Any], key: str, default: str | None = None) -> str:
        value = payload.get(key, default)
        if isinstance(value, str):
            return value
        raise ValueError(f"Invalid project file: '{key}' must be a string")

    @staticmethod
    def _read_optional_str(payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        raise ValueError(f"Invalid project file: '{key}' must be a string or null")

    @staticmethod
    def _read_int(payload: dict[str, Any], key: str, default: int | None = None) -> int:
        value = payload.get(key, default)
        if isinstance(value, int):
            return value
        raise ValueError(f"Invalid project file: '{key}' must be an integer")

    @staticmethod
    def _read_optional_int(payload: dict[str, Any], key: str) -> int | None:
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, int):
            return value
        raise ValueError(f"Invalid project file: '{key}' must be an integer or null")

    @staticmethod
    def _read_float(payload: dict[str, Any], key: str, default: float | None = None) -> float:
        value = payload.get(key, default)
        if isinstance(value, (int, float)):
            return float(value)
        raise ValueError(f"Invalid project file: '{key}' must be numeric")

    @staticmethod
    def _read_optional_float(payload: dict[str, Any], key: str) -> float | None:
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        raise ValueError(f"Invalid project file: '{key}' must be numeric or null")

    @staticmethod
    def _read_bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
        value = payload.get(key, default)
        if isinstance(value, bool):
            return value
        raise ValueError(f"Invalid project file: '{key}' must be a boolean")
