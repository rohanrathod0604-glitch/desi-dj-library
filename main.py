from __future__ import annotations

import sys

from PySide6.QtCore import QUrl, Qt, QThread, QObject, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QMenu,
)

from desi_dj.library import MusicLibrary

INDIAN_GENRES = [
    "All",
    "Bollywood Remix",
    "Punjabi",
    "Nashik Baja",
    "Tapori Mix",
    "Club Mix",
    "Garba / Dandiya",
    "Indie / Electronic",
    "House",
    "Hip Hop",
    "Rock",
    "Unknown",
]


class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.peaks = []
        self.playhead = 0.0
        self.setMinimumHeight(140)
        self.setStyleSheet("background: #111827; border: 1px solid #1f2937; border-radius: 10px;")

    def set_waveform(self, peaks):
        self.peaks = peaks
        self.update()

    def set_playhead(self, value):
        self.playhead = max(0.0, min(value, 1.0))
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QPen

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111827"))

        if not self.peaks:
            painter.setPen(QPen(QColor("#4ade80"), 1))
            painter.drawLine(0, self.height() / 2, self.width(), self.height() / 2)
            return

        w = self.width()
        h = self.height()
        x_step = (w - 10) / max(len(self.peaks), 1)

        for i, peak in enumerate(self.peaks):
            x = 5 + i * x_step
            bar_h = max(2, int(peak * (h - 18)))
            y = (h - bar_h) / 2
            painter.fillRect(int(x), int(y), max(2, int(x_step * 0.7)), bar_h, QColor("#5eead4"))

        play_x = 5 + self.playhead * (w - 10)
        painter.setPen(QPen(QColor("#fbbf24"), 2))
        painter.drawLine(int(play_x), 0, int(play_x), h)


class AnalysisWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal()

    def __init__(self, library: MusicLibrary, track_ids):
        super().__init__()
        self.library = library
        self.track_ids = track_ids

    def run(self):
        total = len(self.track_ids)
        for i, track_id in enumerate(self.track_ids):
            self.library.get_track(track_id)
            self.progress.emit(i + 1, total, f"Analyzing track {i + 1}")
        self.finished.emit()


