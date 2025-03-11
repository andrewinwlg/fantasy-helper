#!/usr/bin/env python3
"""
Script to automatically update ChromeDriver to match the installed Chrome version.
"""

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen, urlretrieve

def get_chrome_version():
    """Get the installed Chrome version."""
    system = platform.system()
    
    try:
        if system == "Linux":
            # Try different commands for Linux
            commands = [
                ["google-chrome", "--version"],
                ["google-chrome-stable", "--version"],
                ["chromium-browser", "--version"],
                ["chromium", "--version"]
            ]
            
            for cmd in commands:
                try:
                    version = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
                    match = re.search(r'(\d+\.\d+\.\d+)', version)
                    if match:
                        return match.group(1)
                except (subprocess.SubprocessError, FileNotFoundError):
                    continue
                    
        elif system == "Darwin":  # macOS
            try:
                process = subprocess.Popen(
                    ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                version = process.communicate()[0].decode('UTF-8').strip()
                match = re.search(r'(\d+\.\d+\.\d+)', version)
                if match:
                    return match.group(1)
            except (subprocess.SubprocessError, FileNotFoundError):
                pass
                
        elif system == "Windows":
            try:
                # Method 1: Using registry
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                version, _ = winreg.QueryValueEx(key, "version")
                return version
            except:
                # Method 2: Using PowerShell
                try:
                    cmd = r'(Get-Item -Path "$env:PROGRAMFILES\Google\Chrome\Application\chrome.exe").VersionInfo.FileVersion'
                    version = subprocess.check_output(['powershell', '-command', cmd], stderr=subprocess.STDOUT).decode('utf-8').strip()
                    return version
                except:
                    # Method 3: Using Program Files (x86)
                    try:
                        cmd = r'(Get-Item -Path "$env:PROGRAMFILES(x86)\Google\Chrome\Application\chrome.exe").VersionInfo.FileVersion'
                        version = subprocess.check_output(['powershell', '-command', cmd], stderr=subprocess.STDOUT).decode('utf-8').strip()
                        return version
                    except:
                        pass
    except Exception as e:
        print(f"Error detecting Chrome version: {e}")
    
    return None

def get_chromedriver_version():
    """Get the installed ChromeDriver version."""
    try:
        output = subprocess.check_output(['chromedriver', '--version']).decode('utf-8')
        match = re.search(r'ChromeDriver (\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
    except:
        pass
    return None

def get_matching_chromedriver_version(chrome_version):
    """Get the matching ChromeDriver version for the given Chrome version."""
    # Extract major version
    major_version = chrome_version.split('.')[0]
    
    # For Chrome >= 115, we need to use the new API
    if int(major_version) >= 115:
        # Try the known-good-versions-with-downloads.json API to find exact match
        try:
            print(f"Looking for ChromeDriver version that matches Chrome {chrome_version}...")
            url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
            with urlopen(url) as response:
                data = response.read().decode('utf-8')
                import json
                versions = json.loads(data)
                
                if 'versions' in versions:
                    # Find versions that match the major version
                    matching_versions = [v for v in versions['versions'] 
                                       if v['version'].startswith(f"{major_version}.")]
                    
                    if matching_versions:
                        # Sort by version number
                        matching_versions.sort(key=lambda x: [int(n) for n in x['version'].split('.')])
                        
                        # Find the closest version without going over
                        chrome_version_parts = [int(n) for n in chrome_version.split('.')]
                        
                        closest_version = None
                        for v in matching_versions:
                            v_parts = [int(n) for n in v['version'].split('.')]
                            
                            # Check if this version is less than or equal to the Chrome version
                            if all(a <= b for a, b in zip(v_parts, chrome_version_parts)):
                                closest_version = v['version']
                        
                        if closest_version:
                            print(f"Found matching ChromeDriver version: {closest_version}")
                            return closest_version
                        
                        # If no version is less than or equal, take the lowest available version
                        lowest_version = matching_versions[0]['version']
                        print(f"No exact match found. Using lowest available version: {lowest_version}")
                        return lowest_version
        except Exception as e:
            print(f"Error finding exact match: {e}")
    
    # Try to get the latest version for the major version
    try:
        url = f"https://chromedriver.storage.googleapis.com/LATEST_RELEASE_{major_version}"
        with urlopen(url) as response:
            version = response.read().decode('utf-8').strip()
            print(f"Found version for Chrome {major_version}: {version}")
            return version
    except Exception as e:
        print(f"Error with major version API: {e}")
    
    # If all else fails, try to get the latest version for a known good major version
    # Try versions in descending order, but not higher than the current Chrome version
    int_major = int(major_version)
    fallback_versions = [str(v) for v in range(int_major, int_major-10, -1) if v > 0]
    
    for fallback_version in fallback_versions:
        try:
            print(f"Trying fallback to Chrome {fallback_version}...")
            url = f"https://chromedriver.storage.googleapis.com/LATEST_RELEASE_{fallback_version}"
            with urlopen(url) as response:
                version = response.read().decode('utf-8').strip()
                print(f"Found fallback version: {version}")
                return version
        except Exception:
            continue
    
    print(f"Could not find ChromeDriver version for Chrome {chrome_version}")
    return None

def download_chromedriver(version):
    """Download ChromeDriver for the given version."""
    system = platform.system()
    if system == "Linux":
        platform_name = "linux64"
    elif system == "Darwin":  # macOS
        if platform.machine() == "arm64":  # Apple Silicon
            platform_name = "mac_arm64"
        else:
            platform_name = "mac64"
    elif system == "Windows":
        platform_name = "win32"
    else:
        print(f"Unsupported platform: {system}")
        return None
    
    # For Chrome >= 115, use the new download URL format
    major_version = version.split('.')[0]
    if int(major_version) >= 115:
        url = f"https://storage.googleapis.com/chrome-for-testing-public/{version}/{platform_name}/chromedriver-{platform_name}.zip"
    else:
        url = f"https://chromedriver.storage.googleapis.com/{version}/chromedriver_{platform_name}.zip"
    
    print(f"Downloading ChromeDriver {version} from {url}")
    
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "chromedriver.zip")
    
    try:
        # Download the file
        urlretrieve(url, zip_path)
        
        # Extract the zip file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the chromedriver executable
        if int(major_version) >= 115:
            # New structure has a subdirectory
            chromedriver_path = os.path.join(temp_dir, f"chromedriver-{platform_name}", "chromedriver")
            if system == "Windows":
                chromedriver_path += ".exe"
        else:
            # Old structure has chromedriver directly in the zip
            chromedriver_path = os.path.join(temp_dir, "chromedriver")
            if system == "Windows":
                chromedriver_path += ".exe"
        
        if not os.path.exists(chromedriver_path):
            # Try to find it
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file == "chromedriver" or file == "chromedriver.exe":
                        chromedriver_path = os.path.join(root, file)
                        break
        
        return chromedriver_path
    except Exception as e:
        print(f"Error downloading ChromeDriver: {e}")
        return None
    finally:
        # Clean up the zip file
        if os.path.exists(zip_path):
            os.remove(zip_path)

def install_chromedriver(chromedriver_path):
    """Install ChromeDriver to the appropriate location."""
    system = platform.system()
    
    if system == "Linux" or system == "Darwin":  # Linux or macOS
        # Find a directory in PATH
        paths = os.environ["PATH"].split(os.pathsep)
        install_dir = None
        
        for path in paths:
            if os.access(path, os.W_OK) and os.path.isdir(path):
                install_dir = path
                break
        
        if not install_dir:
            # Use /usr/local/bin if available
            if os.path.isdir("/usr/local/bin") and os.access("/usr/local/bin", os.W_OK):
                install_dir = "/usr/local/bin"
            else:
                # Use home directory
                install_dir = os.path.expanduser("~/.local/bin")
                os.makedirs(install_dir, exist_ok=True)
                
                # Add to PATH if not already there
                if install_dir not in paths:
                    print(f"Adding {install_dir} to PATH")
                    with open(os.path.expanduser("~/.bashrc"), "a") as f:
                        f.write(f'\nexport PATH="$PATH:{install_dir}"\n')
                    print("Please restart your shell or run 'source ~/.bashrc'")
        
        # Copy the file
        dest_path = os.path.join(install_dir, "chromedriver")
        shutil.copy2(chromedriver_path, dest_path)
        
        # Make it executable
        os.chmod(dest_path, 0o755)
        
        print(f"Installed ChromeDriver to {dest_path}")
        return dest_path
        
    elif system == "Windows":
        # Find a directory in PATH
        paths = os.environ["PATH"].split(os.pathsep)
        install_dir = None
        
        for path in paths:
            if os.access(path, os.W_OK) and os.path.isdir(path):
                install_dir = path
                break
        
        if not install_dir:
            # Use Python Scripts directory
            install_dir = os.path.join(sys.exec_prefix, "Scripts")
            os.makedirs(install_dir, exist_ok=True)
        
        # Copy the file
        dest_path = os.path.join(install_dir, "chromedriver.exe")
        shutil.copy2(chromedriver_path, dest_path)
        
        print(f"Installed ChromeDriver to {dest_path}")
        return dest_path
    
    else:
        print(f"Unsupported platform: {system}")
        return None

def main():
    """Main function."""
    print("ChromeDriver Update Utility")
    print("==========================")
    
    # Get Chrome version
    chrome_version = get_chrome_version()
    if not chrome_version:
        print("Error: Could not detect Chrome version")
        return 1
    
    print(f"Detected Chrome version: {chrome_version}")
    
    # Get current ChromeDriver version
    current_driver_version = get_chromedriver_version()
    if current_driver_version:
        print(f"Current ChromeDriver version: {current_driver_version}")
    else:
        print("ChromeDriver not found or not in PATH")
    
    # Get matching ChromeDriver version
    driver_version = get_matching_chromedriver_version(chrome_version)
    if not driver_version:
        print("Error: Could not determine matching ChromeDriver version")
        return 1
    
    print(f"Matching ChromeDriver version: {driver_version}")
    
    # Check if update is needed
    if current_driver_version == driver_version:
        print("ChromeDriver is already up to date")
        return 0
    
    # Ask for confirmation
    print("\nReady to download and install ChromeDriver")
    response = input("Do you want to continue? (y/n): ").strip().lower()
    if response != 'y':
        print("Update cancelled")
        return 0
    
    # Download ChromeDriver
    chromedriver_path = download_chromedriver(driver_version)
    if not chromedriver_path:
        print("Error: Failed to download ChromeDriver")
        return 1
    
    # Install ChromeDriver
    install_path = install_chromedriver(chromedriver_path)
    if not install_path:
        print("Error: Failed to install ChromeDriver")
        return 1
    
    print("\nChromium Driver has been successfully updated!")
    print(f"Version: {driver_version}")
    print(f"Location: {install_path}")
    
    # Clean up
    shutil.rmtree(os.path.dirname(chromedriver_path), ignore_errors=True)
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 