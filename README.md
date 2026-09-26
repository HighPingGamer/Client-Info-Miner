# Client Info Miner

Client Info Miner scans a company website, saves research data, downloads relevant report PDFs, and builds an Excel research report.

It has two main parts:

- `scrapper.py` scans a company website and saves research data.
- `report_builder.py` reads the saved data and builds the Excel report.

## Quick Start For Windows

1. Download this project.
2. Unzip it.
3. Double-click `Install-ClientInfoMiner.cmd`.
4. Choose where to install it:
   - Desktop, or
   - another drive/folder.
5. Wait for the installer to set up Python, packages, and Playwright.
6. Double-click the `Client Info Miner` shortcut on your Desktop.

The installer is designed for users who do not already have Python installed.

## Important AI Requirement

The report builder uses Ollama with the `llama3.1` model.

During install, the script checks for Ollama and can try to install it with `winget`. If that does not work, install Ollama manually:

https://ollama.com/download

Then run:

```powershell
ollama pull llama3.1
```

## What Gets Saved

All scan data is saved inside:

```text
Scraper Data/
```

That folder is ignored by Git because it can contain private company research, screenshots, PDFs, generated reports, and logs.

## Run Options

The launcher offers:

1. Scan a company website.
2. Build a report from scanned data.
3. Scan, then build a report.
4. Open the data folder.

## Known Limits

- The first install can take a long time because EasyOCR, Torch, Playwright, and browser files are large.
- The report builder needs enough RAM/VRAM for OCR and local AI work.
- Some websites block automated browsers.
- Do not publish your `Scraper Data` folder.

## Developer Notes

Source files are in:

```text
src/
```

Basic syntax check:

```powershell
python -m py_compile src\scrapper.py src\report_builder.py
```

Install dependencies manually:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

