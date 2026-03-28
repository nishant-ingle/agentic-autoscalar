#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

PROJECT_NAME="pka-autoscaler"

echo "🚀 Scaffolding $PROJECT_NAME monorepo..."

# 1. Create the root directory and navigate into it
mkdir -p $PROJECT_NAME
cd $PROJECT_NAME

# 2. Create Root level files and .github directory
mkdir -p .github/workflows
touch README.md Makefile

# 3. Create the Go Controller (Infrastructure)
echo "🏗️ Setting up the Go Controller..."
mkdir -p controller/api
mkdir -p controller/cmd
mkdir -p controller/config
mkdir -p controller/internal/controller
mkdir -p controller/internal/client

touch controller/Dockerfile
touch controller/go.mod
touch controller/go.sum

# 4. Create the Python Inference Engine (AI/ML)
echo "🧠 Setting up the Python Inference Engine..."
mkdir -p inference-engine/app/api
mkdir -p inference-engine/app/ml
mkdir -p inference-engine/app/core
mkdir -p inference-engine/tests

touch inference-engine/app/__init__.py
touch inference-engine/app/main.py
touch inference-engine/Dockerfile
touch inference-engine/requirements.txt

# 5. Create the Deployment manifests directory
echo "🚀 Setting up Deployment directories..."
mkdir -p deploy/helm
mkdir -p deploy/prometheus

# 6. Create the Hack directory for local scripts
echo "🛠️ Setting up Hack directory..."
mkdir -p hack
touch hack/setup-k3d.sh

# Make the local dev script executable
chmod +x hack/setup-k3d.sh
# Add a basic bash header to the setup script
echo "#!/bin/bash" > hack/setup-k3d.sh
echo 'echo "Starting K3D cluster..."' >> hack/setup-k3d.sh

echo "✅ Scaffolding complete! Your project structure is ready."
echo "➡️  Run 'cd $PROJECT_NAME' to get started."
