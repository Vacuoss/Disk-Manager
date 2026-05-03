# Disck Manager

Disk space analyzer with a graphical interface, file categorization, and real-time updates.

## Features

* Scan disks, folders, and files
* Quick scan mode with background size calculation
* Search by name or full path
* Sorting by size, date, type, and category
* Path exclusion by keywords
* English and Japanese interface
* Open files and folders in Explorer
* Disk usage display for all drives
* Automatic refresh when files change

## Requirements

### Executable version

* No installation required

### Source version

* Python 3.10–3.13

## Supported Operating Systems

### Fully supported

* Windows 10
* Windows 11

### Partially supported (source only)

* Linux (no Explorer integration)
* macOS (no Finder integration)

### Not supported

* Windows 7 / 8 (not tested)
* Mobile platforms

## Run

### Executable

```
dist/Disck Manager.exe
```

### From source

```
python launcher.py
```

## Build

```
pyinstaller --noconfirm --clean --windowed --onefile ^
  --name "Disck Manager" ^
  --icon "assets/disck_manager.ico" ^
  --add-data "assets/disck_manager.ico;assets" ^
  launcher.py
```

## Structure

```
launcher.py
gui.py
scanner.py
classifier.py
config.py
assets/
```

## Notes

* Large disks require more time to scan
* Some folders may require administrator privileges
* Antivirus warnings for the executable are possible
