#!/bin/bash

# Ensure pyenv is initialized
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

# Desired Python version
PYTHON_VERSION="3.11.0"

# Name of the virtual environment folder
VENV_NAME="venv"

echo "🔎 Checking Python $PYTHON_VERSION is installed with pyenv..."
if ! pyenv versions | grep -q "$PYTHON_VERSION"; then
    echo "❌ Python $PYTHON_VERSION is not installed. Installing now..."
    env \
      LDFLAGS="-L$(brew --prefix openssl@3)/lib" \
      CPPFLAGS="-I$(brew --prefix openssl@3)/include" \
      PKG_CONFIG_PATH="$(brew --prefix openssl@3)/lib/pkgconfig" \
      PYTHON_CONFIGURE_OPTS="--with-openssl=$(brew --prefix openssl@3)" \
      pyenv install $PYTHON_VERSION
else
    echo "✅ Python $PYTHON_VERSION is already installed."
fi

# Set pyenv global version
pyenv global $PYTHON_VERSION
echo "✅ Using Python $(python --version)"

# Remove old virtual environment
if [ -d "$VENV_NAME" ]; then
    echo "🧹 Removing old virtual environment: $VENV_NAME"
    rm -rf $VENV_NAME
fi

# Create new virtual environment
echo "📦 Creating new virtual environment using Python $PYTHON_VERSION..."
python -m venv $VENV_NAME

# Activate and install basic packages
source $VENV_NAME/bin/activate
echo "🚀 Virtual environment activated."
pip install --upgrade pip
pip install pandas requests

echo "✅ Setup complete. Python version in venv: $(python --version)"
echo "To run script, do: "
echo "chmod +x setup_venv.sh   # make it executable"
echo "./setup_venv.sh"
echo "To activate it, do: "
echo "source ./venv/bin/activate"
echo " To deactivate it, do: "
echo "deactivate"
echo "To show a specific tool is installed, do: "
echo "pip show numpy"

