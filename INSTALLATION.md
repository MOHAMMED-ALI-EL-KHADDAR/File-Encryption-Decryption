# Quick Start Guide

## Installation (5 minutes)

### 1. Install Python 3.10+
```bash
# macOS
brew install python3

# Ubuntu/Debian
sudo apt install python3.10 python3.10-venv

# Windows: Download from https://www.python.org/downloads/
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Make Executable (Linux/macOS)
```bash
chmod +x main.py
```

---

## First Use

### Encrypt a File
```bash
python3 main.py encrypt document.pdf
```
- Enter password when prompted (min 16 chars recommended)
- Output: `document.pdf.enc`

### Decrypt the File
```bash
python3 main.py decrypt document.pdf.enc
```
- Enter password to verify
- Output: `document.pdf` (recovered)

---

## Security Checklist

✅ Use strong passwords (16+ characters, mixed case, numbers, symbols)  
✅ Store backup copies encrypted in multiple locations  
✅ Test recovery by decrypting backup files periodically  
✅ Securely delete originals: `shred -vfz document.pdf`  
✅ Keep this tool updated: `pip install --upgrade cryptography`  

---

## Support

For help:
```bash
python3 main.py --help
python3 main.py encrypt --help
python3 main.py decrypt --help
```

See `README.md` for comprehensive documentation.
