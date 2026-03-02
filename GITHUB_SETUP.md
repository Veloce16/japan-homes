# GitHub Setup Guide — Japan Home Search

Follow these steps once to get the scraper running automatically in the cloud,
with the dashboard available from any device (phone, tablet, etc.).

---

## Step 1 — Create a GitHub Account (if you don't have one)

1. Go to https://github.com
2. Click **Sign up**
3. Use username **Veloce16** (or whatever is available)
4. Verify your email address

If you already have an account, just sign in.

---

## Step 2 — Create a New Private Repository

1. Click the **+** icon (top-right) → **New repository**
2. Fill in:
   - **Repository name:** `japan-homes`
   - **Visibility:** Private *(your listings are private — only you can see them)*
   - Leave "Add a README" unchecked
3. Click **Create repository**
4. You'll land on an empty repo page — leave it open

---

## Step 3 — Upload All Project Files

The easiest way is the GitHub web interface:

1. On your new repo page, click **uploading an existing file** (or drag-and-drop)
2. Drag in the entire `japan_realestate` folder contents:
   - `scraper.py`
   - `config.json`
   - `requirements.txt`
   - `docs/` folder (contains `index.html`)
   - `.github/` folder (contains `workflows/scrape.yml`)
3. Scroll down, click **Commit changes**

> **Tip:** If drag-and-drop doesn't show `.github/` (hidden folder), use GitHub Desktop
> or the GitHub CLI (`gh repo clone ...` then copy files and `git push`).

---

## Step 4 — Add Your Gmail App Password as a Secret

The scraper uses a Gmail App Password to send emails. We store it securely as a
GitHub Secret (never visible in your code).

1. In your repo, click **Settings** (top nav)
2. Left sidebar → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name:  `GMAIL_APP_PASSWORD`
5. Value: your Gmail App Password (the 16-character code from Google Account settings)
6. Click **Add secret**

> **Don't have a Gmail App Password yet?**
> - Go to https://myaccount.google.com/security
> - Enable 2-Step Verification (required)
> - Search for "App passwords"
> - Create one named "Japan Scraper" — copy the 16-character code

---

## Step 5 — Enable GitHub Pages (your dashboard URL)

1. In your repo, click **Settings**
2. Left sidebar → **Pages**
3. Under **Source**, select **Deploy from a branch**
4. Branch: `main` | Folder: `/docs`
5. Click **Save**

After ~2 minutes your dashboard will be live at:
**https://Veloce16.github.io/japan-homes**

---

## Step 6 — Run the Scraper Manually (First Test)

1. In your repo, click the **Actions** tab
2. Left sidebar → **Scrape Japan Real Estate**
3. Click **Run workflow** → **Run workflow** (green button)
4. Watch the progress — it takes about 5-10 minutes

When it finishes:
- `docs/listings.json` is committed to your repo
- Your dashboard at https://Veloce16.github.io/japan-homes shows listings
- You receive an email with the Fuji banner

---

## Step 7 — Set Up the Dashboard "Search Now" Button

The **Search Now** button in the dashboard calls the GitHub API to trigger a
new scrape manually from your phone.

1. Go to https://github.com/settings/tokens/new
2. Name: `Japan Homes Dashboard`
3. Expiration: No expiration (or 1 year)
4. Scopes: check **workflow** (under repo section)
5. Click **Generate token** — copy it immediately (you only see it once)
6. Open your dashboard → click **Search Now**
7. When the modal appears, enter:
   - GitHub Owner: `Veloce16`
   - Repo name: `japan-homes`
   - Token: (paste your token)
8. Click Save — it's stored in your browser for next time

---

## Automatic Schedule

The scraper runs automatically at:
- **12:00 AM, 6:00 AM, 12:00 PM, 6:00 PM UTC**
- (= 9 AM, 3 PM, 9 PM, 3 AM Japan Standard Time / JST)

You'll get an email each time new listings are found.
If nothing new is found, no email is sent.

---

## Dashboard URL

**https://Veloce16.github.io/japan-homes**

Bookmark this on your phone! Works on any browser, any device.
