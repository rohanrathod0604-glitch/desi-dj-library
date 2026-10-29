# Desi DJ Library

Free local Windows DJ music library and organizer.

## Features
- Import folders and scan music
- Auto-suggest Indian DJ genres:
  - Bollywood Remix
  - Punjabi
  - Nashik Baja
  - Tapori Mix
  - Club Mix
  - Garba / Dandiya
- BPM, key, energy and section analysis
- Waveform preview
- Playlist creation and M3U export
- CSV export
- ID3 tag write-back
- Free and no subscription

## Run from source
1. Install Python 3.11+
2. Open terminal in project folder
3. Run:
   ```bash
   python -m pip install -r requirements.txt
   ```
4. Run:
   ```bash
   python selftest.py
   ```
5. Launch:
   ```bash
   python main.py
   ```

## Build EXE
1. In project folder run:
   ```bash
   build_exe.bat
   ```
2. Output: `dist\DesiDJ.exe`

## Database location
- Windows: `%APPDATA%\DesiDJ\desidj.db`
