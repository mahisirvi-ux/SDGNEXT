# UI Design Tokens — SDGNext

Defined in `js/tailwind-config.js`. Available as Tailwind utility classes everywhere.

## Colors

| Token | Hex | Tailwind | Usage |
|---|---|---|---|
| shell | #1a233a | bg-shell, text-shell | App-shell header background |
| shell-muted | #94a3b8 | text-shell-muted | Muted text on dark backgrounds |
| primary | #ec4899 | bg-primary, text-primary | Commit actions (Edit, Save, Create Project) |
| primary-hover | #db2777 | hover:bg-primary-hover | Hover state for primary |
| secondary | #6366f1 | bg-secondary | Discovery / navigation (Add, Open) |
| secondary-hover | #4f46e5 | hover:bg-secondary-hover | Hover state for secondary |
| success | #10b981 | bg-success | Confirmation states (Save successful) |
| danger | #ef4444 | bg-danger | Destructive / overdue states |

## Header pattern

Every top-level page uses the same header:

- `bg-shell text-white` background
- `py-4 px-6` padding (or `py-3 px-6` for details.html's compact variant)
- Wordmark: `text-lg font-bold` with pink "NEXT"
- Action buttons on the header use the
  `bg-white/10 border-white/20 hover:bg-white/20` pattern
  (NOT bg-primary or bg-secondary, which are for body content)

## Modal sizes

Three sizes only:

- `w-[400px]` — sm, single-field forms
- `w-[520px]` — md, typical forms
- `w-[700px]` — lg, complex multi-column forms

Avoid arbitrary widths. If a modal doesn't fit any of these, redesign
its content rather than introducing a fourth size.

## Button color semantics (codified)

| Color | When to use | Example |
|---|---|---|
| primary (pink) | Commits/important | Edit Details, Create Project, Send MoM |
| secondary (indigo) | Discovery, lower-stakes | + Add Follow-Up (when shown as standalone button) |
| success (emerald) | Save confirmation | Save Changes |
| danger (red) | Destructive, overdue | Delete, Overdue pill |
| slate-100/200 | Neutral, cancel | Cancel buttons in modals |
| white/10 on dark | Header-chrome buttons | Email Report on dark header |

## Adding new components

- Reach for token classes (bg-primary, bg-shell) before raw Tailwind colors.
- For components on dark backgrounds (headers, dark modals), use the
  bg-white/10 family for action buttons — token colors don't read well
  on dark.
- Update this file if a new token is added.
