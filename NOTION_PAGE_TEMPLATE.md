# Chronicle Companion Page

Paste this into a new Notion page and replace placeholders as needed.

## Chronicle

Personal productivity command center for Telegram + the Chronicle dashboard.

### Setup

1. Create or connect the `Chronicle Activity Log` database.
2. Share the database with your Notion integration.
3. Copy the database ID into `.env` and into the browser setup modal for the dashboard.
4. Run the Telegram bot.
5. Open `dashboard/index.html` in your browser.

### Embedded Views

Create these linked database views from `Chronicle Activity Log`:

- `Today`
  Filter: `Date is today`
  Sort: `Date ascending`
- `This Week`
  Filter: `Date is within this week`
  Group by: `Category`
- `Sleep Log`
  Filter: `Category is Sleep`
  Sort: `Date descending`
- `Daily Reviews`
  Filter: `Day Rating is not empty`
  Sort: `Date descending`

### Suggested Sections

#### Daily Reset

- Review yesterday's total hours
- Add today's priorities
- Check planned wake time

#### Weekly Review

- Longest focus block
- Average sleep
- Category balance
- Wins / friction / changes

#### Dashboard Embed

If you host the dashboard HTML on a local or remote web server, embed it with:

```html
<iframe
  src="http://localhost:8000/dashboard/index.html"
  width="100%"
  height="900"
  style="border:0;border-radius:16px;overflow:hidden;"
></iframe>
```

If you're only opening the file directly in your browser, keep using the browser tab instead of an embed.
