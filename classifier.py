from __future__ import annotations

from pathlib import Path

#Priority order matters:
#1) Windows / protected system paths
#2) Known launcher game libraries, for example steamapps/common
#3) Launcher application folders/files
#4) Cache, development, user folders, file type fallbacks

SYSTEM_ROOT_NAMES = {
    "windows",
    "system volume information",
    "$recycle.bin",
    "recovery",
    "boot",
    "efi",
    "msocache",
    "perflogs",
}

SYSTEM_PROGRAM_FILES_CHILDREN = {
    "windows defender",
    "windows defender advanced threat protection",
    "windows mail",
    "windows media player",
    "windows multimedia platform",
    "windows nt",
    "windows photo viewer",
    "windows portable devices",
    "windows security",
    "windowsapps",
    "internet explorer",
    "microsoft update health tools",
    "common files",
}

SYSTEM_PROGRAMDATA_CHILDREN = {
    "microsoft",
    "package cache",
    "usoshared",
    "windows defender",
}

#Launcher programs themselves. These should be launcher/program, not games.
LAUNCHER_FILE_NAMES = {
    "steam.exe",
    "epicgameslauncher.exe",
    "battle.net.exe",
    "riotclientservices.exe",
    "riotclientux.exe",
    "upc.exe",
    "ubisoftconnect.exe",
    "eadesktop.exe",
    "ealauncher.exe",
    "galaxyclient.exe",
    "minecraftlauncher.exe",
}

LAUNCHER_FOLDER_SEQUENCES = {
    ("program files (x86)", "steam"),
    ("program files", "steam"),
    ("program files (x86)", "epic games", "launcher"),
    ("program files", "epic games", "launcher"),
    ("program files (x86)", "battle.net"),
    ("program files", "battle.net"),
    ("program files (x86)", "blizzard app"),
    ("program files", "blizzard app"),
    ("riot games", "riot client"),
    ("program files (x86)", "ubisoft", "ubisoft game launcher"),
    ("program files", "ubisoft", "ubisoft game launcher"),
    ("program files", "ea games", "ea app"),
    ("program files", "electronic arts", "ea desktop"),
    ("program files", "gog galaxy"),
    ("program files (x86)", "gog galaxy"),
    ("minecraft launcher",),
    ("wargaming.net", "game center"),
}

#Game libraries / install locations created by launchers.
#These are trusted enough that files and folders below them are games/game data.
GAME_LIBRARY_SEQUENCES = {
    ("steamapps", "common"),
    ("steam library", "steamapps", "common"),
    ("steamlibrary", "steamapps", "common"),
    ("epic games",),
    ("program files", "epic games"),
    ("gog games",),
    ("xboxgames",),
    ("ea games",),
    ("ubisoft game launcher", "games"),
    ("riot games", "league of legends"),
    ("riot games", "valorant"),
    ("riot games", "legends of runeterra"),
    ("wargaming.net", "games"),
}

#Common Blizzard installs do not always live inside a clean "games" folder.
BLIZZARD_GAME_ROOTS = {
    "world of warcraft",
    "overwatch",
    "overwatch 2",
    "diablo iii",
    "diablo iv",
    "hearthstone",
    "heroes of the storm",
    "starcraft",
    "starcraft ii",
    "warcraft iii",
}

CACHE_SEGMENTS = {
    "cache",
    "caches",
    "code cache",
    "gpu cache",
    "shadercache",
    "shader-cache",
    "crashdumps",
    "logs",
    "log",
    "temp",
    "tmp",
    "nv_cache",
}

DEVELOPMENT_SEGMENTS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".gradle",
    ".m2",
    ".git",
    "target",
    "build",
    "dist",
    ".cargo",
    ".nuget",
}

USER_FOLDER_SEGMENTS = {
    "desktop",
    "downloads",
    "documents",
    "pictures",
    "videos",
    "music",
    "onedrive",
}

MEDIA_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".mp3", ".wav", ".flac",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".psd", ".ai",
}

DOCUMENT_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".csv", ".json", ".xml", ".yaml", ".yml",
}

ARCHIVE_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
}