class StatCard(QFrame):
    def __init__(self, title: str, value: str, color: str = "#38bdf8"):
        super().__init__()
        self.setObjectName("statCard")
        self.setStyleSheet(
            """
            QFrame#statCard {
                background: #111827;
                border: 1px solid #1f2937;
                border-radius: 10px;
            }
            QLabel {
                color: #e5e7eb;
                background: transparent;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #9ca3af; font-size: 10px; letter-spacing: 1px; text-transform: uppercase;")
        value_lbl = QLabel(value)
        value_lbl.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 700;")

        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)

        self.value_label = value_lbl


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Desi DJ Library")
        self.resize(1500, 900)
        self.setStyleSheet("""
            QWidget {
                background: #0b1020;
                color: #e5e7eb;
                font-family: "Segoe UI", sans-serif;
            }

            QMainWindow {
                background: #0b1020;
            }

            QPushButton {
                background: #1f2937;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #374151;
            }

            QLineEdit, QComboBox, QListWidget, QTableWidget {
                background: #111827;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 8px 10px;
            }

            QTableWidget::item {
                padding: 8px;
                background: #111827;
                color: #f3f4f6;
                border: none;
            }

            QTableWidget::item:selected {
                background: #1d4ed8;
                color: white;
            }

            QHeaderView::section {
                background: #111827;
                color: #cbd5e1;
                border: 1px solid #1f2937;
                padding: 8px;
                font-weight: 600;
            }

            QListWidget::item {
                background: #111827;
                border: 1px solid #1f2937;
                border-radius: 8px;
                padding: 10px 12px;
                margin: 2px 0;
            }

            QListWidget::item:selected {
                background: #1d4ed8;
                color: white;
            }

            QLabel {
                color: #e5e7eb;
            }
        """)

        self.library = MusicLibrary()
        self.current_tracks = []
        self.current_track_id = None
        self.current_playlist_name = "Favorites"

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.75)

        self.player.positionChanged.connect(self._on_position)

        self._build_ui()
        self.populate_genres()
        self.populate_playlists()
        self.refresh_table()
        self._ensure_defaults()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Desi DJ Library")
        title.setStyleSheet("font-size: 28px; font-weight: 700; color: #f8fafc;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.import_btn = QPushButton("Import Folder")
        self.export_csv_btn = QPushButton("Export CSV")
        self.export_m3u_btn = QPushButton("Export M3U")
        self.play_btn = QPushButton("Play / Pause")

        header_layout.addWidget(self.import_btn)
        header_layout.addWidget(self.export_csv_btn)
        header_layout.addWidget(self.export_m3u_btn)
        header_layout.addWidget(self.play_btn)

        root.addWidget(header)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search title / artist / genre")
        self.search_box.setFixedHeight(40)

        self.genre_box = QComboBox()
        self.genre_box.addItems(INDIAN_GENRES)
        self.genre_box.setFixedHeight(40)

        self.sort_box = QComboBox()
        self.sort_box.addItems(["Title", "BPM Low→High", "BPM High→Low", "Key"])
        self.sort_box.setFixedHeight(40)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(75)
        self.volume_slider.setFixedWidth(180)

        controls_layout.addWidget(self.search_box, 2)
        controls_layout.addWidget(self.genre_box)
        controls_layout.addWidget(self.sort_box)
        controls_layout.addWidget(self.volume_slider)
        root.addWidget(controls)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        root.addWidget(self.progress_bar)

        split = QSplitter(Qt.Horizontal)
        split.setStyleSheet("QSplitter::handle { background: #1f2937; }")

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(12)

        genre_title = QLabel("Genres")
        genre_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f8fafc;")
        left_layout.addWidget(genre_title)

        self.genre_list = QListWidget()
        left_layout.addWidget(self.genre_list)

        playlist_title = QLabel("Playlists")
        playlist_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f8fafc;")
        left_layout.addWidget(playlist_title)

        self.playlist_list = QListWidget()
        left_layout.addWidget(self.playlist_list)

        self.new_playlist_input = QLineEdit()
        self.new_playlist_input.setPlaceholderText("New playlist name")
        self.new_playlist_input.setFixedHeight(36)

        self.create_playlist_btn = QPushButton("Create Playlist")
        self.add_to_playlist_btn = QPushButton("Add Selected to Playlist")

        left_layout.addWidget(self.new_playlist_input)
        left_layout.addWidget(self.create_playlist_btn)
        left_layout.addWidget(self.add_to_playlist_btn)

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 10, 0)

        lib_title = QLabel("Music Library")
        lib_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f8fafc;")
        center_layout.addWidget(lib_title)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Title", "Artist", "Genre", "BPM", "Key", "Energy", "Rating", "Path"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.cellDoubleClicked.connect(self._on_track_double_click)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        center_layout.addWidget(self.table)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.track_title = QLabel("No track selected")
        self.track_title.setStyleSheet("font-size: 22px; font-weight: 700; color: #f8fafc;")
        right_layout.addWidget(self.track_title)

        self.waveform = WaveformWidget()
        right_layout.addWidget(self.waveform)

        stats = QHBoxLayout()
        self.bpm_card = StatCard("BPM", "0", "#fbbf24")
        self.key_card = StatCard("Key", "Unknown", "#34d399")
        self.energy_card = StatCard("Energy", "0", "#60a5fa")
        stats.addWidget(self.bpm_card)
        stats.addWidget(self.key_card)
        stats.addWidget(self.energy_card)
        right_layout.addLayout(stats)

        section_label = QLabel("Song Structure")
        section_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #f8fafc;")
        right_layout.addWidget(section_label)

        self.section_list = QListWidget()
        self.section_list.setFixedHeight(120)
        right_layout.addWidget(self.section_list)

        split.addWidget(left_panel)
        split.addWidget(center_panel)
        split.addWidget(right_panel)

        root.addWidget(split)

        self.import_btn.clicked.connect(self.import_folder)
        self.export_csv_btn.clicked.connect(self.export_csv)
        self.export_m3u_btn.clicked.connect(self.export_m3u)
        self.play_btn.clicked.connect(self.toggle_play)
        self.search_box.textChanged.connect(self.refresh_table)
        self.genre_box.currentTextChanged.connect(self.refresh_table)
        self.sort_box.currentTextChanged.connect(self.refresh_table)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.genre_list.itemClicked.connect(self._on_genre_selected)
        self.playlist_list.itemClicked.connect(self._on_playlist_selected)
        self.create_playlist_btn.clicked.connect(self.create_playlist)
        self.add_to_playlist_btn.clicked.connect(self.add_selected_to_playlist)

    def _ensure_defaults(self):
        playlists = self.library.list_playlists()
        if not any(p["name"] == "Favorites" for p in playlists):
            self.library.create_playlist("Favorites")
        self.populate_playlists()

    def populate_genres(self):
        self.genre_list.clear()
        for genre in INDIAN_GENRES:
            self.genre_list.addItem(QListWidgetItem(genre))
        self.genre_list.setCurrentRow(0)

    def populate_playlists(self):
        self.playlist_list.clear()
        playlists = self.library.list_playlists()
        for p in playlists:
            self.playlist_list.addItem(QListWidgetItem(p["name"]))

    def _get_selected_genre(self):
        current = self.genre_list.currentItem()
        if not current:
            return "All"
        return current.text()

    def _get_selected_sort(self):
        value = self.sort_box.currentText()
        if value == "BPM Low→High":
            return "bpm_asc"
        if value == "BPM High→Low":
            return "bpm_desc"
        if value == "Key":
            return "key"
        return "title"

    def refresh_table(self):
        query = self.search_box.text().strip()
        genre_filter = self._get_selected_genre()
        sort = self._get_selected_sort()
        if genre_filter == "All":
            genre_filter = ""
        tracks = self.library.list_tracks(query=query, genre=genre_filter, sort=sort)
        self.current_tracks = tracks

        self.table.setRowCount(len(tracks))
        for row_idx, track in enumerate(tracks):
            values = [
                str(track.get("title", "")),
                str(track.get("artist", "")),
                str(track.get("genre", "")),
                str(track.get("bpm", 0.0)),
                str(track.get("key", "Unknown")),
                str(track.get("energy", 0.0)),
                str(track.get("rating", 0)),
                str(track.get("file_path", "")),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(value))

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose music folder")
        if not folder:
            return

        imported = self.library.import_folder(folder)
        self.refresh_table()
        QMessageBox.information(self, "Import complete", f"Imported {len(imported)} tracks.")

    def export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "desi_dj_library.csv", "CSV (*.csv)")
        if not file_path:
            return
        self.library.export_csv(file_path)
        QMessageBox.information(self, "Export complete", f"Saved to {file_path}")

    def export_m3u(self):
        playlist_name = self.current_playlist_name
        file_path, _ = QFileDialog.getSaveFileName(self, "Export playlist", "playlist.m3u", "M3U (*.m3u)")
        if not file_path:
            return

        if playlist_name and playlist_name != "Favorites":
            self.library.export_m3u(playlist_name, file_path)
        else:
            tracks = self.library.list_tracks()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for track in tracks:
                    f.write(f"#EXTINF:{int(track['duration'])},{track['artist']} - {track['title']}\n")
                    f.write(f"{track['file_path']}\n")

        QMessageBox.information(self, "Export complete", f"Saved to {file_path}")

    def create_playlist(self):
        name = self.new_playlist_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Playlist", "Enter a name first.")
            return

        self.library.create_playlist(name)
        self.new_playlist_input.clear()
        self.populate_playlists()
        self.current_playlist_name = name

    def add_selected_to_playlist(self):
        playlist_item = self.playlist_list.currentItem()
        if not playlist_item:
            QMessageBox.warning(self, "Playlist", "Choose a playlist first.")
            return

        rows = {item.row() for item in self.table.selectedItems()}
        if not rows:
            QMessageBox.warning(self, "Playlist", "Select one or more tracks first.")
            return

        playlist_name = playlist_item.text()
        for row_idx in rows:
            track = self.current_tracks[row_idx]
            self.library.add_track_to_playlist(playlist_name, track["id"])

        QMessageBox.information(self, "Playlist", f"Added tracks to {playlist_name}")

    def _on_genre_selected(self, item):
        self.refresh_table()

    def _on_playlist_selected(self, item):
        playlist_name = item.text()
        self.current_playlist_name = playlist_name
        tracks = self.library.get_playlist_tracks(playlist_name)
        self.current_tracks = tracks
        self.table.setRowCount(len(tracks))
        for row_idx, track in enumerate(tracks):
            values = [
                str(track.get("title", "")),
                str(track.get("artist", "")),
                str(track.get("genre", "")),
                str(track.get("bpm", 0.0)),
                str(track.get("key", "Unknown")),
                str(track.get("energy", 0.0)),
                str(track.get("rating", 0)),
                str(track.get("file_path", "")),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        if tracks:
            self._load_track(tracks[0])

    def _load_track(self, track: dict):
        self.current_track_id = track.get("id")
        self.track_title.setText(f"{track.get('title', 'Unknown')} — {track.get('artist', 'Unknown Artist')}")

        self.bpm_card.value_label.setText(str(track.get("bpm", 0.0)))
        self.key_card.value_label.setText(str(track.get("key", "Unknown")))
        self.energy_card.value_label.setText(str(track.get("energy", 0.0)))

        waveform = track.get("waveform", [])
        if waveform:
            self.waveform.set_waveform(waveform)
        else:
            self.waveform.set_waveform([0.1] * 80)

        sections = track.get("analysis", [])
        self.section_list.clear()
        if sections:
            for sec in sections[:8]:
                label = sec.get("label", "Section")
                start = sec.get("start", 0.0)
                end = sec.get("end", 0.0)
                self.section_list.addItem(QListWidgetItem(f"{label} • {start:.1f}s → {end:.1f}s"))
        else:
            self.section_list.addItem(QListWidgetItem("No section data available"))

        if track.get("file_path"):
            self.player.setSource(QUrl.fromLocalFile(track["file_path"]))
            self.player.play()

    def _on_track_double_click(self, row, col):
        if row < 0 or row >= len(self.current_tracks):
            return
        track = self.current_tracks[row]
        self._load_track(track)

    def _table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        track = self.current_tracks[row]

        menu = QMenu(self)
        play_action = menu.addAction("Play")
        export_action = menu.addAction("Export M3U")
        action = menu.exec(self.table.mapToGlobal(pos))

        if action == play_action:
            self._load_track(track)
        elif action == export_action:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save track", f"{track.get('title', 'track')}.m3u", "M3U (*.m3u)")
            if file_path:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("#EXTM3U\n")
                    f.write(f"#EXTINF:{int(track.get('duration', 0))},{track.get('artist', 'Unknown')} - {track.get('title', 'Unknown')}\n")
                    f.write(f"{track['file_path']}\n")
                QMessageBox.information(self, "Exported", f"Saved to {file_path}")

    def _set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)

    def toggle_play(self):
        if not self.current_tracks:
            return

        if self.current_track_id is None:
            self.current_track_id = self.current_tracks[0]["id"]
            track = self.library.get_track(self.current_track_id)
            if track:
                self._load_track(track)
                return

        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_position(self, pos_ms):
        duration = self.player.duration()
        if duration > 0:
            ratio = pos_ms / duration
            self.waveform.set_playhead(ratio)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Desi DJ Library")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
