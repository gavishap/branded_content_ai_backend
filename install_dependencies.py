import sys
import subprocess
import platform

def install_dependencies():
    """Install dependencies based on Python version."""
    print("Detecting Python version...")
    print(f"Python version: {sys.version}")
    python_version = float(f"{sys.version_info.major}.{sys.version_info.minor}")
    
    print(f"Python version: {python_version}")
    
    # First, ensure pip is up to date
    print("Updating pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    
    # Install critical packages first to ensure they're correctly installed
    print("Installing critical packages first...")
    critical_packages = [
        "google-generativeai==0.3.1",
        "clarifai-grpc==9.8.1"
    ]
    
    for package in critical_packages:
        print(f"Installing critical package: {package}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        except subprocess.CalledProcessError:
            # If failed with version constraint, try without version
            print(f"Failed to install {package} with version constraint. Trying without version...")
            package_name = package.split("==")[0]
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    
    # Create requirements based on Python version
    if python_version >= 3.12:
        print("Using dependencies compatible with Python 3.12+")
        requirements = [
            "Flask==2.2.3",
            "flask-cors==3.0.10",
            "python-dotenv==1.0.0",
            "yt-dlp==2023.10.13",
            "boto3==1.28.53",
            "requests==2.31.0",
            "numpy==1.26.0",
            "pillow==10.0.0",
            "matplotlib==3.8.0",
            "pandas==2.0.3"
        ]
    else:
        print("Using dependencies compatible with Python 3.8-3.11")
        requirements = [
            "Flask==2.2.3",
            "flask-cors==3.0.10",
            "python-dotenv==1.0.0",
            "yt-dlp==2023.10.13",
            "boto3==1.28.53",
            "requests==2.31.0",
            "numpy==1.24.2",
            "pillow==9.4.0",
            "matplotlib==3.7.1",
            "pandas==1.5.3"
        ]
    
    # Install dependencies one by one
    print("Installing dependencies...")
    for req in requirements:
        print(f"Installing {req}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", req])
        except subprocess.CalledProcessError:
            # If failed with version constraint, try without version
            print(f"Failed to install {req} with version constraint. Trying without version...")
            package_name = req.split("==")[0]
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    
    # Verify critical packages
    print("\nVerifying critical packages...")
    try:
        subprocess.check_call([sys.executable, "-c", "import google.generativeai; print('Google Generative AI package successfully imported')"])
    except subprocess.CalledProcessError:
        print("WARNING: Google Generative AI package not properly installed. Attempting reinstallation...")
        subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "google-generativeai"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-generativeai"])
    
    try:
        subprocess.check_call([sys.executable, "-c", "import clarifai_grpc; print('Clarifai gRPC package successfully imported')"])
    except subprocess.CalledProcessError:
        print("WARNING: Clarifai gRPC package not properly installed. Attempting reinstallation...")
        subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "clarifai-grpc"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "clarifai-grpc"])
    
    print("\nDependencies installation complete!")

if __name__ == "__main__":
    install_dependencies() 
