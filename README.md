# University AI — MVP 1

Windows上で常駐し、授業・課題・試験をローカルに管理して決定的な期限通知を行うアプリです。MVP 1はLLMやクラウドサービスを使いません。

## 対応環境

- Windows 11
- Python 3.13（Python 3.xを想定）
- インターネット接続は通常利用時に不要

## インストール

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 起動

```powershell
python -m university_ai.app.main
```

起動後はメインウィンドウを常時表示せず、System Trayに常駐します。Trayメニューから今日の予定、未完了課題、試験、設定、終了を利用できます。

## 保存データ

既定では起動した作業ディレクトリの下に保存します。

- `data/university_ai.sqlite3`: SQLiteデータベース
- `data/settings.json`: 通知・Startup設定
- `logs/university_ai.log`: ローカルログ

## 機能

- Course / Assignment / Exam / ScheduleOverrideのSQLite管理
- CANCEL / MAKEUP / CHANGEを反映した予定表示
- 授業開始30分前、課題・試験の24時間前通知（設定変更可）
- NotificationEventの永続化とSQLite UNIQUE制約による重複抑止
- Windows Toast。初回起動時にユーザー単位のStartメニューショートカットへ AUMID を登録し、利用不可・送信失敗時はTray通知へフォールバック
- Windows Startupフォルダを利用した、ユーザー単位のログオン時自動起動

Startupは設定画面で有効化します。現在のPython実行環境とプロジェクト作業ディレクトリを参照するため、プロジェクトの移動や仮想環境の削除後は設定を無効化してから再設定してください。

Toast用の登録はStartupとは別です。`%APPDATA%\Microsoft\Windows\Start Menu\Programs\University AI.lnk` に `MillMiya.UniversityAI` を設定し、管理者権限を必要としません。

## テスト

```powershell
pytest -q
```

## MVP 1対象外

LLM、Ollama、クラウドAI、PDF/OCR/RAG、Hotkey、Overlay、Memory、Web検索、音声、自律操作、メール/SNS連携はMVP 1には含みません。
