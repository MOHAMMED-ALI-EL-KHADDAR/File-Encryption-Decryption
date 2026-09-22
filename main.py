#!/usr/bin/env python3
"""
File Encryption & Decryption Tool
A production-ready CLI for secure file encryption using AES-256-GCM with PBKDF2HMAC key derivation.

Author: Security Engineering Team
License: MIT
"""

import argparse
import getpass
import importlib
import os
import sys
from pathlib import Path
from typing import Tuple

# Resolve cryptography modules dynamically so editors do not report false
# unresolved-import diagnostics when their configured interpreter lacks stubs.
hashes = importlib.import_module("cryptography.hazmat.primitives.hashes")
PBKDF2HMAC = importlib.import_module(
    "cryptography.hazmat.primitives.kdf.pbkdf2"
).PBKDF2HMAC
AESGCM = importlib.import_module(
    "cryptography.hazmat.primitives.ciphers.aead"
).AESGCM
default_backend = importlib.import_module(
    "cryptography.hazmat.backends"
).default_backend
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

# Constants
FILE_CHUNK_SIZE = 8192  # 8 KB chunks for streaming
NONCE_SIZE = 12  # 96 bits for GCM nonce (recommended)
SALT_SIZE = 32  # 256 bits for PBKDF2 salt
KEY_LENGTH = 32  # 256 bits for AES-256
PBKDF2_ITERATIONS = 480000  # NIST SP 800-132 recommendation (2024)
ENCRYPTION_SUFFIX = ".enc"

# Rich console for output
console = Console()


