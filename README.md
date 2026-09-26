<img width="1672" height="941" alt="Client Info Miner flowchart" src="https://raw.githubusercontent.com/HighPingGamer/Client-Info-Miner/refs/heads/main/Image%20Sep%2026%2C%202026%2C%2001_10_24%20PM.png" />

# Client Info Miner

**Client Info Miner is a free Windows tool that turns public company websites into decision-ready client briefing reports using website scanning, report collection, OCR, local AI, and Excel output.**

It is built for people who need to understand whether a company is worth pursuing, without spending hours manually opening pages, downloading reports, copying facts, and building research notes.

## What It Does

Client Info Miner scans a company website, saves research data, downloads relevant report PDFs, and builds an Excel research report.

It has two main parts:

- `scrapper.py` scans a company website and saves research data.
- `report_builder.py` reads the saved data and builds the Excel report.

## Why This Exists

Client research is repetitive.

You usually need to:

- open the company website
- inspect services, assets, leadership, and contact details
- find reports and PDFs
- extract useful financial or ESG evidence
- decide if the company is worth more time
- turn everything into a usable briefing

Client Info Miner automates that first research pass.

## Core Workflow

```text
Company Website
      ↓
Website Scanner
      ↓
Reports + PDFs
      ↓
OCR + Local AI
      ↓
Excel Client Briefing Report
```

## Key Features

- Scans public company websites
- Captures useful website text and page evidence
- Downloads relevant report PDFs when found
- Uses OCR for screenshot/page evidence
- Uses local AI through Ollama
- Builds Excel research reports
- Keeps scan outputs local on your machine
- Designed for one-click Windows use
- Free and open source

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

## Minimum Requirements

See:

```text
MINIMUM_REQUIREMENTS.md
```

Short version:

- Windows 11 64-bit recommended
- CPU-only works, but can be slow
- NVIDIA GPU recommended for normal use
- 16 GB RAM minimum recommended for the full workflow
- 32 GB RAM recommended
- Internet required during install and website scanning

## What Gets Saved

All scan data is saved inside:

```text
Scraper Data/
```

That folder is ignored by Git because it can contain private company research, screenshots, PDFs, generated reports, and logs.

Do **not** publish your `Scraper Data/` folder.

## Run Options

The launcher offers:

1. Scan a company website.
2. Build a report from scanned data.
3. Scan, then build a report.
4. Open the data folder.

## Privacy / Local-First Notes

Client Info Miner is designed to keep generated research files on your computer.

However:

- websites you scan are visited through your internet connection
- Ollama runs the report-building AI locally
- generated screenshots, PDFs, JSON files, logs, and Excel reports may contain company research data
- you should review outputs before sharing them

## Known Limits

- The first install can take a long time because EasyOCR, Torch, Playwright, and browser files are large.
- The report builder needs enough RAM/VRAM for OCR and local AI work.
- Some websites block automated browsers.
- Large websites and annual reports can take time to process.
- Do not publish your `Scraper Data` folder.

## Project Structure

```text
Client-Info-Miner/
├─ Install-ClientInfoMiner.cmd
├─ Run-ClientInfoMiner.cmd
├─ requirements.txt
├─ MINIMUM_REQUIREMENTS.md
├─ src/
│  ├─ scrapper.py
│  └─ report_builder.py
└─ tools/
   ├─ install-client-info-miner.ps1
   └─ run-client-info-miner.ps1
```

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

## License

This project is released under the MIT License.<img width="1672" height="941" alt="image" src="https://github.com/user-attachments/assets/5329be12-3f2b-4a7a-a542-dadb0f0e0606" />
**Client Info Miner**

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

