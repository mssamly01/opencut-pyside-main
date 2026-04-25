from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.clips.audio_clip import AudioClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


@dataclass(slots=True)
class _ClipPlaybackState:
    player: object
    media_path: str | None = None


class _RealAudioClipPlayer:
    def __init__(self, parent: QObject) -> None:
        self._audio_output = QAudioOutput(parent)
        self._audio_output.setVolume(1.0)
        self._player = QMediaPlayer(parent)
        self._player.setAudioOutput(self._audio_output)
        self._source_path: str | None = None

    def ensure_source(self, media_path: str, volume: float) -> None:
        if self._source_path != media_path:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(media_path))
            self._source_path = media_path

        self._audio_output.setVolume(volume)

    def set_position_ms(self, position_ms: int) -> None:
        self._player.setPosition(max(0, position_ms))

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def position_ms(self) -> int:
        return int(self._player.position())

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState


class AudioPlaybackService(QObject):
    def __init__(self, player_factory: object | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player_factory = player_factory or self._create_real_player
        self._players: dict[str, _ClipPlaybackState] = {}
        self._current_project_id: str | None = None
        self._seek_tolerance_ms = 80

    def clear(self) -> None:
        for clip_state in self._players.values():
            clip_state.player.stop()
        self._players.clear()
        self._current_project_id = None

    def sync_to_playhead(
        self,
        project: Project | None,
        time_seconds: float,
        project_path: str | None,
        playback_state: str,
    ) -> None:
        if project is None:
            self.clear()
            return

        if self._current_project_id != project.project_id:
            self.clear()
            self._current_project_id = project.project_id

        project_root = self._project_root(project_path)
        active_clips = self._active_audio_clips(project, time_seconds)
        active_clip_ids: set[str] = set()

        for clip in active_clips:
            media_asset = self._find_media_asset(project, clip.media_id)
            if media_asset is None:
                self._stop_clip(clip.clip_id)
                continue

            media_path = self._resolve_media_path(media_asset.file_path, project_root)
            if not media_path.exists() or not media_path.is_file():
                self._stop_clip(clip.clip_id)
                continue

            player_state = self._players.get(clip.clip_id)
            if player_state is None:
                player_state = _ClipPlaybackState(player=self._player_factory(self))
                self._players[clip.clip_id] = player_state

            player = player_state.player
            volume = self._gain_to_volume(clip.gain_db)
            player.ensure_source(str(media_path), volume)

            desired_position_ms = self._clip_position_ms(clip, time_seconds, media_asset)
            self._sync_player(player, desired_position_ms, playback_state)
            active_clip_ids.add(clip.clip_id)

        for clip_id in list(self._players):
            if clip_id in active_clip_ids:
                continue
            self._stop_clip(clip_id)

    def _stop_clip(self, clip_id: str) -> None:
        clip_state = self._players.get(clip_id)
        if clip_state is None:
            return
        clip_state.player.stop()

    def _sync_player(self, player: object, position_ms: int, playback_state: str) -> None:
        if playback_state == "playing":
            current_position = player.position_ms()
            if not player.is_playing() or abs(current_position - position_ms) > self._seek_tolerance_ms:
                player.set_position_ms(position_ms)
            player.play()
            return

        if playback_state in {"paused", "stopped"}:
            player.set_position_ms(position_ms)
            player.pause()
            return

        player.set_position_ms(0)
        player.stop()

    def _active_audio_clips(self, project: Project, time_seconds: float) -> list[AudioClip]:
        active_clips: list[AudioClip] = []
        epsilon = 1e-6
        for track in project.timeline.tracks:
            if track.is_hidden or track.is_muted:
                continue
            for clip in track.sorted_clips():
                if not isinstance(clip, AudioClip):
                    continue
                if clip.is_muted:
                    continue
                if clip.timeline_start - epsilon <= time_seconds < clip.timeline_end + epsilon:
                    active_clips.append(clip)
        return active_clips

    @staticmethod
    def _find_media_asset(project: Project, media_id: str | None) -> MediaAsset | None:
        if media_id is None:
            return None
        for media_asset in project.media_items:
            if media_asset.media_id == media_id:
                return media_asset
        return None

    @staticmethod
    def _clip_position_ms(clip: AudioClip, time_seconds: float, media_asset: MediaAsset) -> int:
        local_offset = max(0.0, time_seconds - clip.timeline_start)
        source_time = clip.source_start + local_offset
        if clip.source_end is not None:
            source_time = min(source_time, clip.source_end)

        if media_asset.duration_seconds is not None:
            safe_end = max(0.0, media_asset.duration_seconds - 0.001)
            source_time = min(source_time, safe_end)

        return max(0, int(round(source_time * 1000.0)))

    @staticmethod
    def _gain_to_volume(gain_db: float) -> float:
        if abs(gain_db) <= 1e-9:
            return 1.0
        volume = 10 ** (gain_db / 20.0)
        return max(0.0, min(1.0, volume))

    @staticmethod
    def _project_root(project_path: str | None) -> Path | None:
        if project_path is None or not project_path.strip():
            return None

        resolved_path = Path(project_path).expanduser().resolve()
        if resolved_path.is_dir():
            return resolved_path
        return resolved_path.parent

    @staticmethod
    def _resolve_media_path(file_path: str, project_root: Path | None) -> Path:
        raw_path = Path(file_path).expanduser()
        if raw_path.is_absolute():
            return raw_path.resolve()

        if project_root is not None:
            return (project_root / raw_path).resolve()

        return raw_path.resolve()

    def _create_real_player(self, parent: QObject) -> _RealAudioClipPlayer:
        return _RealAudioClipPlayer(parent)
