# University AI — MVP 1

Windows上で常駐し、授業・課題・試験をローカルに管理して決定的な期限通知を行うアプリです。MVP 1はLLMやクラウドサービスを使いません。

MVP 1 は `v0.4.2` として完成・固定済みです。現在は MVP 2 のローカル入力基盤として、資料取り込み、ユーザー操作起点の画面キャプチャ、ローカルOCRを追加しています。LLM、RAG、外部通信は含みません。

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
- `data/documents/`: 取り込んだ資料の管理コピー
- `data/captures/`: ユーザーが明示的に取得した PNG 画面キャプチャ

## 機能

- Course / Assignment / Exam / ScheduleOverrideのSQLite管理
- CANCEL / MAKEUP / CHANGEを反映した予定表示
- 授業開始30分前、課題・試験の24時間前通知（設定変更可）
- NotificationEventの永続化とSQLite UNIQUE制約による重複抑止
- Windows Toast。初回起動時にユーザー単位のStartメニューショートカットへ AUMID を登録し、利用不可・送信失敗時はTray通知へフォールバック
- Windows Startupフォルダを利用した、ユーザー単位のログオン時自動起動
- Trayの「資料」からの PDF / TXT / DOCX / PNG / JPG / JPEG のローカル取り込みと、対応文書の本文抽出
- Trayの「画面キャプチャ」からの primary screen、アクティブウィンドウ、矩形範囲の PNG 保存
- Trayの「範囲を読取」から、保存した範囲PNGを完全ローカルでOCRし、結果をSQLiteへ保存

Startupは設定画面で有効化します。現在のPython実行環境とプロジェクト作業ディレクトリを参照するため、プロジェクトの移動や仮想環境の削除後は設定を無効化してから再設定してください。

画面キャプチャは Tray の明示操作時にだけ実行されます。常時・バックグラウンド監視や外部送信は行いません。全画面と範囲選択は primary screen の Qt 論理座標を使用し、active window は Windows HWND を直接取得します。

## ローカルOCR

OCRはローカルにインストールされた [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) をCLI Adapterとして使用します。PythonパッケージやクラウドAPIは追加しません。日本語・英語を読むには、Tesseractの `jpn` と `eng` 言語データが必要です。未導入・言語データ不足・画像破損時はOCR結果をFAILEDとして保存し、常駐アプリは継続します。

OCR結果の正本はSQLiteの `ocr_results` です。画像Documentの `extracted_text` は、最後に成功したOCR結果を参照しやすくする代表テキストとして更新されます。OCRはTrayの明示操作および明示的なサービス呼び出し時のみ実行されます。

Toast用の登録はStartupとは別です。`%APPDATA%\Microsoft\Windows\Start Menu\Programs\University AI.lnk` に `MillMiya.UniversityAI` を設定し、管理者権限を必要としません。

## テスト

```powershell
pytest -q
```

## MVP 1対象外

LLM、Ollama、クラウドAI、PDF/RAG、Hotkey、Overlay、Memory、Web検索、音声、自律操作、メール/SNS連携はMVP 1には含みません。
