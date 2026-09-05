# Progressive accountant handoff — UI mocks

These screenshots use fictional data in the actual frontend. Drive and Mailjet are mocked.

## Progressive export

Only paired, unexported documents appear. **Export N documents** immediately copies them without email. **Finish month & send email** directly exports the remainder and sends the completion email. There is no mode selector.

![Exportable](exportable.png)

## Manual export status

Edit Invoice can mark a manual handoff without sending files or email.

![Manual export status](manual-export.png)

## Final handoff

Expand **Preview final email & notes** to review the message before finishing. The final email includes notes from the remaining documents and documents handed over earlier.

![Completion email](completion-email.png)

To run the interactive mock locally, build the frontend with `npm run build` in `frontend`, then run `uv run python tests/mock_preview.py` from the project root. Open http://localhost:8765/exportable?month=2026-08. All data resets when the mock server restarts.
