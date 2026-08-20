Gitty is lightweight content addressable version control system. the idea is inspired straight from Git, i wanted to know how Git works under the hood so i built a simpler version of it.
Gitty has all the basic commands of Git. 


https://github.com/user-attachments/assets/4defb3df-544c-4918-8198-a718369f8b0e


Installation:
Option 1: Standalone Binary (Windows)

Download gitty.exe from the latest GitHub Release in <a href="https://github.com/srinick007/gitty/releases/tag/alpha_release"> GitHub Release</a>.

Add the executable directory to your system PATH, or run directly from your terminal:

```
.\gitty.exe 
```

Option 2: Run from Source
Clone this repository:

```
git clone https://github.com/your-username/gitty.git
cd gitty
Create a virtual environment and install dependencies:
```

```
python -m venv venv
source venv/bin/activate 
pip install -r requirements.txt
```

CLI Usage Guide
1. Configuration
Set your author details:

```
gitty config --global user.name "YourName"
```

2. Initialize a Repository
```
gitty init
echo "Hello from Gitty" > README.md
gitty add .
gitty commit "Initial commit"
```

4. Remote Tracking & Push
Connect to a remote repository on the live cloud backend:

```
gitty remote add origin YourName/my-project
gitty push -u origin main
```
4. Branching & Checking Out

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

```
gitty clone YourName/my-project
cd my-project
gitty branch
```

for help
```
gitty -h
```
<img width="720" height="640" alt="Screenshot 2026-08-20 113430" src="https://github.com/user-attachments/assets/94fd9e42-7850-4161-b3ba-926dffcaeb6b" />