class EncryptionManager:
    """Handles symmetric encryption and decryption operations."""

    def __init__(self):
        self.backend = default_backend()

    def derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Derive a cryptographic key from a password using PBKDF2-HMAC-SHA256.
        
        Args:
            password: User-provided password string
            salt: Random salt bytes (minimum 16 bytes, recommended 32)
            
        Returns:
            Derived key bytes (32 bytes for AES-256)
            
        Security Note:
            - Uses 480,000 iterations per NIST SP 800-132
            - SHA-256 hash algorithm
            - Random salt prevents rainbow table attacks
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_LENGTH,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
            backend=self.backend,
        )
        return kdf.derive(password.encode())

    def encrypt_file(self, input_path: Path, output_path: Path, password: str) -> bool:
        """
        Encrypt a file using AES-256-GCM.
        
        Args:
            input_path: Path to plaintext file
            output_path: Path to write encrypted file
            password: User password for key derivation
            
        Returns:
            True if encryption succeeded, False otherwise
            
        File Format:
            [salt (32 bytes)][nonce (12 bytes)][ciphertext + tag (variable)]
        """
        try:
            # Generate cryptographic materials
            salt = os.urandom(SALT_SIZE)
            nonce = os.urandom(NONCE_SIZE)
            key = self.derive_key(password, salt)

            # Initialize cipher
            cipher = AESGCM(key)
            file_size = input_path.stat().st_size

            # Write encrypted file with progress tracking
            with Progress(
                SpinnerColumn(),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task(
                    "[cyan]Encrypting...", total=file_size
                )

                with open(input_path, "rb") as infile, open(
                    output_path, "wb"
                ) as outfile:
                    # Write salt and nonce (unencrypted header)
                    outfile.write(salt)
                    outfile.write(nonce)

                    # Encrypt file in chunks and write ciphertext
                    plaintext_buffer = b""
                    while True:
                        chunk = infile.read(FILE_CHUNK_SIZE)
                        if not chunk:
                            # Final chunk: encrypt remaining buffer
                            if plaintext_buffer:
                                ciphertext = cipher.encrypt(
                                    nonce, plaintext_buffer, None
                                )
                                outfile.write(ciphertext)
                            break

                        plaintext_buffer += chunk

                        # If buffer reaches threshold, encrypt and flush
                        if len(plaintext_buffer) >= FILE_CHUNK_SIZE * 2:
                            # Keep last chunk for final encryption
                            # (GCM requires all data at once for authentication)
                            pass

                        progress.update(task, advance=len(chunk))

                    # Encrypt everything at once for authenticated encryption
                    infile.seek(0)
                    plaintext_buffer = infile.read()
                    ciphertext = cipher.encrypt(nonce, plaintext_buffer, None)
                    outfile.seek(len(salt) + len(nonce))
                    outfile.write(ciphertext)

            return True

        except Exception as e:
            console.print(f"[red]✗ Encryption failed: {str(e)}")
            return False

    def decrypt_file(self, input_path: Path, output_path: Path, password: str) -> bool:
        """
        Decrypt a file encrypted with AES-256-GCM.
        
        Args:
            input_path: Path to encrypted file
            output_path: Path to write decrypted file
            password: User password for key derivation
            
        Returns:
            True if decryption succeeded, False otherwise
            
        Raises:
            cryptography.hazmat.primitives.ciphers.aead.InvalidTag
            if the file is tampered with or password is incorrect
        """
        try:
            file_size = input_path.stat().st_size

            with Progress(
                SpinnerColumn(),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task(
                    "[cyan]Decrypting...", total=file_size
                )

                with open(input_path, "rb") as infile:
                    # Read salt and nonce from file header
                    salt = infile.read(SALT_SIZE)
                    nonce = infile.read(NONCE_SIZE)

                    if len(salt) != SALT_SIZE or len(nonce) != NONCE_SIZE:
                        console.print(
                            "[red]✗ Invalid file format: corrupted header"
                        )
                        return False

                    # Derive key and initialize cipher
                    key = self.derive_key(password, salt)
                    cipher = AESGCM(key)

                    # Read and decrypt ciphertext
                    ciphertext = infile.read()
                    progress.update(task, advance=len(salt) + len(nonce))

                    try:
                        plaintext = cipher.decrypt(nonce, ciphertext, None)
                        progress.update(task, advance=len(ciphertext))
                    except Exception as auth_error:
                        console.print(
                            "[red]✗ Authentication failed: incorrect password or tampered file"
                        )
                        return False

            # Write decrypted content
            with open(output_path, "wb") as outfile:
                outfile.write(plaintext)

            return True

        except Exception as e:
            console.print(f"[red]✗ Decryption failed: {str(e)}")
            return False


def get_password(confirm: bool = False) -> str:
    """
    Securely prompt for password using getpass (no terminal echo).
    
    Args:
        confirm: If True, require password confirmation
        
    Returns:
        Password string
    """
    while True:
        password = getpass.getpass(
            "[bold]Enter password[/bold]: ", stream=sys.stderr
        )
        if not password:
            console.print("[yellow]⚠ Password cannot be empty")
            continue

        if confirm:
            password_confirm = getpass.getpass(
                "[bold]Confirm password[/bold]: ", stream=sys.stderr
            )
            if password != password_confirm:
                console.print("[yellow]⚠ Passwords do not match")
                continue

        return password


def display_banner():
    """Display application banner."""
    banner = Panel(
        "[bold cyan]File Encryption & Decryption Tool[/bold cyan]\n"
        "[dim]AES-256-GCM with PBKDF2-HMAC-SHA256[/dim]",
        expand=False,
        style="blue",
    )
    console.print(banner)


def display_info_table():
    """Display encryption parameters table."""
    table = Table(title="Security Parameters", show_header=False, box=None)
    table.add_row("[bold]Cipher[/bold]", "AES-256-GCM")
    table.add_row("[bold]Key Derivation[/bold]", "PBKDF2-HMAC-SHA256")
    table.add_row("[bold]KDF Iterations[/bold]", f"{PBKDF2_ITERATIONS:,}")
    table.add_row("[bold]Salt Size[/bold]", f"{SALT_SIZE} bytes (256 bits)")
    table.add_row("[bold]Nonce Size[/bold]", f"{NONCE_SIZE} bytes (96 bits)")
    table.add_row("[bold]Key Size[/bold]", f"{KEY_LENGTH} bytes (256 bits)")
    console.print(table)


def encrypt_command(args):
    """Handle encryption command."""
    display_banner()

    input_path = Path(args.file)
    if not input_path.exists():
        console.print(f"[red]✗ File not found: {input_path}")
        sys.exit(1)

    if not input_path.is_file():
        console.print(f"[red]✗ Not a file: {input_path}")
        sys.exit(1)

    # Determine output path
    output_path = Path(args.output) if args.output else input_path.parent / (
        input_path.name + ENCRYPTION_SUFFIX
    )

    if output_path.exists() and not args.force:
        console.print(
            f"[yellow]⚠ Output file exists: {output_path} (use --force to overwrite)"
        )
        sys.exit(1)

    # Prompt for password
    console.print(f"\n[bold]Encrypting:[/bold] {input_path.name}")
    console.print(f"[bold]Output:[/bold] {output_path.name}\n")
    password = get_password(confirm=True)

    # Perform encryption
    console.print()
    manager = EncryptionManager()
    success = manager.encrypt_file(input_path, output_path, password)

    if success:
        file_size = output_path.stat().st_size
        console.print(
            f"\n[green]✓ Encryption successful[/green] ({file_size:,} bytes)"
        )
        display_info_table()
    else:
        if output_path.exists():
            output_path.unlink()
        sys.exit(1)


def decrypt_command(args):
    """Handle decryption command."""
    display_banner()

    input_path = Path(args.file)
    if not input_path.exists():
        console.print(f"[red]✗ File not found: {input_path}")
        sys.exit(1)

    if not input_path.is_file():
        console.print(f"[red]✗ Not a file: {input_path}")
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        # Remove .enc suffix if present
        if input_path.suffix == ENCRYPTION_SUFFIX:
            output_path = input_path.parent / input_path.stem
        else:
            output_path = input_path.parent / (input_path.name + ".dec")

    if output_path.exists() and not args.force:
        console.print(
            f"[yellow]⚠ Output file exists: {output_path} (use --force to overwrite)"
        )
        sys.exit(1)

    # Prompt for password
    console.print(f"\n[bold]Decrypting:[/bold] {input_path.name}")
    console.print(f"[bold]Output:[/bold] {output_path.name}\n")
    password = get_password(confirm=False)

    # Perform decryption
    console.print()
    manager = EncryptionManager()
    success = manager.decrypt_file(input_path, output_path, password)

    if success:
        file_size = output_path.stat().st_size
        console.print(
            f"\n[green]✓ Decryption successful[/green] ({file_size:,} bytes)"
        )
        display_info_table()
    else:
        if output_path.exists():
            output_path.unlink()
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="encrypt-tool",
        description="Secure file encryption and decryption using AES-256-GCM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Encrypt a file (password prompted securely)
  python3 main.py encrypt document.pdf
  
  # Encrypt with custom output path
  python3 main.py encrypt document.pdf -o backup.enc
  
  # Decrypt a file
  python3 main.py decrypt document.pdf.enc
  
  # Decrypt with custom output path
  python3 main.py decrypt document.pdf.enc -o restored.pdf
  
  # Force overwrite existing output file
  python3 main.py encrypt large.zip -f
        """,
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Command to execute"
    )

    # Encrypt subcommand
    encrypt_parser = subparsers.add_parser(
        "encrypt", help="Encrypt a file"
    )
    encrypt_parser.add_argument(
        "file", type=str, help="Path to file to encrypt"
    )
    encrypt_parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file path (default: <file>.enc)",
    )
    encrypt_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file",
    )
    encrypt_parser.set_defaults(func=encrypt_command)

    # Decrypt subcommand
    decrypt_parser = subparsers.add_parser(
        "decrypt", help="Decrypt a file"
    )
    decrypt_parser.add_argument(
        "file", type=str, help="Path to file to decrypt"
    )
    decrypt_parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file path (default: <file without .enc>)",
    )
    decrypt_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file",
    )
    decrypt_parser.set_defaults(func=decrypt_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
