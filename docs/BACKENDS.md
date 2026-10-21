# Backends

A backend is where the imagery comes from. You choose it in the Imagery section; all three give the same 14-layer chip, so every view, fill and statistic works with any of them.

| Backend | Needs | Real imagery | Notes |
|---|---|---|---|
| `demo` | nothing | no (synthetic, always labelled) | Works offline. For learning the tool and for tests. |
| `pc` | internet | yes | Microsoft Planetary Computer, public STAC API, no account. The tool asks for a short-lived read token itself. |
| `ee` | an Earth Engine account and project | yes | Your own account. The tool never stores your key. |

## Planetary Computer

Nothing to set up. The tool searches Sentinel-2 L2A scenes over the box, picks the least cloudy, reads the bands over HTTPS and, for the cloudless median and clear-sky sources, combines several scenes. The approach (STAC search, then a median of clear observations) follows the open-source `solafune-tools` package by Solafune Inc. (MIT licence). TrigPoint does not import that package.

Check the Planetary Computer terms of use before heavy use. Large boxes with many scenes download a lot of data; start with a single scene.

## Earth Engine: setting it up, step by step

Earth Engine is optional. Without it, the Demo and Planetary Computer backends still work. Google changes its screens from time to time, so if a step does not match what you see, follow Google's own Earth Engine guide (search for "Earth Engine access" and "Earth Engine service account").

You need a Google account and a Google Cloud project that is registered for Earth Engine. Registration is free for research and other non-commercial use; commercial use needs a paid plan, and this tool's licence does not allow commercial use anyway.

### Easiest way: sign in as yourself (no key file)

1. Install the library: `pip install earthengine-api`
2. Sign in once: `earthengine authenticate` (a browser window opens; approve access).
3. Tell the tool which project to use. Your project id is on the Google Cloud console home page.
   * Windows PowerShell: `$env:EE_PROJECT = "your-project-id"`
   * macOS or Linux: `export EE_PROJECT=your-project-id`
4. Start the tool (`python server.py`), open the Imagery section, choose Earth Engine, and press Check the connection.

### For unattended or shared use: a service-account key file

1. In the Google Cloud console, open your project, then IAM and Admin, then Service accounts, and create a service account.
2. Make sure the Earth Engine API is enabled for the project and the project is registered for Earth Engine.
3. Register the service account's email address with Earth Engine (Google's guide calls this "registering a service account"), and give it permission to use Earth Engine in the project (the role "Earth Engine Resource Viewer", plus "Service Usage Consumer", is usually enough for reading).
4. On the service account, choose Keys, then Add key, then JSON. A file downloads. **This file is a password.** Keep it outside this folder, never send it to anyone and never publish it.
5. Point the tool at it:
   * Windows PowerShell: `$env:EE_SERVICE_ACCOUNT_KEY_FILE = "C:\keys\my-key.json"`
   * macOS or Linux: `export EE_SERVICE_ACCOUNT_KEY_FILE=/home/you/keys/my-key.json`
   * The project id is read from the key file. Set `EE_PROJECT` only if it does not name one.
   * Or put the key text in `EE_SERVICE_ACCOUNT_JSON` (useful in a container secret).
6. Start the tool and press Check the connection in the Imagery section.

### If it does not work

| What you see | What to try |
|---|---|
| "Earth Engine is not set up (no credentials)" | You have not signed in or set the key variable in the window that starts the tool. Variables set in one terminal window do not reach another. |
| "Not signed up to Earth Engine" or "project is not registered" | Register the project for Earth Engine in the Google Cloud console. |
| "Permission denied" or "caller does not have permission" | The service account is not registered with Earth Engine, or lacks the roles in step 3. |
| "Quota" or "too many requests" | Wait a few minutes; fetch one site at a time. |
| Everything else | Run `python -c "import ee; ee.Initialize(project='your-project-id'); print(ee.Number(1).getInfo())"`. If that fails, the problem is the account setup, not the tool. |

The tool never stores or sends your key anywhere except to Google through the Earth Engine library. Keep key files out of anything you publish; `secrets/` is in `.gitignore`.

If Earth Engine is not ready, the Imagery section says so in plain words and the other backends keep working.

## What has and has not been tested

The Earth Engine and Planetary Computer code is covered by automated tests that use stand-ins (a recording stub and fake HTTP responses).

Both were also run live on 18 to 21 October 2026.

* **Earth Engine** (a service account): six sites as single scenes, a cloudless median and a clear-sky layer for two cloudy sites, and the gap-fill test; later the placement study on ten sites with four Sentinel-5P products. Every fetch worked, 6 to 31 seconds each for the imagery.
* **Planetary Computer** (no account): two sites as single scenes (24 to 36 seconds) and one cloudless median of 12 scenes (about 3.5 minutes), 13 MB in all, with views and statistics. Every fetch worked. A median over many scenes is slow on this backend because each scene is read over the internet; start with a single scene. The first connection check once timed out although the fetch itself then worked, so the check now waits longer and tries twice.

Not tested: Docker, a second operating system, and the Earth Engine key-creation steps above (they follow Google's documentation but were not clicked through here). Please report anything that behaves differently on your setup.
