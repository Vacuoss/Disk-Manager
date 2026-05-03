# Disck Manager

Disk space analyzer with a graphical interface, file categorization, and real-time updates.

ディスク容量を分析するためのGUIアプリケーション。ファイル分類とリアルタイム更新に対応。

---

## Features / 機能

* Scan disks, folders, and files /
  ディスク・フォルダ・ファイルのスキャン
* Quick scan mode with background size calculation /
  クイックスキャン（サイズはバックグラウンドで計算）
* Search by name or full path /
  名前またはパスで検索
* Sorting by size, date, type, and category /
  サイズ・日付・種類・カテゴリで並び替え
* Path exclusion by keywords /
  キーワードによるパス除外
* English and Japanese interface /
  英語・日本語インターフェース対応
* Open files and folders in Explorer /
  エクスプローラーでファイル・フォルダを開く
* Disk usage display for all drives /
  全ドライブの使用状況表示
* Automatic refresh when files change /
  ファイル変更時の自動更新
  
<img width="1277" height="845" alt="image" src="https://github.com/user-attachments/assets/a20c22ec-e4bf-4dba-9e5c-a5b36edb926c" />


---

## Requirements / 動作環境

### Executable version / 実行ファイル版

* No installation required
  インストール不要

### Source version / ソース版

* Python 3.10–3.13

---

## Supported Operating Systems / 対応OS

### Fully supported / 完全対応

* Windows 10
* Windows 11

### Partially supported (source only) / 一部対応（ソースのみ）

* Linux（Explorer連携なし）
* macOS（Finder連携なし）

### Not supported / 非対応

* Windows 7 / 8（未検証）
* Mobile platforms

---

## Run / 起動方法

### Executable / 実行ファイル

```
dist/Disck Manager.exe
```

### From source / ソースから起動

```
python launcher.py
```

---

## Build / ビルド

```
pyinstaller --noconfirm --clean --windowed --onefile ^
  --name "Disck Manager" ^
  --icon "assets/disck_manager.ico" ^
  --add-data "assets/disck_manager.ico;assets" ^
  launcher.py
```

---

## Structure / 構成

```
launcher.py
gui.py
scanner.py
classifier.py
config.py
assets/
```

---

## Notes / 注意事項

* Large disks require more time to scan
  大容量ディスクではスキャンに時間がかかる
* Some folders may require administrator privileges
  一部フォルダは管理者権限が必要
* Antivirus warnings for the executable are possible
  実行ファイルはウイルス対策ソフトに警告される場合がある