INSTALLER_EXTENSIONS = {
    ".msi", ".msix", ".appx",
}

PROGRAM_EXTENSIONS = {
    ".exe", ".dll", ".sys", ".bat", ".cmd", ".ps1",
}


def _normalize(path: Path | str) -> str:
    return str(path).replace("\\", "/").lower().strip()


def _segments(path: Path | str) -> list[str]:
    raw = [part.strip() for part in _normalize(path).split("/") if part.strip()]
    if raw and raw[0].endswith(":"):
        raw = raw[1:]
    return raw


def _contains_sequence(parts: list[str], sequence: tuple[str, ...]) -> bool:
    if not sequence or len(parts) < len(sequence):
        return False
    length = len(sequence)
    return any(tuple(parts[i:i + length]) == sequence for i in range(len(parts) - length + 1))


def _extension(path: Path | str) -> str:
    try:
        return Path(str(path)).suffix.lower()
    except Exception:
        return ""


def _is_under_system_location(parts: list[str]) -> bool:
    if not parts:
        return False

    if parts[0] in SYSTEM_ROOT_NAMES:
        return True

    if len(parts) >= 2 and parts[0] in {"program files", "program files (x86)"}:
        if parts[1] in SYSTEM_PROGRAM_FILES_CHILDREN:
            return True
        if len(parts) >= 3 and parts[1] == "microsoft" and parts[2].startswith("edge"):
            return True

    if len(parts) >= 2 and parts[0] == "programdata" and parts[1] in SYSTEM_PROGRAMDATA_CHILDREN:
        return True

    return False


def _is_epic_launcher_path(parts: list[str]) -> bool:
    #Epic itself usually lives in .../Epic Games/Launcher,while games often live
    #directly under .../Epic Games/<GameName>.
    return _contains_sequence(parts, ("epic games", "launcher")) or _contains_sequence(parts, ("epicgameslauncher",))


def _is_game_library_path(parts: list[str]) -> bool:
    if _is_epic_launcher_path(parts):
        return False

    for sequence in GAME_LIBRARY_SEQUENCES:
        if _contains_sequence(parts, sequence):
            return True

    #Battle.net/Blizzard games often appear as direct install folders.
    if any(part in BLIZZARD_GAME_ROOTS for part in parts):
        return True

    return False


def _is_launcher_path(parts: list[str], file_name: str) -> bool:
    if file_name in LAUNCHER_FILE_NAMES:
        return True

    if _is_epic_launcher_path(parts):
        return True

    for sequence in LAUNCHER_FOLDER_SEQUENCES:
        if _contains_sequence(parts, sequence):
            return True

    return False


def classify_key(path: Path | str, is_dir: bool | None = None) -> str:
    parts = _segments(path)
    file_name = parts[-1] if parts else ""
    ext = _extension(path)

    #System must win over every other category.
    if _is_under_system_location(parts):
        return "system"

    #Games are only detected from launcher libraries / known install roots.
    if _is_game_library_path(parts):
        return "game"

    #Launcher applications and launcher folders.
    if _is_launcher_path(parts, file_name):
        return "launcher"

    #.exe is usually an application/program, not automatically a game.
    if ext in PROGRAM_EXTENSIONS:
        return "programs"

    if any(part in CACHE_SEGMENTS for part in parts):
        return "cache"

    if any(part in DEVELOPMENT_SEGMENTS for part in parts):
        return "development"

    if any(part in USER_FOLDER_SEGMENTS for part in parts):
        if ext in MEDIA_EXTENSIONS:
            return "media"
        if ext in DOCUMENT_EXTENSIONS:
            return "documents"
        if ext in ARCHIVE_EXTENSIONS:
            return "archives"
        if ext in INSTALLER_EXTENSIONS:
            return "installers"
        return "user_files"

    if "appdata" in parts:
        return "app_data"

    if ext in MEDIA_EXTENSIONS:
        return "media"
    if ext in DOCUMENT_EXTENSIONS:
        return "documents"
    if ext in ARCHIVE_EXTENSIONS:
        return "archives"
    if ext in INSTALLER_EXTENSIONS:
        return "installers"

    return "other"
