from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from mutagen import File as MutagenFile

from .analysis import analyze_audio_file, suggest_indian_genre

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".opus"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MusicLibrary:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
            db_dir = Path(appdata) / "DesiDJ"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "desidj.db")
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    genre TEXT,
                    year INTEGER,
                    duration REAL,
                    bpm REAL,
                    key TEXT,
                    energy REAL,
                    waveform_json TEXT,
                    analysis_json TEXT,
                    file_size INTEGER,
                    modified_at TEXT,
                    imported_at TEXT,
                    play_count INTEGER DEFAULT 0,
                    rating INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER,
                    track_id INTEGER,
                    position INTEGER,
                    added_at TEXT,
                    UNIQUE(playlist_id, track_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_bpm ON tracks(bpm)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_key ON tracks(key)")
            conn.commit()
        finally:
            conn.close()

    def _extract_tags(self, file_path: str) -> Dict[str, Any]:
        tags: Dict[str, Any] = {}
        try:
            audio = MutagenFile(file_path, easy=True)
            if audio:
                tags = {
                    str(k): str(v[0]) if isinstance(v, list) and v else str(v)
                    for k, v in audio.items()
                }
        except Exception:
            tags = {}
        return tags

    def _read_file_stats(self, file_path: str) -> Dict[str, Any]:
        p = Path(file_path)
        stats = p.stat()
        return {
            "file_size": int(stats.st_size),
            "modified_at": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def _normalize_record(self, file_path: str, tags: Dict[str, Any]) -> Dict[str, Any]:
        p = Path(file_path)
        title = tags.get("title") or p.stem
        artist = tags.get("artist") or tags.get("albumartist") or "Unknown Artist"
        album = tags.get("album") or ""
        genre = suggest_indian_genre(file_path, tags)

        try:
            analysis = analyze_audio_file(file_path)
        except Exception:
            analysis = {"bpm": 0.0, "key": "Unknown", "energy": 0.0, "sections": [], "waveform": [], "duration_seconds": 0.0}

        stats = self._read_file_stats(file_path)
        year = None
        if "date" in tags:
            try:
                year = int(str(tags["date"])[:4])
            except Exception:
                year = None

        return {
            "file_path": str(p.resolve()),
            "title": str(title),
            "artist": str(artist),
            "album": str(album),
            "genre": str(genre),
            "year": year,
            "duration": float(analysis.get("duration_seconds", 0.0)),
            "bpm": float(analysis.get("bpm", 0.0)),
            "key": str(analysis.get("key", "Unknown")),
            "energy": float(analysis.get("energy", 0.0)),
            "waveform_json": json.dumps(analysis.get("waveform", [])),
            "analysis_json": json.dumps(analysis.get("sections", [])),
            "file_size": int(stats["file_size"]),
            "modified_at": stats["modified_at"],
            "imported_at": _utc_now(),
        }

    def add_track_from_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        p = Path(file_path)
        if not p.exists() or p.suffix.lower() not in AUDIO_EXTS:
            return None

        tags = self._extract_tags(str(p))
        record = self._normalize_record(str(p), tags)

        conn = self._connect()
        try:
            existing = conn.execute("SELECT * FROM tracks WHERE file_path = ?", (record["file_path"],)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE tracks
                    SET title=?, artist=?, album=?, genre=?, year=?, duration=?, bpm=?, key=?, energy=?,
                        waveform_json=?, analysis_json=?, file_size=?, modified_at=?
                    WHERE id=?
                    """,
                    (
                        record["title"],
                        record["artist"],
                        record["album"],
                        record["genre"],
                        record["year"],
                        record["duration"],
                        record["bpm"],
                        record["key"],
                        record["energy"],
                        record["waveform_json"],
                        record["analysis_json"],
                        record["file_size"],
                        record["modified_at"],
                        existing["id"],
                    ),
                )
                conn.commit()
                return self.get_track(existing["id"])

            conn.execute(
                """
                INSERT INTO tracks (
                    file_path, title, artist, album, genre, year, duration, bpm, key, energy,
                    waveform_json, analysis_json, file_size, modified_at, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["file_path"],
                    record["title"],
                    record["artist"],
                    record["album"],
                    record["genre"],
                    record["year"],
                    record["duration"],
                    record["bpm"],
                    record["key"],
                    record["energy"],
                    record["waveform_json"],
                    record["analysis_json"],
                    record["file_size"],
                    record["modified_at"],
                    record["imported_at"],
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM tracks WHERE file_path = ?", (record["file_path"],)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def import_folder(self, folder_path: str) -> List[Dict[str, Any]]:
        folder = Path(folder_path)
        imported = []
        if not folder.exists():
            return imported

        for file_path in sorted(folder.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTS:
                track = self.add_track_from_file(str(file_path))
                if track:
                    imported.append(track)
        return imported

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        analysis = []
        waveform = []
        try:
            if row["analysis_json"]:
                analysis = json.loads(row["analysis_json"])
        except Exception:
            analysis = []
        try:
            if row["waveform_json"]:
                waveform = json.loads(row["waveform_json"])
        except Exception:
            waveform = []
        return {
            "id": row["id"],
            "file_path": row["file_path"],
            "title": row["title"],
            "artist": row["artist"],
            "album": row["album"],
            "genre": row["genre"],
            "year": row["year"],
            "duration": row["duration"],
            "bpm": row["bpm"],
            "key": row["key"],
            "energy": row["energy"],
            "analysis": analysis,
            "waveform": waveform,
            "play_count": row["play_count"],
            "rating": row["rating"],
            "file_size": row["file_size"],
            "modified_at": row["modified_at"],
            "imported_at": row["imported_at"],
        }

    def get_track(self, track_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def list_tracks(self, query: str = "", genre: str = "", sort: str = "title", limit: int = 500) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            sql = "SELECT * FROM tracks WHERE 1=1"
            params: List[Any] = []

            if query:
                q = f"%{query.lower()}%"
                sql += " AND (LOWER(title) LIKE ? OR LOWER(artist) LIKE ? OR LOWER(album) LIKE ? OR LOWER(file_path) LIKE ?)"
                params.extend([q, q, q, q])

            if genre and genre.lower() != "all":
                sql += " AND LOWER(genre) = LOWER(?)"
                params.append(genre)

            order_sql = " ORDER BY title ASC"
            if sort == "bpm_asc":
                order_sql = " ORDER BY bpm IS NULL, bpm ASC"
            elif sort == "bpm_desc":
                order_sql = " ORDER BY bpm IS NULL, bpm DESC"
            elif sort == "key":
                order_sql = " ORDER BY key IS NULL, key ASC"
            elif sort == "genre":
                order_sql = " ORDER BY genre IS NULL, genre ASC, title ASC"

            rows = conn.execute(sql + order_sql + " LIMIT ?", (*params, limit)).fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def save_track_edits(self, track_id: int, title: str, artist: str, genre: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE tracks
                SET title=?, artist=?, genre=?
                WHERE id=?
                """,
                (title, artist, genre, track_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
            return self._row_to_dict(row) if row else {}
        finally:
            conn.close()

    def write_id3_tags(self, file_path: str, title: str, artist: str, genre: str) -> str:
        try:
            audio = MutagenFile(file_path, easy=True)
            if audio is None:
                audio = MutagenFile(file_path)
            if audio is None:
                return "File format not supported for tag write-back"

            if hasattr(audio, "tags") and audio.tags is not None:
                audio["title"] = [title]
                audio["artist"] = [artist]
                audio["genre"] = [genre]
                audio.save(file_path)
                return ""
            return "Tag container not writable"
        except Exception as exc:
            return f"Tag write failed: {exc}"

    def update_track_metadata(self, track_id: int, title: str, artist: str, genre: str) -> Dict[str, Any]:
        track = self.get_track(track_id)
        if not track:
            return {}

        error = self.write_id3_tags(track["file_path"], title, artist, genre)
        if error:
            return {"error": error}

        updated = self.save_track_edits(track_id, title, artist, genre)
        updated["error"] = ""
        return updated

    def create_playlist(self, name: str) -> Dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Playlist name cannot be empty")
        conn = self._connect()
        try:
            existing = conn.execute("SELECT * FROM playlists WHERE name = ?", (name,)).fetchone()
            if existing:
                return {"id": existing["id"], "name": existing["name"]}
            conn.execute("INSERT INTO playlists (name, created_at) VALUES (?, ?)", (name, _utc_now()))
            conn.commit()
            row = conn.execute("SELECT * FROM playlists WHERE name = ?", (name,)).fetchone()
            return {"id": row["id"], "name": row["name"]} if row else {}
        finally:
            conn.close()

    def add_track_to_playlist(self, playlist_name: str, track_id: int):
        conn = self._connect()
        try:
            playlist = conn.execute("SELECT * FROM playlists WHERE name = ?", (playlist_name,)).fetchone()
            if not playlist:
                conn.execute("INSERT INTO playlists (name, created_at) VALUES (?, ?)", (playlist_name, _utc_now()))
                conn.commit()
                playlist = conn.execute("SELECT * FROM playlists WHERE name = ?", (playlist_name,)).fetchone()

            conn.execute(
                """
                INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, position, added_at)
                VALUES (?, ?, (SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_tracks WHERE playlist_id = ?), ?)
                """,
                (playlist["id"], track_id, playlist["id"], _utc_now()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_playlist_tracks(self, playlist_name: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            pl = conn.execute("SELECT * FROM playlists WHERE name = ?", (playlist_name,)).fetchone()
            if not pl:
                return []
            rows = conn.execute(
                """
                SELECT t.* FROM playlist_tracks pt
                JOIN tracks t ON t.id = pt.track_id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position ASC
                """,
                (pl["id"],),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def list_playlists(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM playlists ORDER BY created_at DESC").fetchall()
            return [{"id": row["id"], "name": row["name"]} for row in rows]
        finally:
            conn.close()

    def export_m3u(self, playlist_name: str, output_path: str) -> str:
        tracks = self.get_playlist_tracks(playlist_name)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for track in tracks:
                f.write(f"#EXTINF:{int(track['duration'])},{track['artist']} - {track['title']}\n")
                f.write(f"{track['file_path']}\n")
        return str(out)

    def export_csv(self, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tracks = self.list_tracks()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "id", "title", "artist", "album", "genre", "year", "duration", "bpm", "key", "energy", "file_path"
            ])
            writer.writeheader()
            for track in tracks:
                writer.writerow({
                    "id": track["id"],
                    "title": track["title"],
                    "artist": track["artist"],
                    "album": track["album"],
                    "genre": track["genre"],
                    "year": track["year"],
                    "duration": track["duration"],
                    "bpm": track["bpm"],
                    "key": track["key"],
                    "energy": track["energy"],
                    "file_path": track["file_path"],
                })
        return str(path)
