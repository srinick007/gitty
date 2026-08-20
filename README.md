Gitty is lightweight content addressable version control system. the idea is inspired straight from Git, i wanted to know how Git works under the hood so i built a simpler version of it.
Gitty has all the basic commands of Git. 

Installation:
Option 1: Standalone Binary (Windows)

Download gitty.exe from the latest GitHub Release.

Add the executable directory to your system PATH, or run directly from your terminal:

PowerShell
```
.\gitty.exe version
```

Option 2: Run from Source
Clone this repository:

Bash
```
git clone https://github.com/your-username/gitty.git
cd gitty
Create a virtual environment and install dependencies:
```

Bash
```
python -m venv venv
source venv/bin/activate 
pip install -r requirements.txt
```

CLI Usage Guide
1. Configuration
Set your author details:

Bash
```
gitty config --global user.name "YourName"
```

2. Initialize a Repository
Bash
```
gitty init
echo "Hello from Gitty" > README.md
gitty add .
gitty commit "Initial commit"
```

4. Remote Tracking & Push
Connect to a remote repository on the live cloud backend:

Bash
```
gitty remote add origin YourName/my-project
gitty push -u origin main
```
4. Branching & Checking Out

Bash
```
gitty branch feature-api
gitty checkout feature-api
echo "new feature" > feature.py
gitty add .
gitty commit "Add feature module"
gitty push origin feature-api
```
5. Clone a Live Repository
Clone any public repository hosted on the live cluster:

Bash
```
gitty clone YourName/my-project
cd my-project
gitty branch
```
