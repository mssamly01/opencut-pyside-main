from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.sticker_clip import StickerClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.dto.export_dto import ExportOptions, ExportResult
from app.infrastructure.gpu_encoder import GpuEncoderProbe
from app.services.keyframe_evaluator import clip_has_keyframes, ffmpeg_piecewise_expression

ProgressCallback = Callable[[float, str], None]


@dataclass(slots=True)
class _PreparedClip:
    clip: BaseClip
    input_index: int
    placeholder: bool
    source_start: float
    source_end: float


class ExportService:
    _AUDIO_SAMPLE_RATE = 48_000
    _VIDEO_CODEC = "libx264"
    _VIDEO_PRESET = "veryfast"
    _VIDEO_CRF = "23"
    _AUDIO_CODEC = "aac"
    _AUDIO_BITRATE = "192k"
    _XFADE_NAME_MAP: dict[str, str] = {
        "cross_dissolve": "fade",
        "fade_to_black": "fadeblack",
        "slide_left": "slideleft",
        "slide_right": "slideright",
        "wipe_left": "wipeleft",
        "wipe_right": "wiperight",
    }
    _qt_gui_app = None

    def __init__(self, ffmpeg_executable: str | None = None, timeout_seconds: float | None = None) -> None:
        self._ffmpeg_executable = self._resolve_ffmpeg_executable(ffmpeg_executable)
        self._timeout_seconds = timeout_seconds
        self._gpu_probe = GpuEncoderProbe(self._ffmpeg_executable)

    def export_project(
        self,
        project: Project,
        output_path: str,
        project_path: str | None = None,
        progress_callback: ProgressCallback | None = None,
        options: ExportOptions | None = None,
    ) -> ExportResult:
        if project is None:
            raise ValueError("No active project to export.")
        if not output_path or not output_path.strip():
            raise ValueError("An export output path is required.")
        if project.width <= 0 or project.height <= 0:
            raise ValueError("Project resolution must be greater than zero.")
        if project.fps <= 0:
            raise ValueError("Project FPS must be greater than zero.")
        if not any(track.clips for track in project.timeline.tracks):
            raise ValueError("Project has no clips to export.")

        effective_options = options or ExportOptions()
        effective_project = self._apply_options_to_project(project, effective_options)
        in_point, out_point = self._normalized_time_window(
            effective_options,
            max(0.0, effective_project.timeline.total_duration()),
        )

        target_path = self._normalize_output_path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        project_root = self._project_root(project_path)
        total_duration = max((out_point - in_point) if out_point is not None else (effective_project.timeline.total_duration() - in_point), 0.1)

        warnings: list[str] = []
        self._emit_progress(progress_callback, 0.0, "Preparing export")
        command = self._build_ffmpeg_command(
            effective_project,
            target_path,
            warnings,
            project_root,
            effective_options,
            in_point,
            out_point,
        )
        self._emit_progress(progress_callback, 5.0, "Launching FFmpeg")
        self._run_ffmpeg(command, total_duration, progress_callback)
        self._emit_progress(progress_callback, 100.0, "Export complete")
        return ExportResult(output_path=str(target_path), warnings=warnings)

    @staticmethod
    def _apply_options_to_project(project: Project, options: ExportOptions) -> Project:
        if (
            options.width_override is None
            and options.height_override is None
            and options.fps_override is None
        ):
            return project
        import copy

        clone = copy.copy(project)
        if options.width_override is not None:
            clone.width = max(16, int(options.width_override))
        if options.height_override is not None:
            clone.height = max(16, int(options.height_override))
        if options.fps_override is not None and options.fps_override > 0:
            clone.fps = float(options.fps_override)
        return clone

    @staticmethod
    def _normalized_time_window(options: ExportOptions, project_duration: float) -> tuple[float, float | None]:
        max_duration = max(0.0, float(project_duration))
        start = max(0.0, min(max_duration, float(options.in_point_seconds or 0.0)))
        if options.out_point_seconds is None:
            return start, None
        end = max(0.0, float(options.out_point_seconds))
        if end <= start:
            return start, None
        return start, min(end, max(max_duration, start))

    def _build_ffmpeg_command(
        self,
        project: Project,
        target_path: Path,
        warnings: list[str],
        project_root: Path | None,
        options: ExportOptions,
        in_point: float,
        out_point: float | None,
    ) -> list[str]:
        duration = max(project.timeline.total_duration(), 0.1)
        fps = project.fps if project.fps > 0 else 30.0

        command = [
            self._ffmpeg_executable,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={project.width}x{project.height}:r={fps:.6f}:d={duration:.6f}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={self._AUDIO_SAMPLE_RATE}:cl=stereo:d={duration:.6f}",
        ]

        visual_inputs: list[_PreparedClip] = []
        audio_inputs: list[_PreparedClip] = []
        input_index = 2

        text_clips: list[TextClip] = []

        for track in project.timeline.tracks:
            if track.is_hidden or track.is_muted:
                continue
            for clip in track.sorted_clips():
                if clip.is_muted:
                    continue
                if isinstance(clip, TextClip):
                    text_clips.append(clip)
                    continue

                media_asset = self._resolve_media_asset(project, clip.media_id)
                if isinstance(clip, (VideoClip, ImageClip, StickerClip)):
                    prepared_clip, input_index = self._append_visual_input(
                        command,
                        input_index,
                        clip,
                        media_asset,
                        project,
                        project_root,
                        fps,
                        warnings,
                    )
                    visual_inputs.append(prepared_clip)
                    continue

                if isinstance(clip, AudioClip):
                    prepared_clip, input_index = self._append_audio_input(
                        command,
                        input_index,
                        clip,
                        media_asset,
                        project_root,
                        warnings,
                    )
                    audio_inputs.append(prepared_clip)

        filter_parts: list[str] = ["[0:v]format=rgba[basev]"]
        current_video_label = "basev"

        for text_index, text_clip in enumerate(text_clips):
            overlays = self._build_text_clip_drawtext_chain(text_clip, project)
            for overlay_index, drawtext_options in enumerate(overlays):
                overlay_label = f"tov{text_index}_{overlay_index}"
                filter_parts.append(
                    f"[{current_video_label}]"
                    f"drawtext={':'.join(drawtext_options)}"
                    f"[{overlay_label}]"
                )
                current_video_label = overlay_label

        transition_lookup: dict[tuple[str, str], object] = {}
        for track in project.timeline.tracks:
            if track.is_hidden:
                continue
            if track.track_type.lower() not in {"video", "overlay"}:
                continue
            for transition in getattr(track, "transitions", []):
                transition_lookup[(transition.from_clip_id, transition.to_clip_id)] = transition

        consumed_in_xfade: set[str] = set()
        xfade_pair_index = 0

        for clip_index, clip_source in enumerate(visual_inputs):
            if clip_source.clip.clip_id in consumed_in_xfade:
                continue

            source_label = f"{clip_source.input_index}:v"
            clip_label = f"v{clip_index}"
            overlay_label = f"ov{clip_index}"
            source_end = self._visual_source_end_seconds(clip_source)
            video_filters = self._video_filters_for_clip(
                clip_source=clip_source,
                project=project,
                fps=fps,
                source_end=source_end,
            )
            filter_parts.append(f"[{source_label}]{','.join(video_filters)}[{clip_label}]")

            next_clip_source = visual_inputs[clip_index + 1] if clip_index + 1 < len(visual_inputs) else None
            transition = None
            if next_clip_source is not None:
                transition = transition_lookup.get((clip_source.clip.clip_id, next_clip_source.clip.clip_id))

            if transition is not None and next_clip_source is not None:
                next_source_label = f"{next_clip_source.input_index}:v"
                next_clip_label = f"v{clip_index}_b"
                next_source_end = self._visual_source_end_seconds(next_clip_source)
                next_video_filters = self._video_filters_for_clip(
                    clip_source=next_clip_source,
                    project=project,
                    fps=fps,
                    source_end=next_source_end,
                )
                filter_parts.append(
                    f"[{next_source_label}]"
                    f"{','.join(next_video_filters)}"
                    f"[{next_clip_label}]"
                )

                xfade_label = f"xf{xfade_pair_index}"
                xfade_pair_index += 1
                xfade_offset = max(
                    0.0,
                    float(clip_source.clip.duration) - float(transition.duration_seconds),
                )
                xfade_name = self._XFADE_NAME_MAP.get(
                    str(getattr(transition, "transition_type", "")),
                    "fade",
                )
                filter_parts.append(
                    f"[{clip_label}][{next_clip_label}]"
                    f"xfade=transition={xfade_name}:"
                    f"duration={float(transition.duration_seconds):.6f}:"
                    f"offset={xfade_offset:.6f}"
                    f"[{xfade_label}]"
                )

                ox, oy = self._clip_overlay_xy_expressions(clip_source.clip, project)
                filter_parts.append(
                    f"[{current_video_label}][{xfade_label}]"
                    f"overlay=x={ox}:y={oy}:eof_action=pass:repeatlast=0"
                    f"[{overlay_label}]"
                )
                current_video_label = overlay_label
                consumed_in_xfade.add(next_clip_source.clip.clip_id)
                continue

            ox, oy = self._clip_overlay_xy_expressions(clip_source.clip, project)
            filter_parts.append(
                f"[{current_video_label}][{clip_label}]"
                f"overlay=x={ox}:y={oy}:eof_action=pass:repeatlast=0"
                f"[{overlay_label}]"
            )
            current_video_label = overlay_label

        audio_output_label = "1:a"
        if audio_inputs:
            audio_streams: list[tuple[str, set[str]]] = []
            for clip_index, clip_source in enumerate(audio_inputs):
                source_label = f"{clip_source.input_index}:a"
                audio_label = f"a{clip_index}"
                delay_ms = int(round(max(0.0, clip_source.clip.timeline_start) * 1000.0))
                source_end = self._audio_source_end_seconds(clip_source)
                audio_filters: list[str] = [
                    "aformat=channel_layouts=stereo",
                    f"aresample={self._AUDIO_SAMPLE_RATE}",
                    f"atrim=start={clip_source.source_start:.6f}:end={source_end:.6f}",
                    "asetpts=PTS-STARTPTS",
                ]

                if isinstance(clip_source.clip, AudioClip):
                    speed = max(0.1, float(clip_source.clip.playback_speed))
                    audio_filters.extend(self._atempo_chain(speed))
                    volume_filter = self._audio_volume_filter_for_clip(clip_source.clip)
                    if volume_filter:
                        audio_filters.append(volume_filter)

                fade_in, fade_out = self._clip_fade_seconds(clip_source.clip)
                if fade_in > 1e-6:
                    audio_filters.append(f"afade=t=in:st=0:d={fade_in:.6f}")
                if fade_out > 1e-6:
                    fade_out_start = max(0.0, clip_source.clip.duration - fade_out)
                    audio_filters.append(f"afade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}")

                audio_filters.append(f"adelay={delay_ms}|{delay_ms}")
                filter_parts.append(f"[{source_label}]{','.join(audio_filters)}[{audio_label}]")
                label = f"[{audio_label}]"
                audio_streams.append((label, {clip_source.clip.clip_id}))

            transition_lookup: dict[tuple[str, str], object] = {}
            for track in project.timeline.tracks:
                if track.is_hidden:
                    continue
                for transition in getattr(track, "transitions", []):
                    transition_lookup[(transition.from_clip_id, transition.to_clip_id)] = transition

            processed_streams: list[tuple[str, set[str]]] = []
            stream_index = 0
            acrossfade_index = 0
            while stream_index < len(audio_streams):
                if stream_index + 1 >= len(audio_streams):
                    processed_streams.append(audio_streams[stream_index])
                    break

                left_label, left_ids = audio_streams[stream_index]
                right_label, right_ids = audio_streams[stream_index + 1]
                left_clip_id = next(iter(left_ids))
                right_clip_id = next(iter(right_ids))
                transition = transition_lookup.get((left_clip_id, right_clip_id))
                if transition is None:
                    processed_streams.append((left_label, left_ids))
                    stream_index += 1
                    continue

                acrossfade_label = f"acrossfade_{acrossfade_index}"
                acrossfade_index += 1
                duration_seconds = max(
                    0.05,
                    min(2.0, float(getattr(transition, "duration_seconds", 0.5))),
                )
                filter_parts.append(
                    f"{left_label}{right_label}"
                    f"acrossfade=d={duration_seconds:.6f}:c1=tri:c2=tri"
                    f"[{acrossfade_label}]"
                )
                merged_label = f"[{acrossfade_label}]"
                merged_ids = set(left_ids) | set(right_ids)
                processed_streams.append((merged_label, merged_ids))
                stream_index += 2

            audio_streams = processed_streams

            voice_clip_ids: set[str] = set()
            music_clip_ids: set[str] = set()
            sfx_clip_ids: set[str] = set()
            for track in project.timeline.tracks:
                if track.is_hidden or track.is_muted:
                    continue
                if track.track_type.lower() not in {"audio", "mixed"}:
                    continue
                role = str(getattr(track, "track_role", "music")).lower()
                if role == "voice":
                    target_set = voice_clip_ids
                elif role == "sfx":
                    target_set = sfx_clip_ids
                else:
                    target_set = music_clip_ids
                for clip in track.clips:
                    if isinstance(clip, AudioClip):
                        target_set.add(clip.clip_id)

            def _mix_labels(labels: list[str], output_label: str) -> str:
                if len(labels) == 1:
                    return labels[0]
                filter_parts.append(
                    f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[{output_label}]"
                )
                return f"[{output_label}]"

            final_audio_labels = [label for label, _ids in audio_streams]
            if voice_clip_ids and music_clip_ids:
                voice_labels = [
                    label
                    for label, ids in audio_streams
                    if ids.intersection(voice_clip_ids)
                ]
                music_labels = [
                    label
                    for label, ids in audio_streams
                    if ids.intersection(music_clip_ids)
                ]
                managed_ids = voice_clip_ids | music_clip_ids | sfx_clip_ids
                other_labels = [
                    label
                    for label, ids in audio_streams
                    if not ids.intersection(managed_ids)
                ]
                sfx_labels = [
                    label
                    for label, ids in audio_streams
                    if ids.intersection(sfx_clip_ids)
                ]

                if voice_labels and music_labels:
                    voice_label = _mix_labels(voice_labels, "voice_mix")
                    music_label = _mix_labels(music_labels, "music_mix")
                    # FFmpeg cannot consume the same output label twice.
                    # Voice must feed sidechain key input and final amix.
                    # Split once so each branch is consumed exactly one time.
                    filter_parts.append(
                        f"{voice_label}asplit=2[voice_for_sc][voice_for_mix]"
                    )
                    filter_parts.append(
                        f"{music_label}[voice_for_sc]"
                        "sidechaincompress=threshold=0.05:ratio=4:attack=20:release=300"
                        "[music_ducked]"
                    )
                    final_audio_labels = [
                        "[voice_for_mix]",
                        "[music_ducked]",
                        *sfx_labels,
                        *other_labels,
                    ]

            amix_input_labels = "[1:a]" + "".join(final_audio_labels)
            filter_parts.append(
                f"{amix_input_labels}amix=inputs={len(final_audio_labels) + 1}:normalize=0:duration=longest[aout]"
            )
            audio_output_label = "aout"

        codec = options.codec if options.codec in {"libx264", "libx265", "libvpx-vp9"} else self._VIDEO_CODEC
        preset = (options.preset or self._VIDEO_PRESET).strip() or self._VIDEO_PRESET
        crf = str(max(0, min(int(options.crf), 63)))

        gpu_override = (options.gpu_codec_override or "").strip().lower()
        if gpu_override == "auto":
            gpu_codec = self._gpu_probe.first_available_h264()
            if gpu_codec is not None:
                codec = gpu_codec.name
            else:
                codec = self._VIDEO_CODEC
                warnings.append("No GPU encoder detected; using software libx264.")
        elif gpu_override:
            available_names = {codec_info.name for codec_info in self._gpu_probe.available()}
            if gpu_override in available_names:
                codec = gpu_override
            else:
                codec = self._VIDEO_CODEC
                warnings.append(
                    f"Requested GPU encoder '{gpu_override}' unavailable; using software libx264."
                )

        is_gpu_codec = any(
            family in codec for family in ("_nvenc", "_qsv", "_amf", "_videotoolbox")
        )

        command.extend(["-filter_complex", ";".join(filter_parts)])
        command.extend(["-map", f"[{current_video_label}]"])
        command.extend(["-map", audio_output_label if audio_output_label == "1:a" else f"[{audio_output_label}]"])
        if in_point > 0.0:
            command.extend(["-ss", f"{in_point:.6f}"])
        if out_point is not None:
            command.extend(["-t", f"{max(0.001, out_point - in_point):.6f}"])

        if codec == "libvpx-vp9":
            command.extend(["-c:v", "libvpx-vp9", "-crf", crf, "-b:v", "0"])
        elif is_gpu_codec:
            gpu_preset = "p4" if "_nvenc" in codec else "medium"
            command.extend(
                [
                    "-c:v",
                    codec,
                    "-preset",
                    gpu_preset,
                    "-cq",
                    crf,
                    "-rc",
                    "vbr",
                ]
            )
        else:
            command.extend(["-c:v", codec, "-preset", preset, "-crf", crf])
        command.extend(
            [
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                self._AUDIO_CODEC,
                "-b:a",
                self._AUDIO_BITRATE,
                "-progress",
                "pipe:1",
                "-movflags",
                "+faststart",
                str(target_path),
            ]
        )
        return command

    @staticmethod
    def _transform_adjust_filters_for_clip(clip: BaseClip, project: Project) -> list[str]:
        if not isinstance(clip, (VideoClip, ImageClip, StickerClip)):
            return []

        project_width = max(16, int(project.width))
        project_height = max(16, int(project.height))
        filters: list[str] = []

        scale = max(0.05, min(8.0, float(getattr(clip, "scale", 1.0))))
        if clip_has_keyframes(clip, "scale"):
            scale_expr = ffmpeg_piecewise_expression(
                clip.scale_keyframes,
                default_value=scale,
                clip_duration=clip.duration,
            )
        else:
            scale_expr = f"{scale:.6f}"

        if clip_has_keyframes(clip, "scale") or abs(scale - 1.0) > 1e-6:
            filters.append(f"scale=iw*({scale_expr}):ih*({scale_expr}):eval=frame")
            filters.append(
                f"pad=w=max(iw\\,{project_width}):h=max(ih\\,{project_height}):x=(ow-iw)/2:y=(oh-ih)/2:color=#00000000"
            )
            filters.append(f"crop=w={project_width}:h={project_height}:x=(iw-{project_width})/2:y=(ih-{project_height})/2")

        rotation = float(getattr(clip, "rotation", 0.0))
        if clip_has_keyframes(clip, "rotation"):
            rotation_expr = ffmpeg_piecewise_expression(
                clip.rotation_keyframes,
                default_value=rotation,
                clip_duration=clip.duration,
            )
        else:
            rotation_expr = f"{rotation:.6f}"

        if clip_has_keyframes(clip, "rotation") or abs(rotation) > 1e-6:
            filters.append(
                f"rotate=({rotation_expr})*PI/180:ow=rotw(iw):oh=roth(ih):c=none"
            )
            filters.append(
                f"scale={project_width}:{project_height}:force_original_aspect_ratio=decrease"
            )
            filters.append(f"pad={project_width}:{project_height}:(ow-iw)/2:(oh-ih)/2:color=#00000000")

        eq_parts: list[str] = []
        brightness = max(-1.0, min(1.0, float(getattr(clip, "brightness", 0.0))))
        contrast = max(-1.0, min(1.0, float(getattr(clip, "contrast", 0.0))))
        saturation = max(-1.0, min(1.0, float(getattr(clip, "saturation", 0.0))))
        if abs(brightness) > 1e-6:
            eq_parts.append(f"brightness={brightness:.6f}")
        if abs(contrast) > 1e-6:
            eq_parts.append(f"contrast={1.0 + contrast:.6f}")
        if abs(saturation) > 1e-6:
            eq_parts.append(f"saturation={1.0 + saturation:.6f}")
        if eq_parts:
            filters.append("eq=" + ":".join(eq_parts))

        blur = max(0.0, min(1.0, float(getattr(clip, "blur", 0.0))))
        if blur > 1e-6:
            filters.append(f"gblur=sigma={max(0.2, blur * 14.0):.6f}:steps=1")

        vignette = max(0.0, min(1.0, float(getattr(clip, "vignette", 0.0))))
        if vignette > 1e-6:
            filters.append(f"vignette=angle={max(0.02, vignette * 1.57):.6f}")

        opacity = max(0.0, min(1.0, float(getattr(clip, "opacity", 1.0))))
        if clip_has_keyframes(clip, "opacity"):
            opacity_raw = ffmpeg_piecewise_expression(
                clip.opacity_keyframes,
                default_value=opacity,
                clip_duration=clip.duration,
            )
        else:
            opacity_raw = f"{opacity:.6f}"
        opacity_expr = f"min(1\\,max(0\\,{opacity_raw}))"
        if clip_has_keyframes(clip, "opacity") or abs(opacity - 1.0) > 1e-6:
            filters.append(f"colorchannelmixer=aa={opacity_expr}")
        return filters

    def _video_filters_for_clip(
        self,
        clip_source: _PreparedClip,
        project: Project,
        fps: float,
        source_end: float,
    ) -> list[str]:
        video_filters: list[str] = [
            f"trim=start={clip_source.source_start:.6f}:end={source_end:.6f}",
            "setpts=PTS-STARTPTS",
        ]
        if isinstance(clip_source.clip, VideoClip):
            if clip_source.clip.is_reversed:
                video_filters.append("reverse")
            speed_keyframes = list(getattr(clip_source.clip, "playback_speed_keyframes", []))
            static_speed = max(0.1, float(clip_source.clip.playback_speed))
            if speed_keyframes:
                speed_expr = ffmpeg_piecewise_expression(
                    speed_keyframes,
                    static_speed,
                    max(0.001, float(clip_source.clip.duration)),
                )
                video_filters.append(f"setpts=PTS/({speed_expr})")
            elif abs(static_speed - 1.0) > 1e-6:
                video_filters.append(f"setpts=PTS/{static_speed:.6f}")

        fade_in, fade_out = self._clip_fade_seconds(clip_source.clip)
        if fade_in > 1e-6:
            video_filters.append(f"fade=t=in:st=0:d={fade_in:.6f}")
        if fade_out > 1e-6:
            fade_out_start = max(0.0, clip_source.clip.duration - fade_out)
            video_filters.append(f"fade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}")

        video_filters.extend(
            [
                f"scale={project.width}:{project.height}:force_original_aspect_ratio=decrease",
                f"pad={project.width}:{project.height}:(ow-iw)/2:(oh-ih)/2",
            ]
        )
        video_filters.extend(self._transform_adjust_filters_for_clip(clip_source.clip, project))
        video_filters.extend(
            [
                f"fps={fps:.6f}",
                "format=rgba",
                f"setpts=PTS-STARTPTS+{max(0.0, clip_source.clip.timeline_start):.6f}/TB",
            ]
        )
        return video_filters

    @staticmethod
    def _clip_overlay_xy_expressions(clip: BaseClip, project: Project) -> tuple[str, str]:
        """Return x/y expressions for overlay= respecting position keyframes."""
        project_width = max(16, int(project.width))
        project_height = max(16, int(project.height))

        static_x = float(getattr(clip, "position_x", 0.5))
        static_y = float(getattr(clip, "position_y", 0.5))
        position_x_keyframes = list(getattr(clip, "position_x_keyframes", []))
        position_y_keyframes = list(getattr(clip, "position_y_keyframes", []))

        if position_x_keyframes:
            x_expr = ffmpeg_piecewise_expression(
                position_x_keyframes,
                default_value=static_x,
                clip_duration=max(0.001, float(clip.duration)),
            )
        else:
            x_expr = f"{static_x:.6f}"

        if position_y_keyframes:
            y_expr = ffmpeg_piecewise_expression(
                position_y_keyframes,
                default_value=static_y,
                clip_duration=max(0.001, float(clip.duration)),
            )
        else:
            y_expr = f"{static_y:.6f}"

        overlay_x = f"({project_width}*({x_expr})-(W/2))-((overlay_w-W)/2)"
        overlay_y = f"({project_height}*({y_expr})-(H/2))-((overlay_h-H)/2)"
        return overlay_x, overlay_y

    def _append_visual_input(
        self,
        command: list[str],
        input_index: int,
        clip: BaseClip,
        media_asset: MediaAsset | None,
        project: Project,
        project_root: Path | None,
        fps: float,
        warnings: list[str],
    ) -> tuple[_PreparedClip, int]:
        duration = max(clip.duration, 0.001)
        if isinstance(clip, StickerClip):
            sticker_path = Path(clip.sticker_path).expanduser()
            if not sticker_path.is_absolute():
                if project_root is not None:
                    sticker_path = (project_root / sticker_path).resolve()
                else:
                    sticker_path = sticker_path.resolve()
            if not sticker_path.exists() or not sticker_path.is_file():
                warnings.append(f"Missing sticker for clip '{clip.name}'; using placeholder video.")
                command.extend(
                    [
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c=gray:s={project.width}x{project.height}:r={fps:.6f}:d={duration:.6f}",
                    ]
                )
                return _PreparedClip(
                    clip=clip,
                    input_index=input_index,
                    placeholder=True,
                    source_start=0.0,
                    source_end=duration,
                ), input_index + 1

            command.extend(["-loop", "1", "-i", str(sticker_path)])
            return _PreparedClip(
                clip=clip,
                input_index=input_index,
                placeholder=False,
                source_start=0.0,
                source_end=duration,
            ), input_index + 1

        source_start, source_end = self._clip_source_bounds(clip, placeholder=media_asset is None)

        if not self._media_file_exists(media_asset, project_root):
            warnings.append(f"Missing media for clip '{clip.name}'; using placeholder video.")
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=gray:s={project.width}x{project.height}:r={fps:.6f}:d={duration:.6f}",
                ]
            )
            return _PreparedClip(
                clip=clip,
                input_index=input_index,
                placeholder=True,
                source_start=0.0,
                source_end=duration,
            ), input_index + 1

        media_path = self._resolve_media_path(media_asset.file_path, project_root)
        if isinstance(clip, ImageClip):
            command.extend(["-loop", "1", "-i", str(media_path)])
        else:
            command.extend(["-i", str(media_path)])
        return _PreparedClip(
            clip=clip,
            input_index=input_index,
            placeholder=False,
            source_start=source_start,
            source_end=source_end,
        ), input_index + 1

    def _append_audio_input(
        self,
        command: list[str],
        input_index: int,
        clip: AudioClip,
        media_asset: MediaAsset | None,
        project_root: Path | None,
        warnings: list[str],
    ) -> tuple[_PreparedClip, int]:
        duration = max(clip.duration, 0.001)
        source_start, source_end = self._clip_source_bounds(clip, placeholder=media_asset is None)

        if not self._media_file_exists(media_asset, project_root):
            warnings.append(f"Missing media for clip '{clip.name}'; using placeholder audio.")
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"anullsrc=r={self._AUDIO_SAMPLE_RATE}:cl=stereo:d={duration:.6f}",
                ]
            )
            return _PreparedClip(
                clip=clip,
                input_index=input_index,
                placeholder=True,
                source_start=0.0,
                source_end=duration,
            ), input_index + 1

        media_path = self._resolve_media_path(media_asset.file_path, project_root)
        command.extend(["-i", str(media_path)])
        return _PreparedClip(
            clip=clip,
            input_index=input_index,
            placeholder=False,
            source_start=source_start,
            source_end=source_end,
        ), input_index + 1

    @staticmethod
    def _project_root(project_path: str | None) -> Path | None:
        if project_path is None or not project_path.strip():
            return None

        resolved_path = Path(project_path).expanduser().resolve()
        if resolved_path.is_dir():
            return resolved_path
        return resolved_path.parent

    @staticmethod
    def _clip_source_bounds(clip: BaseClip, placeholder: bool) -> tuple[float, float]:
        duration = max(clip.duration, 0.001)
        if placeholder:
            return 0.0, duration

        source_start = max(0.0, clip.source_start)
        source_end = clip.source_end
        if source_end is None or source_end <= source_start:
            source_end = source_start + duration
        return source_start, source_end

    @staticmethod
    def _visual_source_end_seconds(clip_source: _PreparedClip) -> float:
        clip = clip_source.clip
        source_start = max(0.0, clip_source.source_start)
        source_end = max(clip_source.source_end, source_start + 0.001)
        if not isinstance(clip, VideoClip):
            return source_end

        speed = max(0.1, float(clip.playback_speed))
        desired_end = source_start + max(0.001, clip.duration * speed)
        if clip.source_end is None:
            return max(source_end, desired_end)
        return max(source_start + 0.001, min(source_end, desired_end))

    @staticmethod
    def _audio_source_end_seconds(clip_source: _PreparedClip) -> float:
        clip = clip_source.clip
        source_start = max(0.0, clip_source.source_start)
        source_end = max(clip_source.source_end, source_start + 0.001)
        if not isinstance(clip, AudioClip):
            return source_end

        speed = max(0.1, float(clip.playback_speed))
        desired_end = source_start + max(0.001, clip.duration * speed)
        if clip.source_end is None:
            return max(source_end, desired_end)
        return max(source_start + 0.001, min(source_end, desired_end))

    @staticmethod
    def _clip_fade_seconds(clip: BaseClip) -> tuple[float, float]:
        max_total = max(0.0, clip.duration - 0.001)
        fade_in = max(0.0, min(float(clip.fade_in_seconds), max_total))
        fade_out = max(0.0, min(float(clip.fade_out_seconds), max_total))
        if fade_in + fade_out > max_total and fade_in + fade_out > 0:
            scale = max_total / (fade_in + fade_out)
            fade_in *= scale
            fade_out *= scale
        return fade_in, fade_out

    @staticmethod
    def _atempo_chain(playback_speed: float) -> list[str]:
        speed = max(0.1, float(playback_speed))
        if abs(speed - 1.0) < 1e-6:
            return []

        filters: list[str] = []
        if speed < 1.0:
            while speed < 0.5:
                filters.append("atempo=0.5")
                speed *= 2.0
            filters.append(f"atempo={speed:.6f}")
            return filters

        while speed > 2.0:
            filters.append("atempo=2.0")
            speed /= 2.0
        filters.append(f"atempo={speed:.6f}")
        return filters

    @staticmethod
    def _audio_volume_filter_for_clip(clip: AudioClip) -> str | None:
        gain_db = float(clip.gain_db)
        if clip_has_keyframes(clip, "gain_db"):
            db_expr = ffmpeg_piecewise_expression(
                clip.gain_db_keyframes,
                default_value=gain_db,
                clip_duration=clip.duration,
            )
            return f"volume=pow(10\\,({db_expr})/20):eval=frame"

        if abs(gain_db) <= 1e-9:
            return None
        gain_factor = 10 ** (gain_db / 20.0)
        return f"volume={gain_factor:.6f}"

    @classmethod
    def _build_text_clip_drawtext_chain(cls, text_clip: TextClip, project: Project) -> list[list[str]]:
        """
        Build drawtext options for a text clip.

        Always returns one base overlay. If clip has word timings and a single line of
        text, append one overlay per word for highlight parity with preview.
        """
        start_seconds = max(0.0, text_clip.timeline_start)
        end_seconds = start_seconds + text_clip.duration

        base_options = cls._drawtext_options_for_clip(text_clip, project)
        base_options.append(f"enable='between(t,{start_seconds:.6f},{end_seconds:.6f})'")
        chain: list[list[str]] = [base_options]

        word_timings = list(getattr(text_clip, "word_timings", []) or [])
        if not word_timings:
            return chain

        raw_text = text_clip.content or "Text"
        if "\n" in raw_text:
            # Multi-line per-word export is intentionally deferred.
            return chain

        try:
            overlays = cls._build_per_word_overlays(
                text_clip=text_clip,
                project=project,
                word_timings=word_timings,
                clip_start_seconds=start_seconds,
            )
        except Exception:
            # Keep export robust in headless environments.
            return chain

        chain.extend(overlays)
        return chain

    @classmethod
    def _build_per_word_overlays(
        cls,
        text_clip: TextClip,
        project: Project,
        word_timings: list,
        clip_start_seconds: float,
    ) -> list[list[str]]:
        from PySide6.QtGui import QFont, QFontMetricsF, QGuiApplication

        if QGuiApplication.instance() is None:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            cls._qt_gui_app = QGuiApplication([])

        font = QFont(text_clip.font_family or "Arial", max(1, int(text_clip.font_size)))
        font.setBold(bool(text_clip.bold))
        font.setItalic(bool(text_clip.italic))
        metrics = QFontMetricsF(font)

        space_width = metrics.horizontalAdvance(" ")
        word_widths = [metrics.horizontalAdvance(timing.text or "") for timing in word_timings]
        content_width = sum(word_widths) + max(0, len(word_widths) - 1) * space_width

        anchor_x = float(text_clip.position_x) * float(project.width)
        anchor_y = float(text_clip.position_y) * float(project.height)
        alignment = (text_clip.alignment or "center").lower()
        if alignment == "left":
            block_left = anchor_x
        elif alignment == "right":
            block_left = anchor_x - content_width
        else:
            block_left = anchor_x - content_width / 2.0

        line_height = metrics.height()
        block_top_y = anchor_y - (line_height / 2.0)

        highlight_color = text_clip.highlight_color or "#ffd166"
        font_size = max(1, int(text_clip.font_size))
        font_file = cls._resolve_font_file(
            text_clip.font_family,
            prefer_bold=bool(text_clip.bold),
        )

        overlays: list[list[str]] = []
        cursor_x = block_left
        for index, timing in enumerate(word_timings):
            escaped_text = (
                (timing.text or "")
                .replace("\\", "\\\\")
                .replace(":", "\\:")
                .replace("'", "\\'")
                .replace("%", "\\%")
            )
            word_x = int(round(cursor_x))
            word_y = int(round(block_top_y))
            window_start = clip_start_seconds + float(timing.start_seconds)
            window_end = clip_start_seconds + float(timing.end_seconds)

            options: list[str] = [
                f"text='{escaped_text}'",
                f"fontsize={font_size}",
                f"fontcolor={highlight_color}",
                f"x={word_x}",
                f"y={word_y}",
                f"enable='between(t,{window_start:.6f},{window_end:.6f})'",
            ]
            if font_file is not None:
                options.append(f"fontfile={font_file}")
            overlays.append(options)

            cursor_x += word_widths[index]
            if index + 1 < len(word_timings):
                cursor_x += space_width

        return overlays

    @staticmethod
    def _drawtext_options_for_clip(text_clip: TextClip, project: Project) -> list[str]:
        escaped_content = (
            (text_clip.content or "Text")
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace("%", "\\%")
            .replace("\n", "\\n")
        )
        font_size = max(1, int(text_clip.font_size))
        alignment = (text_clip.alignment or "center").lower()
        anchor_x = int(text_clip.position_x * project.width)
        anchor_y = int(text_clip.position_y * project.height)

        if alignment == "left":
            x_expr = f"{anchor_x}"
        elif alignment == "right":
            x_expr = f"{anchor_x}-tw"
        else:
            x_expr = f"{anchor_x}-tw/2"
        y_expr = f"{anchor_y}-th/2"

        options: list[str] = [
            f"text='{escaped_content}'",
            f"fontsize={font_size}",
            f"fontcolor={text_clip.color or '#ffffff'}",
            f"x={x_expr}",
            f"y={y_expr}",
            "line_spacing=4",
        ]

        outline_width = max(0, int(round(float(text_clip.outline_width))))
        if outline_width > 0:
            options.append(f"bordercolor={text_clip.outline_color or '#000000'}")
            options.append(f"borderw={outline_width}")

        background_opacity = max(0.0, min(1.0, float(text_clip.background_opacity)))
        if background_opacity > 0.0:
            options.append("box=1")
            options.append(f"boxcolor={text_clip.background_color or '#000000'}@{background_opacity:.3f}")
            options.append(f"boxborderw={max(4, font_size // 6)}")

        shadow_x = int(round(float(text_clip.shadow_offset_x)))
        shadow_y = int(round(float(text_clip.shadow_offset_y)))
        if shadow_x != 0 or shadow_y != 0:
            options.append(f"shadowcolor={text_clip.shadow_color or '#000000'}")
            options.append(f"shadowx={shadow_x}")
            options.append(f"shadowy={shadow_y}")

        font_file = ExportService._resolve_font_file(text_clip.font_family, prefer_bold=bool(text_clip.bold))
        if font_file is not None:
            options.append(f"fontfile={font_file}")

        return options

    @staticmethod
    def _resolve_font_file(font_family: str | None, prefer_bold: bool = False) -> str | None:
        requested = (font_family or "").strip().lower()
        base_candidates: list[tuple[str, list[str]]] = [
            (
                "dejavu sans",
                [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                ],
            ),
            (
                "liberation sans",
                [
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                ],
            ),
            (
                "noto sans",
                [
                    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
                    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
                ],
            ),
            (
                "arial",
                [
                    "C:/Windows/Fonts/arialbd.ttf",
                    "C:/Windows/Fonts/arial.ttf",
                ],
            ),
            (
                "helvetica",
                [
                    "/System/Library/Fonts/Helvetica.ttc",
                ],
            ),
        ]

        ordered_candidates: list[str] = []
        if requested:
            for family_name, paths in base_candidates:
                if requested in family_name:
                    if prefer_bold and len(paths) > 1:
                        ordered_candidates.extend(paths)
                    else:
                        ordered_candidates.extend(reversed(paths) if len(paths) > 1 else paths)
                    break

        if not ordered_candidates:
            for _family_name, paths in base_candidates:
                if prefer_bold and len(paths) > 1:
                    ordered_candidates.extend(paths)
                else:
                    ordered_candidates.extend(reversed(paths) if len(paths) > 1 else paths)

        seen: set[str] = set()
        for path in ordered_candidates:
            if path in seen:
                continue
            seen.add(path)
            if Path(path).exists():
                return path.replace(":", "\\:")
        return None

    def _resolve_media_asset(self, project: Project, media_id: str | None) -> MediaAsset | None:
        if media_id is None:
            return None
        for media_asset in project.media_items:
            if media_asset.media_id == media_id:
                return media_asset
        return None

    @staticmethod
    def _media_file_exists(media_asset: MediaAsset | None, project_root: Path | None) -> bool:
        if media_asset is None or not media_asset.file_path:
            return False
        media_path = ExportService._resolve_media_path(media_asset.file_path, project_root)
        return media_path.exists() and media_path.is_file()

    @staticmethod
    def _resolve_media_path(file_path: str, project_root: Path | None) -> Path:
        raw_path = Path(file_path).expanduser()
        if raw_path.is_absolute():
            return raw_path.resolve()

        if project_root is not None:
            return (project_root / raw_path).resolve()

        return raw_path.resolve()

    def _normalize_output_path(self, output_path: str) -> Path:
        normalized_path = Path(output_path).expanduser()
        if normalized_path.suffix.lower() != ".mp4":
            normalized_path = normalized_path.with_suffix(".mp4")
        return normalized_path.resolve()

    def _run_ffmpeg(
        self,
        command: list[str],
        duration_seconds: float,
        progress_callback: ProgressCallback | None,
    ) -> None:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise OSError(f"Unable to run FFmpeg: {exc}") from exc

        stderr_chunks: list[str] = []
        progress_thread = threading.Thread(
            target=self._consume_ffmpeg_progress,
            args=(process.stdout, duration_seconds, progress_callback),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._drain_stream,
            args=(process.stderr, stderr_chunks),
            daemon=True,
        )
        progress_thread.start()
        stderr_thread.start()

        start_time = time.monotonic()
        try:
            if self._timeout_seconds is None:
                process.wait()
            else:
                while True:
                    try:
                        process.wait(timeout=0.25)
                        break
                    except subprocess.TimeoutExpired as timeout_exc:
                        if time.monotonic() - start_time > self._timeout_seconds:
                            process.kill()
                            process.wait()
                            raise RuntimeError(
                                f"FFmpeg export timed out after {self._timeout_seconds} seconds."
                            ) from timeout_exc
        except OSError as exc:
            process.kill()
            process.wait()
            raise OSError(f"Unable to run FFmpeg: {exc}") from exc
        finally:
            progress_thread.join()
            stderr_thread.join()

        if process.returncode != 0:
            stderr_text = "".join(stderr_chunks).strip()
            message = stderr_text or f"FFmpeg exited with code {process.returncode}"
            raise RuntimeError(message)

    @staticmethod
    def _consume_ffmpeg_progress(
        stdout: TextIO | None,
        duration_seconds: float,
        progress_callback: ProgressCallback | None,
    ) -> None:
        if stdout is None:
            return

        last_reported_percent: float | None = None
        for raw_line in stdout:
            line = raw_line.strip()
            if not line or "=" not in line:
                continue

            key, value = line.split("=", 1)
            if key == "progress":
                if value == "end":
                    ExportService._emit_progress(progress_callback, 99.9, "Finalizing export")
                    return
                continue

            elapsed_seconds = ExportService._parse_ffmpeg_progress_time(key, value)
            if elapsed_seconds is None:
                continue

            percent = ExportService._percent_from_time(elapsed_seconds, duration_seconds)
            if last_reported_percent is not None and percent <= last_reported_percent + 0.5:
                continue
            last_reported_percent = percent
            ExportService._emit_progress(progress_callback, percent, "Rendering")

    @staticmethod
    def _parse_ffmpeg_progress_time(key: str, value: str) -> float | None:
        if key == "out_time":
            return ExportService._parse_ffmpeg_timecode(value)
        if key in {"out_time_us", "out_time_ms"}:
            try:
                return int(value) / 1_000_000.0
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_ffmpeg_timecode(timecode: str) -> float | None:
        parts = timecode.strip().split(":")
        if len(parts) != 3:
            return None

        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
        except ValueError:
            return None
        return (hours * 3600.0) + (minutes * 60.0) + seconds

    @staticmethod
    def _percent_from_time(elapsed_seconds: float, duration_seconds: float) -> float:
        if duration_seconds <= 0:
            return 0.0

        percent = (elapsed_seconds / duration_seconds) * 100.0
        return max(0.0, min(percent, 99.9))

    @staticmethod
    def _emit_progress(progress_callback: ProgressCallback | None, percent: float, message: str) -> None:
        if progress_callback is None:
            return
        progress_callback(max(0.0, min(percent, 100.0)), message)

    @staticmethod
    def _drain_stream(stream: TextIO | None, sink: list[str]) -> None:
        if stream is None:
            return
        for line in stream:
            sink.append(line)

    @staticmethod
    def _resolve_ffmpeg_executable(explicit_executable: str | None) -> str:
        if explicit_executable:
            return explicit_executable

        bin_dir = Path(__file__).resolve().parents[1] / "bin"
        candidate_names = ["ffmpeg.exe"] if sys.platform.startswith("win") else ["ffmpeg"]
        for name in candidate_names:
            candidate = bin_dir / name
            if candidate.exists():
                return str(candidate)

        for name in ("ffmpeg", "ffmpeg.exe"):
            system_executable = shutil.which(name)
            if system_executable is not None:
                return system_executable

        raise FileNotFoundError("ffmpeg executable was not found.")
