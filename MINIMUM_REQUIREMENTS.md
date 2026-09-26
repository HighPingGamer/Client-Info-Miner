# Minimum Run Requirements

These requirements are based on the actual components used by Client Info Miner:

- Playwright Chromium for website scanning
- PyMuPDF for PDF reading
- OpenPyXL for Excel output
- EasyOCR + PyTorch for screenshot OCR
- Ollama + `llama3.1` for local AI report extraction

This file is not a benchmark result. It is a component-based minimum. A full clean-machine install test has not been run yet.

---

## Verified Component Requirements

### Operating System

Client Info Miner is packaged for Windows.

The strictest official requirement comes from Playwright Python:

- Python 3.8 or higher
- Windows 11+, Windows Server 2019+, or WSL

Ollama for Windows requires:

- Windows 10 22H2 or newer, Home or Pro
- NVIDIA driver 452.39+ if using an NVIDIA GPU
- AMD Radeon driver if using an AMD GPU

Project decision:

- Minimum supported: Windows 11 64-bit
- May work on Windows 10 22H2, but Playwright's current official Python requirement says Windows 11+

### Python

The installer provides portable Python, so users do not need Python pre-installed.

Component requirements:

- Playwright Python: Python 3.8+
- PyTorch on Windows: Python 3.10-3.14

Project decision:

- Installer uses Python 3.11.x portable runtime.

### RAM

Ollama guidance says 7B-class models need at least 8 GB RAM available. `llama3.1:latest` / `llama3.1:8b` is the model used here and is listed by Ollama as 4.9 GB.

Client Info Miner also runs Chromium, OCR, PyTorch, PDF parsing, and Excel generation at the same time or in the same workflow.

Project decision:

- Absolute minimum: 16 GB RAM
- Recommended: 32 GB RAM

Reason: 8 GB may run the model alone, but it is not a safe minimum for this full workflow.

### Disk Space

Verified component storage:

- Ollama Windows install needs at least 4 GB for the binary install.
- `llama3.1:latest` / `llama3.1:8b` is listed by Ollama as 4.9 GB.
- Playwright installs browser binaries.
- PyTorch/EasyOCR packages are large.
- Client Info Miner stores screenshots, PDFs, JSON, Excel reports, and logs in `Scraper Data/`.

Project decision:

- Absolute minimum free space before install: 25 GB
- Recommended free space: 40 GB+

Reason: Ollama + model alone account for about 9 GB before Python packages, Playwright browser files, and generated scan data.

### GPU

GPU is not required for the minimum run path.

PyTorch says an NVIDIA GPU is recommended, but not required, on Windows. The packaged report builder now uses GPU OCR only when PyTorch detects CUDA.

Project decision:

- Minimum: no GPU required; CPU-only is allowed
- Normal/recommended use: NVIDIA CUDA-capable GPU
- Practical minimum for GPU acceleration: 6 GB VRAM
- Recommended GPU: 8 GB+ VRAM
- NVIDIA driver: 452.39+ for Ollama on Windows

CPU-only runs may be slow, especially during OCR and local AI report building.

AMD GPUs may work for Ollama on Windows with current Radeon drivers, but NVIDIA/CUDA is the clearer path for PyTorch/EasyOCR acceleration.

---

## Required Internet Access

Internet is required during install for:

- Portable Python download
- Python packages
- Playwright Chromium browser
- Optional Ollama install
- Optional `llama3.1` model download

Internet is also required during normal use to scan company websites.

---

## Installer Downloads / Installs

The installer may download or install:

- Portable Python 3.11.x
- Packages from `requirements.txt`
- Playwright Chromium
- Ollama
- `llama3.1`

First install can take a long time.

---

## Required For Report Builder

The report builder needs Ollama and the `llama3.1` model.

If the installer does not install Ollama automatically, install it manually:

https://ollama.com/download

Then run:

```powershell
ollama pull llama3.1
```

---

## Storage Warning

Client Info Miner saves scan data locally in:

```text
Scraper Data/
```

This folder can become large because it may contain:

- screenshots
- downloaded PDFs
- research JSON files
- generated Excel reports
- logs

Do not publish `Scraper Data/` to GitHub.

---

## Known Runtime Limits

- Some websites block automated browsers.
- CPU-only OCR and local AI can be slow.
- Large annual reports can take time to process.
- Very large websites can create large `Scraper Data/` folders.
- Full clean-machine install has not yet been tested.

---

## Sources Checked

- Playwright Python installation docs: https://playwright.dev/python/docs/intro
- Playwright browser install docs: https://playwright.dev/python/docs/browsers
- PyTorch Windows install docs: https://pytorch.org/get-started/locally/
- PyTorch Windows FAQ: https://docs.pytorch.org/docs/main/notes/windows.html
- EasyOCR PyPI / README: https://pypi.org/project/easyocr/
- Ollama Windows docs: https://ollama.readthedocs.io/en/windows/
- Ollama quickstart RAM guidance: https://ollama.readthedocs.io/en/quickstart/
- Ollama llama3.1 model page: https://ollama.com/library/llama3.1
