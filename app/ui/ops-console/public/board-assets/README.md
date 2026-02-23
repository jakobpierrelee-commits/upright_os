Board asset mirror cache for Setup pin-guide references.

Populate/update with:

`tools/sync_board_assets.sh`

Expected structure:

- `board-id/docs.html`
- `board-id/pinout.pdf` (when available)
- `board-id/schematic.pdf` (when available)
- `board-id/cad.zip` (when available)

The Setup UI prefers local mirrored paths first, then remote vendor links.
