# True Value of Video Games — test build

Runs every Steam game through the frozen v0.1 formula once a day and
publishes a searchable page. No servers, no cost, no AI running in the loop.

## How it works

Every day at 2am Central, GitHub runs a script that:

1. Downloads the full Steam catalog from SteamSpy: user reviews and playtime
   for every game (about 1–2 hours, SteamSpy only allows one page per minute).
2. Looks up critic scores from the Steam store for games it hasn't checked yet,
   most-reviewed first (3 hours per day; Steam only allows ~200 lookups per
   5 minutes, so the full catalog takes about two weeks to fill in, then it's
   quick after that).
3. Runs every game through the formula in `tvvg/formula.py`.
4. Saves the results. Your search page updates automatically.

## One-time setup (about 20 minutes, all in your browser)

1. **Make a GitHub account** at github.com (free).
2. **Create a repository.** Click the + in the top right → *New repository*.
   Name it `tvvg`. Choose **Public** (required for the free page and free
   daily runs; nobody will find it unless you share the link). Click *Create*.
3. **Upload the files.** On the new repo page click *uploading an existing
   file*, drag in everything from this folder, click *Commit changes*.
   - The `.github` folder is often hidden and may not upload. If
     `.github/workflows/daily.yml` doesn't appear in the repo afterwards:
     click *Add file → Create new file*, type the name
     `.github/workflows/daily.yml` (slashes create the folders), paste in
     the contents of that file, and commit.
4. **Turn on the page.** *Settings → Pages*. Under *Branch*, pick `main`
   and folder `/docs`, click *Save*. Your page will be at
   `https://YOUR-USERNAME.github.io/tvvg/`.
5. **Do a 5-minute test run.** *Actions* tab → *Daily True Value update* →
   *Run workflow*. Set pages to `2` and critic minutes to `3`, then run.
   A green check means it worked; open your page and search.
6. **Do the real run.** Run it again with pages **blank** and critic minutes
   `180`. This is the full Steam catalog, and takes 4–5 hours. After that
   it runs itself every day.

## Reading the results

- **Notes column:** `critic not checked yet` goes away as critic lookups fill
  in over the first two weeks. `no critic score` means the game has no
  Metacritic score. `low reviews` means fewer than 50 Steam reviews.
- **Spreadsheet:** `docs/games.csv` in the repo has every game. Click it →
  *Download raw file* to open in Excel and sort however you like.
- Games with no playtime data aren't scored at all (they can't be; H would
  be zero).

## Data decisions you can change

These live at the top of `tvvg/build.py`. They affect the **inputs**, not
the formula.

| Setting | Current | What it means |
|---|---|---|
| `H_SOURCE` | `median` | H = median hours Steam owners have played. `average` is the alternative. |
| `MISSING_CRITIC_RULE` | `use_user` | No critic score → use the user % in its place. `skip` = don't score those games. |
| `LOW_REVIEW_FLAG` | `50` | Review count below which a game is flagged. |

## Data sources

- SteamSpy (steamspy.com/api.php): public, no key.
- Steam Store appdetails (store.steampowered.com/api/appdetails): public,
  no key. Critic scores are Metacritic's, as shown on Steam.

Credit both on the page before going public.
