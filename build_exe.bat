@echo off
cd /d "%~dp0"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller --noconfirm --onefile --windowed --name DesiDJ main.py --distpath dist --workpath build --specpath build

echo Build complete.
echo Output: dist\DesiDJ.exe
