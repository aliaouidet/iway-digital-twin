# Get the directory where this script is located
$basePath = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "Creating project structure in: $basePath"

# List of folders to create
$folders = @(
    "iway-chatbot",
    "iway-chatbot/backend",
    "iway-chatbot/backend/app",
    "iway-chatbot/backend/app/api",
    "iway-chatbot/backend/app/core",
    "iway-chatbot/backend/app/models",
    "iway-chatbot/ai_engine",
    "iway-chatbot/ai_engine/data",
    "iway-chatbot/frontend",
    "iway-chatbot/qdrant_storage"
)

# Create folders
foreach ($folder in $folders) {
    $fullPath = Join-Path $basePath $folder
    if (!(Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath | Out-Null
        Write-Host "Created folder: $folder"
    } else {
        Write-Host "Folder already exists: $folder"
    }
}

# Create empty files
$files = @(
    "iway-chatbot/.env",
    "iway-chatbot/docker-compose.yml",
    "iway-chatbot/README.md",
    "iway-chatbot/backend/Dockerfile",
    "iway-chatbot/backend/requirements.txt",
    "iway-chatbot/backend/main.py",
    "iway-chatbot/backend/database.py",
    "iway-chatbot/ai_engine/Dockerfile",
    "iway-chatbot/ai_engine/agent.py",
    "iway-chatbot/ai_engine/rag_engine.py",
    "iway-chatbot/ai_engine/bot_tools.py",
    "iway-chatbot/ai_engine/requirements.txt",
    "iway-chatbot/frontend/Dockerfile",
    "iway-chatbot/frontend/chat_ui.py",
    "iway-chatbot/frontend/requirements.txt"
)

foreach ($file in $files) {
    $filePath = Join-Path $basePath $file
    if (!(Test-Path $filePath)) {
        New-Item -ItemType File -Path $filePath | Out-Null
        Write-Host "Created file: $file"
    } else {
        Write-Host "File already exists: $file"
    }
}

Write-Host "🎉 Project structure created successfully!"