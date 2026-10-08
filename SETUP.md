# Setting up your profile card

## 1. Create the profile repo
On GitHub, create a **public** repo with exactly the same name as your username
(e.g. `octocat/octocat`). GitHub shows its `README.md` on your profile page.

## 2. Upload these files
Upload everything in this folder, including the hidden `.github` folder.
(If you drag and drop in the browser and `.github` doesn't come along, create
`.github/workflows/update-card.yml` with **Add file → Create new file** and paste it in.)

## 3. Fill in your details
- **`profile.json`**: set `username`, `title`, `birthday` (used for Uptime) and
  edit the `card` lines:
  - `["Key", "value"]` is a normal row. Use dots in keys for the two-tone look:
    `"Languages.Programming"`.
  - `""` is a blank spacer line.
  - `"# Contact"` starts a new section.
  - `"@stats"` is the GitHub Stats block.
  - `{uptime}` inside a value is replaced with your age.
  - `width` is the info column width in characters. Raise it if a value is too long.
- **`README.md`**: replace `your-github-username` in the link.

## 4. (Optional) Include private repos in the stats
Create a token at **Settings → Developer settings → Personal access tokens**:
- **Fine-grained token**: grant read-only *Contents* and *Metadata* on *All repositories*.
  This covers repos you own.
- **Classic token** with the `repo` and `read:user` scopes: also covers org repos and
  repos where you're a collaborator.

Then add it in your profile repo under **Settings → Secrets and
variables → Actions → New repository secret**, named `PROFILE_TOKEN`.
Without it, the stats count public repos only.

## 5. Run it
In the repo, open **Actions → Update profile card → Run workflow**. After
that it runs every day on its own, and whenever you edit `profile.json`.
The first run can take a few minutes, because it counts lines of code across
all your commits. Later runs only recount repos with new commits.

## Changing your ASCII art
Replace `ascii.txt` with new art (any size). In `profile.json`, set
`art.background` to the character used for the background (`"+"` here). It gets
blanked out around your face, but the same character inside the drawing is kept.
Set it to `""` to keep the art exactly as it is. The art is scaled to match the
height of the info column automatically.

Preview locally with `python scripts/generate.py --offline`.
